// @vitest-environment node
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { createApiClient } from "../src/api/generated/client";
import type { components } from "../src/api/generated/schema";

describe("generated transport", () => {
  it("roundtrips the immutable registry and decimal configuration", async () => {
    const defaultConfig = JSON.parse(
      readFileSync(
        new URL(
          "../../../data/fixtures/fix-01/strategy.canonical.json",
          import.meta.url,
        ),
        "utf8",
      ),
    );
    const id = "22222222-2222-4222-8222-222222222222";
    const version = "33333333-3333-4333-8333-333333333333";
    const hash =
      "2093c63d190815eba052508d6d42d8ae0c93400cf777602d2c5f759627f43f21";
    const client = createApiClient("http://yams.test", async (input) => {
      expect((input as Request).url).toBe(
        "http://yams.test/api/v1/strategies?limit=1",
      );
      return Response.json({
        items: [
          {
            id,
            name: "Risk-Adjusted Momentum",
            is_template: true,
            template_key: "risk_adjusted_momentum_v1",
            created_at: "2026-10-27T00:00:00Z",
            published_version: {
              id: version,
              strategy_id: id,
              version: 1,
              status: "published",
              config: defaultConfig,
              config_sha256: hash,
              published_at: "2026-10-27T00:00:00Z",
            },
          },
        ],
        next_cursor: null,
      });
    });
    const result = await client.GET("/api/v1/strategies", {
      params: { query: { limit: 1 } },
    });
    const row = result.data?.items[0];
    expect(row?.published_version.config_sha256).toBe(hash);
    expect(row?.published_version.config.portfolio.max_position_weight).toBe(
      "0.2",
    );
    expect(
      row?.published_version.config.signals.z_score_weights.momentum_long,
    ).toBe(0.6);
    expect(result.data?.next_cursor).toBeNull();
  });
  it("uses the implemented typed route through an injected fetch transport", async () => {
    const client = createApiClient("http://yams.test", async (input) => {
      expect((input as Request).url).toBe("http://yams.test/livez");
      return new Response(
        JSON.stringify({ status: "alive", paper_only: true }),
        {
          headers: { "content-type": "application/json" },
        },
      );
    });
    const result = await client.GET("/livez");
    expect(result.data).toEqual({ status: "alive", paper_only: true });
  });

  it("preserves high-precision financial strings in generated types", () => {
    const value: components["schemas"]["MarketBarV1"]["close"] =
      "9007199254740993.01";
    expect(JSON.parse(JSON.stringify({ close: value })).close).toBe(value);
    // @ts-expect-error financial values are strings, never JS numbers
    const invalid: components["schemas"]["MarketBarV1"]["close"] = 1.25;
    expect(typeof invalid).toBe("number");
  });
});

it("uses generated publication types with a named creation wrapper and raw version config", async () => {
  const config: components["schemas"]["StrategyConfigV1"] = JSON.parse(
    readFileSync(
      new URL(
        "../../../data/fixtures/fix-01/strategy.canonical.json",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  const id = "22222222-2222-4222-8222-222222222222";
  const seen: unknown[] = [];
  const client = createApiClient("http://yams.test", async (input) => {
    const request = input as Request;
    expect(request.method).toBe("POST");
    seen.push(await request.json());
    return Response.json(
      { error: { code: "STATE_CONFLICT" } },
      { status: 409 },
    );
  });
  await client.POST("/api/v1/strategies", {
    body: { name: "My fork", config },
  });
  await client.POST("/api/v1/strategies/{strategy_id}/versions", {
    params: { path: { strategy_id: id } },
    body: config,
  });
  expect(seen).toEqual([{ name: "My fork", config }, config]);
  expect((seen[1] as typeof config).portfolio.max_position_weight).toBe("0.2");
});
