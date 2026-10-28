// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { proxyApi } from "../src/lib/proxy";
import fixtures from "./transport-fixtures.json";
afterEach(() => vi.unstubAllEnvs());
const request = (path: string, method = "GET") =>
  new Request(`http://web.test/api/v1/${path}`, {
    method,
    headers: { authorization: "private", cookie: "private" },
  });
describe("same-origin proxy boundary", () => {
  it("uses only the configured private origin and strips incoming credentials", async () => {
    vi.stubEnv("API_INTERNAL_ORIGIN", "http://api:8000");
    const fetcher = vi.fn(async (input, init) => {
      expect(String(input)).toBe("http://api:8000/api/v1/workspace");
      expect(init.headers).toEqual({ Accept: "application/json" });
      expect(init.redirect).toBe("error");
      expect(init.signal).toBeInstanceOf(AbortSignal);
      return Response.json(fixtures.workspace, {
        headers: { "set-cookie": "bad" },
      });
    });
    const result = await proxyApi(request("workspace"), ["workspace"], fetcher);
    expect(result.status).toBe(200);
    expect(result.headers.get("set-cookie")).toBeNull();
    expect(result.headers.get("cache-control")).toBe("no-store");
  });
  it.each([
    ["unknown", ["unknown"]],
    ["health?url=http://evil.test", ["health"]],
    ["jobs/invalid", ["jobs", "invalid"]],
    ["health/../../secret", ["health", "..", "secret"]],
    ["__control", ["__control"]],
  ] as [string, string[]][])(
    "rejects %s without a fetch",
    async (path, parts) => {
      const fetcher = vi.fn();
      expect((await proxyApi(request(path), parts, fetcher)).status).toBe(404);
      expect(fetcher).not.toHaveBeenCalled();
    },
  );
  it("rejects write methods without a fetch", async () => {
    const fetcher = vi.fn();
    expect(
      (await proxyApi(request("workspace", "POST"), ["workspace"], fetcher))
        .status,
    ).toBe(405);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it.each([
    "http://user:password@api:8000",
    "file:///etc/passwd",
    "http://api:8000/other",
  ])("rejects malformed server configuration", async (origin) => {
    vi.stubEnv("API_INTERNAL_ORIGIN", origin);
    const fetcher = vi.fn();
    expect(
      (await proxyApi(request("health"), ["health"], fetcher)).status,
    ).toBe(503);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("sanitizes upstream errors while preserving safe correlation", async () => {
    const correlation = "33333333-3333-4333-8333-333333333333";
    const result = await proxyApi(
      request("workspace"),
      ["workspace"],
      async () =>
        Response.json(
          {
            error: {
              message: "secret password raw stack",
              correlation_id: correlation,
            },
          },
          { status: 500 },
        ),
    );
    const body = await result.json();
    expect(body.error.correlation_id).toBe(correlation);
    expect(JSON.stringify(body)).not.toContain("secret");
  });
  it("converts timeout/non-JSON failures to safe retryable diagnostics", async () => {
    for (const fetcher of [
      async () => {
        throw new DOMException("private origin", "TimeoutError");
      },
      async () => new Response("raw stack"),
    ]) {
      const result = await proxyApi(request("health"), ["health"], fetcher);
      const body = await result.json();
      expect(result.status).toBe(503);
      expect(body.error.retryable).toBe(true);
      expect(body.error.correlation_id).toMatch(/^[0-9a-f-]{36}$/);
      expect(JSON.stringify(body)).not.toMatch(/private origin|raw stack/);
    }
  });
  it("retains the health contract on not-ready responses", async () => {
    const health = { ...fixtures.health, status: "not_ready" };
    const result = await proxyApi(request("health"), ["health"], async () =>
      Response.json(health, { status: 503 }),
    );
    expect(result.status).toBe(503);
    expect(await result.json()).toEqual(health);
  });
});

it("forwards only allowed data query fields", async () => {
  vi.stubEnv("API_INTERNAL_ORIGIN", "http://api:8000");
  const fetcher = vi.fn(async (input) => {
    expect(String(input)).toBe(
      "http://api:8000/api/v1/data/assets?mode=synthetic_fixture&query=AAA",
    );
    return Response.json({ items: [], next_cursor: null });
  });
  expect(
    (
      await proxyApi(
        request("data/assets?mode=synthetic_fixture&query=AAA"),
        ["data", "assets"],
        fetcher,
      )
    ).status,
  ).toBe(200);
  expect(
    (
      await proxyApi(
        request("data/assets?url=http://outside.test"),
        ["data", "assets"],
        fetcher,
      )
    ).status,
  ).toBe(404);
  expect(fetcher).toHaveBeenCalledTimes(1);
});

it("requires same-origin refresh and forwards a bounded JSON payload with its request key", async () => {
  const key = "11111111-1111-4111-8111-111111111111";
  const make = (origin: string) =>
    new Request("http://web.test/api/v1/data/refresh", {
      method: "POST",
      headers: {
        origin,
        "Content-Type": "application/json",
        "Idempotency-Key": key,
        cookie: "private",
      },
      body: JSON.stringify({
        schema_version: 1,
        source_mode: "synthetic_fixture",
      }),
    });
  const fetcher = vi.fn(async (_input, init) => {
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({
      Accept: "application/json",
      "Content-Type": "application/json",
      "Idempotency-Key": key,
    });
    expect(JSON.parse(init.body).source_mode).toBe("synthetic_fixture");
    return Response.json(fixtures.job, { status: 202 });
  });
  expect(
    (await proxyApi(make("http://outside.test"), ["data", "refresh"], fetcher))
      .status,
  ).toBe(422);
  expect(fetcher).not.toHaveBeenCalled();
  expect(
    (await proxyApi(make("http://web.test"), ["data", "refresh"], fetcher))
      .status,
  ).toBe(202);
});

it("compares refresh Origin with the browser-facing Host behind Docker port mapping", async () => {
  const incoming = new Request("http://localhost:3000/api/v1/data/refresh", {
    method: "POST",
    headers: {
      host: "127.0.0.1:55123",
      origin: "http://127.0.0.1:55123",
      "Content-Type": "application/json",
      "Idempotency-Key": "11111111-1111-4111-8111-111111111111",
    },
    body: "{}",
  });
  const fetcher = vi.fn(async () =>
    Response.json(fixtures.job, { status: 202 }),
  );
  expect((await proxyApi(incoming, ["data", "refresh"], fetcher)).status).toBe(
    202,
  );
  expect(fetcher).toHaveBeenCalledTimes(1);
});

it("rejects oversized refresh bodies and missing request keys before upstream access", async () => {
  const fetcher = vi.fn();
  const headers = {
    origin: "http://web.test",
    "Content-Type": "application/json",
    "Idempotency-Key": "11111111-1111-4111-8111-111111111111",
  };
  const large = new Request("http://web.test/api/v1/data/refresh", {
    method: "POST",
    headers,
    body: new Uint8Array(1024 * 1024 + 1),
  });
  expect((await proxyApi(large, ["data", "refresh"], fetcher)).status).toBe(
    413,
  );
  const missing = new Request("http://web.test/api/v1/data/refresh", {
    method: "POST",
    headers: {
      origin: headers.origin,
      "Content-Type": headers["Content-Type"],
    },
    body: "{}",
  });
  expect((await proxyApi(missing, ["data", "refresh"], fetcher)).status).toBe(
    422,
  );
  expect(fetcher).not.toHaveBeenCalled();
});
