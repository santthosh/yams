// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { proxyApi } from "../src/lib/proxy";
import fixtures from "./transport-fixtures.json";
afterEach(() => vi.unstubAllEnvs());

it("forwards same-origin diagnostics without a paper-command key and preserves safe stale errors", async () => {
  const make = (origin: string) =>
    new Request("http://web.test/api/v1/strategy-evaluations", {
      method: "POST",
      headers: { origin, "Content-Type": "application/json" },
      body: "{}",
    });
  const fetcher = vi.fn(async (_input, init) => {
    expect(init.headers).toEqual({
      Accept: "application/json",
      "Content-Type": "application/json",
    });
    return Response.json(
      { error: { code: "STALE_DATA", message: "private raw explanation" } },
      { status: 409 },
    );
  });
  expect(
    (
      await proxyApi(
        make("http://outside.test"),
        ["strategy-evaluations"],
        fetcher,
      )
    ).status,
  ).toBe(422);
  expect(fetcher).not.toHaveBeenCalled();
  const result = await proxyApi(
    make("http://web.test"),
    ["strategy-evaluations"],
    fetcher,
  );
  expect(result.status).toBe(409);
  expect((await result.json()).error.code).toBe("STALE_DATA");
});
const request = (path: string, method = "GET") =>
  new Request(`http://web.test/api/v1/${path}`, {
    method,
    headers: { authorization: "private", cookie: "private" },
  });
