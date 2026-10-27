import { describe, expect, it } from "vitest";
import { createApiClient } from "../src/api/generated/client";
import type { components } from "../src/api/generated/schema";

describe("generated transport", () => {
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
