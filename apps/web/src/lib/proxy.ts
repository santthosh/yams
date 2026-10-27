import type { components } from "../api/generated/schema";
import { UUID_PATTERN } from "./validation";
export function safeError(
  code: components["schemas"]["ErrorDetail"]["code"],
  message: string,
  status: number,
  correlationId?: string,
): Response {
  const body: components["schemas"]["ErrorEnvelope"] = {
    error: {
      code,
      message,
      details: {},
      retryable: status === 503,
      correlation_id:
        correlationId && UUID_PATTERN.test(correlationId)
          ? correlationId
          : crypto.randomUUID(),
    },
  };
  return Response.json(body, {
    status,
    headers: { "Cache-Control": "no-store" },
  });
}
export async function proxyApi(
  request: Request,
  segments: string[],
  fetcher: typeof fetch = fetch,
): Promise<Response> {
  if (request.method !== "GET")
    return safeError(
      "METHOD_NOT_ALLOWED",
      "This operation is not available.",
      405,
    );
  const allowed =
    (segments.length === 1 && ["health", "workspace"].includes(segments[0])) ||
    (segments.length === 2 &&
      segments[0] === "jobs" &&
      UUID_PATTERN.test(segments[1]));
  if (!allowed || new URL(request.url).search)
    return safeError("NOT_FOUND", "This API route is not available.", 404);
  try {
    const origin = new URL(
      process.env.API_INTERNAL_ORIGIN || "http://api:8000",
    );
    if (
      !["http:", "https:"].includes(origin.protocol) ||
      origin.username ||
      origin.password ||
      origin.pathname !== "/" ||
      origin.search ||
      origin.hash
    )
      throw new Error("Invalid internal origin");
    const response = await fetcher(
      new URL(`/api/v1/${segments.join("/")}`, origin),
      {
        headers: { Accept: "application/json" },
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(3000),
      },
    );
    if (!response.headers.get("content-type")?.includes("application/json"))
      throw new Error("Unexpected response");
    const body: unknown = await response.json();
    if (body === null || typeof body !== "object" || Array.isArray(body))
      throw new Error("Unexpected response");
    const healthFailure =
      segments[0] === "health" &&
      response.status === 503 &&
      "status" in body &&
      body.status === "not_ready" &&
      "database" in body &&
      "fixtures" in body;
    if (!response.ok && !healthFailure) {
      const error =
        "error" in body && typeof body.error === "object" && body.error !== null
          ? body.error
          : null;
      const correlation =
        error &&
        "correlation_id" in error &&
        typeof error.correlation_id === "string"
          ? error.correlation_id
          : undefined;
      return response.status === 404
        ? safeError(
            "NOT_FOUND",
            "The requested record was not found.",
            404,
            correlation,
          )
        : safeError(
            "NOT_READY",
            "The local service could not complete this request.",
            503,
            correlation,
          );
    }
    return Response.json(body, {
      status: response.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return safeError(
      "NOT_READY",
      "The local service is unavailable or took too long to respond. Try again.",
      503,
    );
  }
}
