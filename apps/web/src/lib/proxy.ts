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
  const url = new URL(request.url);
  const dataPath = segments.length === 2 && segments[0] === "data";
  const readData =
    dataPath && ["snapshots", "assets", "health"].includes(segments[1]);
  const refresh = dataPath && segments[1] === "refresh";
  const evaluate =
    segments.length === 1 && segments[0] === "strategy-evaluations";
  const readEvaluation =
    segments.length === 2 &&
    segments[0] === "strategy-evaluations" &&
    UUID_PATTERN.test(segments[1]);
  const readStrategies = segments.length === 1 && segments[0] === "strategies";
  if (
    request.method !== "GET" &&
    !(request.method === "POST" && (refresh || evaluate))
  )
    return safeError(
      "METHOD_NOT_ALLOWED",
      "This operation is not available.",
      405,
    );
  const allowed =
    request.method === "POST"
      ? refresh || evaluate
      : readData ||
        readStrategies ||
        readEvaluation ||
        (segments.length === 1 &&
          ["health", "workspace"].includes(segments[0])) ||
        (segments.length === 2 &&
          segments[0] === "jobs" &&
          UUID_PATTERN.test(segments[1]));
  const queryKeys = readData
    ? segments[1] === "assets"
      ? ["mode", "snapshot_id", "query", "limit", "cursor"]
      : segments[1] === "snapshots"
        ? ["mode", "limit", "cursor"]
        : ["mode"]
    : readStrategies
      ? ["limit", "cursor"]
      : [];
  if (
    !allowed ||
    [...url.searchParams.keys()].some((key) => !queryKeys.includes(key))
  )
    return safeError("NOT_FOUND", "This API route is not available.", 404);
  const headers: Record<string, string> = { Accept: "application/json" };
  let payload: string | undefined;
  if (request.method === "POST") {
    const host = request.headers.get("host");
    // Next may construct an internal localhost URL while Host retains the published port.
    // Origin must match that browser-facing authority, never X-Forwarded-Host.
    if (host && !/^[a-z0-9.:[\]-]+$/i.test(host))
      return safeError("VALIDATION_ERROR", "Refresh host is invalid.", 422);
    const browserOrigin = host ? `${url.protocol}//${host}` : url.origin;
    if (
      request.headers.get("origin") !== browserOrigin ||
      !request.headers.get("content-type")?.startsWith("application/json")
    )
      return safeError(
        "VALIDATION_ERROR",
        "Refresh requires a same-origin JSON request.",
        422,
      );
    const key = request.headers.get("Idempotency-Key");
    if (refresh && (!key || !UUID_PATTERN.test(key)))
      return safeError(
        "VALIDATION_ERROR",
        "Refresh requires a valid request key.",
        422,
      );
    const reader = request.body?.getReader();
    if (!reader)
      return safeError("VALIDATION_ERROR", "Refresh input is required.", 422);
    const chunks: Uint8Array[] = [];
    let size = 0;
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      size += chunk.value.byteLength;
      if (size > 1024 * 1024) {
        await reader.cancel();
        return safeError("LIMIT_EXCEEDED", "Refresh input is too large.", 413);
      }
      chunks.push(chunk.value);
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.length;
    }
    payload = new TextDecoder().decode(bytes);
    headers["Content-Type"] = "application/json";
    if (refresh && key) headers["Idempotency-Key"] = key;
  }
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
      new URL(`/api/v1/${segments.join("/")}${url.search}`, origin),
      {
        method: request.method,
        headers,
        body: payload,
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
      if (response.status === 422) {
        const code =
          error && "code" in error && error.code === "WORKLOAD_LIMIT"
            ? "WORKLOAD_LIMIT"
            : error &&
                "code" in error &&
                error.code === "INSUFFICIENT_MARKET_DATA"
              ? "INSUFFICIENT_MARKET_DATA"
              : "VALIDATION_ERROR";
        return safeError(
          code,
          "Request does not match the data contract.",
          422,
          correlation,
        );
      }
      if (response.status === 409) {
        const code =
          error && "code" in error && error.code === "STALE_DATA"
            ? "STALE_DATA"
            : refresh
              ? "IDEMPOTENCY_CONFLICT"
              : "STATE_CONFLICT";
        return safeError(
          code,
          "Request conflicts with an earlier operation.",
          409,
          correlation,
        );
      }
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
