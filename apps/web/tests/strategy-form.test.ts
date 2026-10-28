// @vitest-environment node
import { readFileSync } from "node:fs";
import { expect, it } from "vitest";
import type { components } from "../src/api/generated/schema";
import {
  changes,
  configFromDraft,
  initialDraft,
  validName,
} from "../src/components/strategy/config-form";
const source = (): components["schemas"]["StrategyConfigV1"] =>
  JSON.parse(
    readFileSync(
      new URL(
        "../../../data/fixtures/fix-01/strategy.canonical.json",
        import.meta.url,
      ),
      "utf8",
    ),
  );
it("preserves complete generated config, decimal lexemes and immutable source while editing supported fields", () => {
  const config = source();
  const draft = initialDraft(config);
  draft["portfolio.max_position_weight"] = "0.150000";
  draft["portfolio.min_trade_usd"] = "999999999999.99";
  draft["signals.volatility_sessions"] = "80";
  draft["signals.kind"] = "execute_code";
  draft["unknown_operator"] = "untrusted";
  const edited = configFromDraft(config, draft);
  expect(edited.portfolio.max_position_weight).toBe("0.150000");
  expect(edited.portfolio.min_trade_usd).toBe("999999999999.99");
  expect(edited.signals.volatility_sessions).toBe(80);
  expect(edited.signals.kind).toBe("risk_adjusted_momentum");
  expect(edited).not.toHaveProperty("unknown_operator");
  expect(config.portfolio.max_position_weight).toBe("0.2");
  expect(config.signals.volatility_sessions).toBe(60);
});
it("rejects lossy statistical values and invalid names before building a request", () => {
  const config = source();
  for (const value of ["0.600000000000000001", "NaN", "1e-1000"]) {
    expect(() =>
      configFromDraft(config, {
        ...initialDraft(config),
        "signals.z_score_weights.momentum_long": value,
      }),
    ).toThrow();
  }
  expect(validName("😀".repeat(120))).toBe(true);
  expect(validName("😀".repeat(121))).toBe(false);
  expect(validName("bad\nname")).toBe(false);
  expect(validName("  ")).toBe(false);
});
it("diffs rule semantics without treating numeric display names as decimal amounts", () => {
  const config = source();
  expect(
    changes(
      config,
      configFromDraft(config, {
        ...initialDraft(config),
        "portfolio.max_position_weight": "0.200000",
      }),
    ),
  ).toEqual([]);
  config.display_name = "0.20";
  const edited = configFromDraft(config, {
    ...initialDraft(config),
    display_name: "0.2",
  });
  expect(changes(config, edited)).toEqual([
    { label: "Rule display name", before: "0.20", after: "0.2" },
  ]);
});

it.each(["mean_reversion", "low_volatility"])(
  "edits only the supported %s family fields",
  (kind) => {
    const config: components["schemas"]["StrategyConfigV1"] = JSON.parse(
      readFileSync(
        new URL(
          `../../../data/fixtures/template_extensions/${kind}.canonical.json`,
          import.meta.url,
        ),
        "utf8",
      ),
    );
    const draft = initialDraft(config);
    expect(draft).not.toHaveProperty("signals.momentum_long_sessions");
    draft["signals.volatility_sessions"] = "80";
    draft["signals.momentum_long_sessions"] = "126";
    const edited = configFromDraft(config, draft);
    expect(edited.signals.kind).toBe(kind);
    expect(edited.signals.volatility_sessions).toBe(80);
    expect(edited.signals).not.toHaveProperty("momentum_long_sessions");
    expect(config.signals.volatility_sessions).toBe(60);
  },
);