describe("same-origin proxy boundary", () => {
  it("forwards registry pagination and rejects unsupported operations", async () => {
    vi.stubEnv("API_INTERNAL_ORIGIN", "http://api:8000");
    const fetcher = vi.fn(async (input) => {
      expect(String(input)).toBe("http://api:8000/api/v1/strategies?limit=25");
      return Response.json({ items: [], next_cursor: null });
    });
    expect(
      (await proxyApi(request("strategies?limit=25"), ["strategies"], fetcher))
        .status,
    ).toBe(200);
    expect(
      (
        await proxyApi(
          request("strategies?url=http://outside.test"),
          ["strategies"],
          fetcher,
        )
      ).status,
    ).toBe(404);
    expect(
      (await proxyApi(request("strategies", "PATCH"), ["strategies"], fetcher))
        .status,
    ).toBe(405);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
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

it("publishes closed same-origin strategy paths and preserves safe conflict responses", async () => {
  const id = "184f4ef7-c542-5387-a5aa-9bd4d162efde";
  for (const segments of [["strategies"], ["strategies", id, "versions"]]) {
    const fetcher = vi.fn(async (_input, init) => {
      expect(init.method).toBe("POST");
      expect(init.headers).toEqual({
        Accept: "application/json",
        "Content-Type": "application/json",
      });
      return Response.json(
        { error: { code: "STATE_CONFLICT", message: "private" } },
        { status: 409 },
      );
    });
    const make = (origin: string, body = "{}") =>
      new Request(`http://web.test/api/v1/${segments.join("/")}`, {
        method: "POST",
        headers: {
          origin,
          "Content-Type": "application/json",
          Authorization: "private",
          Cookie: "private",
        },
        body,
      });
    expect(
      (await proxyApi(make("http://outside.test"), segments, fetcher)).status,
    ).toBe(422);
    expect(
      (
        await proxyApi(
          make("http://web.test", "x".repeat(1024 * 1024 + 1)),
          segments,
          fetcher,
        )
      ).status,
    ).toBe(413);
    expect(fetcher).not.toHaveBeenCalled();
    const result = await proxyApi(make("http://web.test"), segments, fetcher);
    expect(result.status).toBe(409);
    expect((await result.json()).error.code).toBe("STATE_CONFLICT");
    expect(fetcher).toHaveBeenCalledTimes(1);
  }
  for (const segments of [
    ["strategies", id],
    ["strategies", id, "versions"],
  ]) {
    const fetcher = vi.fn(async () =>
      Response.json({ items: [], next_cursor: null }),
    );
    expect(
      (await proxyApi(request(segments.join("/")), segments, fetcher)).status,
    ).toBe(200);
  }
  const fetcher = vi.fn();
  expect(
    (
      await proxyApi(
        request("strategies/not-uuid/versions"),
        ["strategies", "not-uuid", "versions"],
        fetcher,
      )
    ).status,
  ).toBe(404);
  expect(
    (
      await proxyApi(
        request(`strategies/${id}/versions?url=private`),
        ["strategies", id, "versions"],
        fetcher,
      )
    ).status,
  ).toBe(404);
  expect(fetcher).not.toHaveBeenCalled();
});

it("forwards experiment pages and same-origin cancellation through the closed routes", async () => {
  const id = "11111111-1111-4111-8111-111111111111";
  const fetcher = vi.fn(async () =>
    Response.json({ items: [], next_cursor: null }),
  );
  for (const parts of [
    ["experiments"],
    ["experiments", id],
    ["experiments", id, "series"],
    ["experiments", id, "trades"],
  ]) {
    expect(
      (await proxyApi(request(parts.join("/")), parts, fetcher)).status,
    ).toBe(200);
  }
  const pages = ["experiments", id, "series"];
  expect(
    (
      await proxyApi(
        request(
          `${pages.join("/")}?limit=2&start_session=2028-07-18&end_session_exclusive=2028-07-24`,
        ),
        pages,
        fetcher,
      )
    ).status,
  ).toBe(200);
  expect(
    (
      await proxyApi(
        request(`${pages.join("/")}?path=../../private`),
        pages,
        fetcher,
      )
    ).status,
  ).toBe(404);
  for (const parts of [["experiments"], ["jobs", id, "cancel"]]) {
    const path = `http://web.test/api/v1/${parts.join("/")}`;
    const post = (origin: string) =>
      new Request(path, {
        method: "POST",
        headers: { origin, "Content-Type": "application/json" },
        body: "{}",
      });
    expect(
      (await proxyApi(post("http://external.test"), parts, fetcher)).status,
    ).toBe(422);
    expect(
      (await proxyApi(post("http://web.test"), parts, fetcher)).status,
    ).toBe(200);
  }
  expect(
    (
      await proxyApi(
        request(`experiments/${id}/download`),
        ["experiments", id, "download"],
        fetcher,
      )
    ).status,
  ).toBe(404);
  expect(
    (
      await proxyApi(
        request(`jobs/${id}/cancel`),
        ["jobs", id, "cancel"],
        fetcher,
      )
    ).status,
  ).toBe(404);
});

it("preserves exact uint64 literals in successful upstream JSON bytes", async () => {
  const id = "11111111-1111-4111-8111-111111111111";
  const raw =
    '{"inputs":{"random_seed":18446744073709551615},"currency":"USD"}';
  const fetcher = vi.fn(
    async () =>
      new Response(raw, { headers: { "Content-Type": "application/json" } }),
  );
  const response = await proxyApi(
    request(`experiments/${id}`),
    ["experiments", id],
    fetcher,
  );
  expect(response.status).toBe(200);
  expect(await response.text()).toBe(raw);
});

it("requires an explicit same-origin account creation key and preserves semantic conflicts", async () => {
  const key = "11111111-1111-4111-8111-111111111111";
  const make = (origin: string, requestKey?: string) =>
    new Request("http://web.test/api/v1/portfolios", {
      method: "POST",
      headers: {
        origin,
        "Content-Type": "application/json",
        ...(requestKey ? { "Idempotency-Key": requestKey } : {}),
        authorization: "private",
        cookie: "private",
      },
      body: '{"name":"SYNTHETIC_DATA_ONLY","opening_cash_usd":"1000.00"}',
    });
  const fetcher = vi.fn(async (_input, init) => {
    expect(init.headers).toEqual({
      Accept: "application/json",
      "Content-Type": "application/json",
      "Idempotency-Key": key,
    });
    return Response.json(
      {
        error: {
          code: "IDEMPOTENCY_CONFLICT",
          message: "private provider details",
        },
      },
      { status: 409 },
    );
  });
  expect(
    (await proxyApi(make("http://web.test"), ["portfolios"], fetcher)).status,
  ).toBe(422);
  expect(
    (await proxyApi(make("http://outside.test", key), ["portfolios"], fetcher))
      .status,
  ).toBe(422);
  expect(fetcher).not.toHaveBeenCalled();
  const result = await proxyApi(
    make("http://web.test", key),
    ["portfolios"],
    fetcher,
  );
  expect(result.status).toBe(409);
  const response = await result.json();
  expect(response.error.code).toBe("IDEMPOTENCY_CONFLICT");
  expect(JSON.stringify(response)).not.toContain("private provider details");
});

it("exposes only account reads and creation while future authorization and funding paths stay closed", async () => {
  const id = "11111111-1111-4111-8111-111111111111";
  const fetcher = vi.fn(async () =>
    Response.json({ items: [], next_cursor: null }),
  );
  for (const [path, parts] of [
    ["portfolios?mode=synthetic_fixture&limit=1", ["portfolios"]],
    [`portfolios/${id}`, ["portfolios", id]],
    [
      `portfolios/${id}/transactions?limit=1`,
      ["portfolios", id, "transactions"],
    ],
  ] as [string, string[]][]) {
    expect((await proxyApi(request(path), parts, fetcher)).status).toBe(200);
  }
  expect(fetcher).toHaveBeenCalledTimes(3);
  expect(
    (
      await proxyApi(
        request(`portfolios/${id}?snapshot_id=${id}`),
        ["portfolios", id],
        fetcher,
      )
    ).status,
  ).toBe(404);
  for (const extra of ["apply", "deposit", "withdraw"]) {
    const response = await proxyApi(
      request(`portfolios/${id}/${extra}`, "POST"),
      ["portfolios", id, extra],
      fetcher,
    );
    expect(response.status).toBe(405);
  }
  expect(fetcher).toHaveBeenCalledTimes(3);
});

it("allows scoped recommendation and forecast reads with exact seed bytes", async () => {
  const id = "11111111-1111-4111-8111-111111111111";
  const raw = '{"seed":18446744073709551615,"status":"available"}';
  const fetcher = vi.fn(
    async () =>
      new Response(raw, { headers: { "Content-Type": "application/json" } }),
  );
  for (const parts of [
    ["portfolios", id, "recommendations"],
    ["recommendations", id],
    ["forecasts", id],
  ]) {
    const response = await proxyApi(request(parts.join("/")), parts, fetcher);
    expect(response.status).toBe(200);
    expect(await response.text()).toBe(raw);
  }
  expect(
    (
      await proxyApi(
        request(`portfolios/${id}/recommendations?limit=1&cursor=abc`),
        ["portfolios", id, "recommendations"],
        fetcher,
      )
    ).status,
  ).toBe(200);
  expect(
    (
      await proxyApi(
        request(`recommendations/${id}?approved_at=now`),
        ["recommendations", id],
        fetcher,
      )
    ).status,
  ).toBe(404);
  expect(
    (
      await proxyApi(
        request(`forecasts/${id}`, "POST"),
        ["forecasts", id],
        fetcher,
      )
    ).status,
  ).toBe(405);
  expect(
    (
      await proxyApi(
        request(`recommendations/${id}/apply`, "POST"),
        ["recommendations", id, "apply"],
        fetcher,
      )
    ).status,
  ).toBe(422);
});

it("forwards only a valid recommendation key and preserves exact request tokens", async () => {
  const id = "11111111-1111-4111-8111-111111111111";
  const parts = ["portfolios", id, "recommendations"];
  const raw =
    '{"as_of_session":"2028-07-17","clock_mode":"synthetic_replay","seed":18446744073709551615}';
  const make = (origin: string, key?: string) =>
    new Request(`http://web.test/api/v1/${parts.join("/")}`, {
      method: "POST",
      headers: {
        origin,
        "Content-Type": "application/json",
        ...(key ? { "Idempotency-Key": key } : {}),
        cookie: "private",
        authorization: "private",
      },
      body: raw,
    });
  const fetcher = vi.fn(async (_input, init) => {
    expect(init.body).toBe(raw);
    expect(init.headers).toEqual({
      Accept: "application/json",
      "Content-Type": "application/json",
      "Idempotency-Key": id,
    });
    return Response.json(
      { job_id: id, recommendation_id: id },
      { status: 202 },
    );
  });
  expect(
    (await proxyApi(make("http://outside.test", id), parts, fetcher)).status,
  ).toBe(422);
  expect(
    (await proxyApi(make("http://web.test", "invalid"), parts, fetcher)).status,
  ).toBe(422);
  expect(fetcher).not.toHaveBeenCalled();
  expect(
    (await proxyApi(make("http://web.test", id), parts, fetcher)).status,
  ).toBe(202);
});

it.each(["queued", "running", "failed", "cancelled"])(
  "retains only safe %s forecast job details",
  async (status) => {
    const id = "11111111-1111-4111-8111-111111111111";
    const fetcher = vi.fn(async () =>
      Response.json(
        {
          error: {
            code: "STATE_CONFLICT",
            message: "private provider trace",
            details: {
              job_id: id,
              status,
              kind: "forecast",
              provider_token: "private credential",
            },
            correlation_id: id,
          },
        },
        { status: 409 },
      ),
    );
    const response = await proxyApi(
      request(`forecasts/${id}`),
      ["forecasts", id],
      fetcher,
    );
    expect(response.status).toBe(409);
    const body = await response.json();
    expect(body.error.details).toEqual({
      job_id: id,
      status,
      kind: "forecast",
    });
    expect(body.error.retryable).toBe(["queued", "running"].includes(status));
    expect(JSON.stringify(body)).not.toContain("private");
  },
);

it("forwards only scoped paper controls with mandatory operation keys", async () => {
  const id = "11111111-1111-4111-8111-111111111111";
  const fetcher = vi.fn(async (_input, init) => {
    expect(init.headers).not.toHaveProperty("Cookie");
    expect(init.headers).not.toHaveProperty("Authorization");
    return Response.json({ batch_id: id });
  });
  for (const parts of [
    ["recommendations", id, "apply"],
    ["order-batches", id, "advance-fixture"],
  ]) {
    const make = (key?: string) =>
      new Request(`http://web.test/api/v1/${parts.join("/")}`, {
        method: "POST",
        headers: {
          Origin: "http://web.test",
          "Content-Type": "application/json",
          Cookie: "private",
          Authorization: "private",
          ...(key ? { "Idempotency-Key": key } : {}),
        },
        body:
          parts[2] === "apply"
            ? '{"expected_revision":9223372036854775807}'
            : "{}",
      });
    expect((await proxyApi(make(), parts, fetcher)).status).toBe(422);
    expect((await proxyApi(make("invalid"), parts, fetcher)).status).toBe(422);
    expect((await proxyApi(make(id), parts, fetcher)).status).toBe(200);
    expect(fetcher.mock.lastCall?.[1].headers["Idempotency-Key"]).toBe(id);
    if (parts[2] === "apply")
      expect(fetcher.mock.lastCall?.[1].body).toBe(
        '{"expected_revision":9223372036854775807}',
      );
  }
  const parts = ["recommendations", id, "apply-result"];
  expect(
    (await proxyApi(request(parts.join("/")), parts, fetcher)).status,
  ).toBe(422);
  const recover = new Request(`http://web.test/api/v1/${parts.join("/")}`, {
    headers: { "Idempotency-Key": id, Cookie: "private" },
  });
  expect((await proxyApi(recover, parts, fetcher)).status).toBe(200);
  expect(fetcher.mock.lastCall?.[1].headers["Idempotency-Key"]).toBe(id);
  for (const parts of [
    ["recommendations", id, "dismiss"],
    ["order-batches", id, "cancel"],
  ]) {
    const body = new Request(`http://web.test/api/v1/${parts.join("/")}`, {
      method: "POST",
      headers: {
        Origin: "http://web.test",
        "Content-Type": "application/json",
      },
      body: "{}",
    });
    expect((await proxyApi(body, parts, fetcher)).status).toBe(200);
  }
  expect(
    (
      await proxyApi(
        request(`order-batches/${id}`),
        ["order-batches", id],
        fetcher,
      )
    ).status,
  ).toBe(200);
  expect(
    (
      await proxyApi(
        request(`order-batches/${id}/fill`, "POST"),
        ["order-batches", id, "fill"],
        fetcher,
      )
    ).status,
  ).toBe(405);
  expect(
    (
      await proxyApi(
        request(`order-batches/${id}?price=1`),
        ["order-batches", id],
        fetcher,
      )
    ).status,
  ).toBe(404);
});

it("allows readonly portfolio schedule status without forwarding credentials or accepting clocks", async () => {
  const id = "11111111-1111-4111-8111-111111111111";
  const parts = ["portfolios", id, "schedule"];
  const fetcher = vi.fn(async (_input, init) => {
    expect(init.headers).toEqual({ Accept: "application/json" });
    return Response.json({ portfolio_id: id, clock_mode: "synthetic_replay" });
  });
  const read = new Request(`http://web.test/api/v1/${parts.join("/")}`, {
    headers: {
      Cookie: "private",
      Authorization: "private",
      "Idempotency-Key": id,
    },
  });
  expect((await proxyApi(read, parts, fetcher)).status).toBe(200);
  expect(
    (await proxyApi(request(parts.join("/") + "?clock=2030"), parts, fetcher))
      .status,
  ).toBe(404);
  expect(
    (await proxyApi(request(parts.join("/"), "POST"), parts, fetcher)).status,
  ).toBe(405);
  expect(fetcher).toHaveBeenCalledTimes(1);
});
