import type { components } from "../api/generated/schema";
import { UUID_PATTERN } from "./validation";
export function safeError(
  code: components["schemas"]["ErrorDetail"]["code"],
  message: string,
  status: number,
  correlationId?: string,
  details: components["schemas"]["ErrorDetail"]["details"] = {},
  retryable = status === 503,
): Response {
  const body: components["schemas"]["ErrorEnvelope"] = {
    error: {
      code,
      message,
      details,
      retryable,
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
  const portfolios = segments.length === 1 && segments[0] === "portfolios";
  const portfolioDetail =
    segments.length === 2 &&
    segments[0] === "portfolios" &&
    UUID_PATTERN.test(segments[1]);
  const portfolioTransactions =
    segments.length === 3 &&
    segments[0] === "portfolios" &&
    UUID_PATTERN.test(segments[1]) &&
    segments[2] === "transactions";
  const portfolioSchedule =
    segments.length === 3 &&
    segments[0] === "portfolios" &&
    UUID_PATTERN.test(segments[1]) &&
    segments[2] === "schedule";
  const portfolioRecommendations =
    segments.length === 3 &&
    segments[0] === "portfolios" &&
    UUID_PATTERN.test(segments[1]) &&
    segments[2] === "recommendations";
  const recommendationDetail =
    segments.length === 2 &&
    segments[0] === "recommendations" &&
    UUID_PATTERN.test(segments[1]);
  const recommendationAction =
    segments.length === 3 &&
    segments[0] === "recommendations" &&
    UUID_PATTERN.test(segments[1]) &&
    ["apply", "dismiss"].includes(segments[2]);
  const approvalRecovery =
    segments.length === 3 &&
    segments[0] === "recommendations" &&
    UUID_PATTERN.test(segments[1]) &&
    segments[2] === "apply-result";
  const batchDetail =
    segments.length === 2 &&
    segments[0] === "order-batches" &&
    UUID_PATTERN.test(segments[1]);
  const batchAction =
    segments.length === 3 &&
    segments[0] === "order-batches" &&
    UUID_PATTERN.test(segments[1]) &&
    ["cancel", "advance-fixture"].includes(segments[2]);
  const keyedPaperAction =
    (recommendationAction && segments[2] === "apply") ||
    (batchAction && segments[2] === "advance-fixture");
  const forecastDetail =
    segments.length === 2 &&
    segments[0] === "forecasts" &&
    UUID_PATTERN.test(segments[1]);
  const experiments = segments.length === 1 && segments[0] === "experiments";
  const experimentDetail =
    segments.length === 2 &&
    segments[0] === "experiments" &&
    UUID_PATTERN.test(segments[1]);
  const experimentSamples =
    segments.length === 3 &&
    segments[0] === "experiments" &&
    UUID_PATTERN.test(segments[1]) &&
    ["series", "trades"].includes(segments[2]);
  const cancelJob =
    segments.length === 3 &&
    segments[0] === "jobs" &&
    UUID_PATTERN.test(segments[1]) &&
    segments[2] === "cancel";
  const readStrategies = segments.length === 1 && segments[0] === "strategies";
  const strategyDetail =
    segments.length === 2 &&
    segments[0] === "strategies" &&
    UUID_PATTERN.test(segments[1]);
  const strategyVersions =
    segments.length === 3 &&
    segments[0] === "strategies" &&
    UUID_PATTERN.test(segments[1]) &&
    segments[2] === "versions";
  if (
    request.method !== "GET" &&
    !(
      request.method === "POST" &&
      (refresh ||
        portfolios ||
        portfolioRecommendations ||
        evaluate ||
        readStrategies ||
        strategyVersions ||
        experiments ||
        cancelJob ||
        recommendationAction ||
        batchAction)
    )
  )
    return safeError(
      "METHOD_NOT_ALLOWED",
      "This operation is not available.",
      405,
    );
  const allowed =
    request.method === "POST"
      ? refresh ||
        portfolios ||
        portfolioRecommendations ||
        evaluate ||
        readStrategies ||
        strategyVersions ||
        experiments ||
        cancelJob ||
        recommendationAction ||
        batchAction
      : approvalRecovery ||
        batchDetail ||
        portfolios ||
        portfolioDetail ||
        portfolioTransactions ||
        portfolioSchedule ||
        portfolioRecommendations ||
        recommendationDetail ||
        forecastDetail ||
        experiments ||
        experimentDetail ||
        experimentSamples ||
        readData ||
        readStrategies ||
        strategyDetail ||
        strategyVersions ||
        readEvaluation ||
        (segments.length === 1 &&
          ["health", "workspace"].includes(segments[0])) ||
        (segments.length === 2 &&
          segments[0] === "jobs" &&
          UUID_PATTERN.test(segments[1]));
  const queryKeys =
    portfolios && request.method === "GET"
      ? ["mode", "limit", "cursor"]
      : portfolioTransactions ||
          (portfolioRecommendations && request.method === "GET")
        ? ["limit", "cursor"]
        : experiments && request.method === "GET"
          ? ["limit", "cursor"]
          : experimentSamples
            ? ["limit", "cursor", "start_session", "end_session_exclusive"]
            : readData
              ? segments[1] === "assets"
                ? ["mode", "snapshot_id", "query", "limit", "cursor"]
                : segments[1] === "snapshots"
                  ? ["mode", "limit", "cursor"]
                  : ["mode"]
              : (readStrategies || strategyVersions) && request.method === "GET"
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
      return safeError("VALIDATION_ERROR", "Request host is invalid.", 422);
    const browserOrigin = host ? `${url.protocol}//${host}` : url.origin;
    if (
      request.headers.get("origin") !== browserOrigin ||
      !request.headers.get("content-type")?.startsWith("application/json")
    )
      return safeError(
        "VALIDATION_ERROR",
        "Operation requires a same-origin JSON request.",
        422,
      );
    const key = request.headers.get("Idempotency-Key");
    if (
      (refresh || portfolios || keyedPaperAction) &&
      (!key || !UUID_PATTERN.test(key))
    )
      return safeError(
        "VALIDATION_ERROR",
        "This operation requires a valid request key.",
        422,
      );
    if (portfolioRecommendations && key && !UUID_PATTERN.test(key))
      return safeError("VALIDATION_ERROR", "Request key is invalid.", 422);
    const reader = request.body?.getReader();
    if (!reader)
      return safeError("VALIDATION_ERROR", "Request input is required.", 422);
    const chunks: Uint8Array[] = [];
    let size = 0;
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      size += chunk.value.byteLength;
      if (size > 1024 * 1024) {
        await reader.cancel();
        return safeError("LIMIT_EXCEEDED", "Request input is too large.", 413);
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
    if (
      (refresh || portfolios || portfolioRecommendations || keyedPaperAction) &&
      key
    )
      headers["Idempotency-Key"] = key;
  }
  if (request.method === "GET" && approvalRecovery) {
    const key = request.headers.get("Idempotency-Key");
    if (!key || !UUID_PATTERN.test(key))
      return safeError(
        "VALIDATION_ERROR",
        "Recovery requires a valid request key.",
        422,
      );
    headers["Idempotency-Key"] = key;
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
    const rawBody = await response.text();
    // Validate/sanitize the envelope without re-encoding successful JSON.
    // Parsing into JS numbers and serializing again corrupts uint64 literals.
    const body: unknown = JSON.parse(rawBody);
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
        if (
          (recommendationDetail || forecastDetail) &&
          error &&
          "code" in error &&
          error.code === "STATE_CONFLICT" &&
          "details" in error &&
          typeof error.details === "object" &&
          error.details !== null
        ) {
          const state = error.details;
          if (
            "job_id" in state &&
            typeof state.job_id === "string" &&
            UUID_PATTERN.test(state.job_id) &&
            "status" in state &&
            typeof state.status === "string" &&
            [
              "queued",
              "running",
              "cancel_requested",
              "failed",
              "cancelled",
            ].includes(state.status) &&
            "kind" in state &&
            typeof state.kind === "string" &&
            state.kind === (forecastDetail ? "forecast" : "evaluate_portfolio")
          )
            return safeError(
              "STATE_CONFLICT",
              "Resource has no completed publication; inspect its job status.",
              409,
              correlation,
              { job_id: state.job_id, status: state.status, kind: state.kind },
              ["queued", "running", "cancel_requested"].includes(state.status),
            );
        }
        const code =
          error && "code" in error && error.code === "STALE_DATA"
            ? "STALE_DATA"
            : refresh ||
                (error &&
                  "code" in error &&
                  error.code === "IDEMPOTENCY_CONFLICT")
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
    return new Response(rawBody, {
      status: response.status,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return safeError(
      "NOT_READY",
      "The local service is unavailable or took too long to respond. Try again.",
      503,
    );
  }
}
