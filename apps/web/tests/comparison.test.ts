import { describe, expect, it } from "vitest";
import sample from "./experiment-transport.json";
import type { components } from "../src/api/generated/schema";
import {
  comparisonDifferences,
  configDifferences,
  fairRerunBody,
  oneRuleConfig,
} from "../src/components/experiments/comparison";

type S = components["schemas"];
const source = sample.completed as S["ExperimentDetailV1"];
describe("stored comparison and controlled challenge", () => {
  it("uses all backend comparison terms and never mistakes a matching ID for fair settings", () => {
    const other = structuredClone(source);
    other.id = "77777777-7777-4777-8777-777777777777";
    expect(comparisonDifferences([source, other])).toEqual([]);
    other.report!.comparison.initial_capital_usd = "2000.00";
    other.report!.comparison.evaluation_split.holdout_fraction = 0.5;
    other.report!.comparison_sha256 = "b".repeat(64);
    expect(
      comparisonDifferences([source, other]).map((row) => row.field),
    ).toEqual(["evaluation_split", "initial_capital_usd"]);
    // Equal visible terms cannot override a differing authoritative fingerprint.
    other.report!.comparison = structuredClone(source.report!.comparison);
    expect(
      comparisonDifferences([source, other]).map((row) => row.field),
    ).toEqual(["comparison_sha256"]);
    expect(() =>
      comparisonDifferences([{ ...source, report: null }]),
    ).toThrow();
  });
  it("retains exact pinned settings and uint64 seeds on shared-setting reruns", () => {
    const exact = {
      ...source,
      inputs_canonical_json: source.inputs_canonical_json.replace(
        '"random_seed":42',
        '"random_seed":18446744073709551615',
      ),
    };
    const target = "77777777-7777-4777-8777-777777777777";
    const body = fairRerunBody(exact, target);
    expect(body).toContain('"random_seed":18446744073709551615');
    expect(body).toContain(`"strategy_version_id":"${target}"`);
    expect(JSON.parse(body)).toEqual({
      ...JSON.parse(exact.inputs_canonical_json),
      strategy_version_id: target,
    });
    expect(source.inputs.strategy_version_id).not.toBe(target);
  });
  it("changes exactly one permitted rule and leaves original complete config intact", () => {
    const original = structuredClone(source.strategy_config);
    const edited = oneRuleConfig(original, "0.10");
    expect(configDifferences(original, edited)).toEqual([
      {
        field: "portfolio.max_position_weight",
        before: original.portfolio.max_position_weight,
        after: "0.10",
      },
    ]);
    expect(original).toEqual(source.strategy_config);
    expect(() =>
      oneRuleConfig(original, original.portfolio.max_position_weight),
    ).toThrow();
    for (const invalid of ["0", "1.1", "-0.1", "NaN", "1e-1", "0.1234567"])
      expect(() => oneRuleConfig(original, invalid)).toThrow();
    const fullFork = structuredClone(edited);
    fullFork.signals.require_positive_trend =
      !original.signals.require_positive_trend;
    expect(configDifferences(original, fullFork)).toHaveLength(2);
  });
});
