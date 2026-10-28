import type { components } from "../../api/generated/schema";
import { serializeExperiment, storedSeed } from "./inputs";

type S = components["schemas"];
export type Run = S["ExperimentDetailV1"];
export type Point = S["ExperimentCurvePointV1"];
export type Difference = { field: string; values: string[] };
export function stableValue(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableValue).join(",")}]`;
  if (value !== null && typeof value === "object")
    return `{${Object.entries(value)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, child]) => `${JSON.stringify(key)}:${stableValue(child)}`)
      .join(",")}}`;
  return JSON.stringify(value) ?? "Unavailable";
}
export function comparisonDifferences(runs: Run[]): Difference[] {
  if (
    !runs.length ||
    runs.some((run) => run.status !== "completed" || !run.report)
  )
    throw new Error("Completed reports are required");
  const terms = runs.map((run) => run.report!.comparison);
  const differences = Object.keys(terms[0])
    .sort()
    .flatMap((field) => {
      const values = terms.map((term) =>
        stableValue(term[field as keyof typeof term]),
      );
      return new Set(values).size === 1 ? [] : [{ field, values }];
    });
  // Matching visible fields cannot overrule the backend's pinned fingerprint.
  if (
    !differences.length &&
    new Set(runs.map((run) => run.report!.comparison_sha256)).size !== 1
  )
    differences.push({
      field: "comparison_sha256",
      values: runs.map((run) => run.report!.comparison_sha256),
    });
  return differences;
}
export function fairRerunBody(
  reference: Run,
  strategyVersionId: string,
): string {
  return serializeExperiment(
    { ...reference.inputs, strategy_version_id: strategyVersionId },
    storedSeed(reference),
  );
}
export function configDifferences(
  before: S["StrategyConfigV1"],
  after: S["StrategyConfigV1"],
): { field: string; before: string; after: string }[] {
  function visit(
    a: unknown,
    b: unknown,
    field: string,
  ): ReturnType<typeof configDifferences> {
    if (
      a !== null &&
      b !== null &&
      typeof a === "object" &&
      typeof b === "object" &&
      !Array.isArray(a) &&
      !Array.isArray(b)
    ) {
      const left = a as Record<string, unknown>,
        right = b as Record<string, unknown>;
      return [...new Set([...Object.keys(left), ...Object.keys(right)])]
        .sort()
        .flatMap((key) =>
          visit(left[key], right[key], field ? `${field}.${key}` : key),
        );
    }
    return stableValue(a) === stableValue(b)
      ? []
      : [
          {
            field,
            before: typeof a === "string" ? a : stableValue(a),
            after: typeof b === "string" ? b : stableValue(b),
          },
        ];
  }
  return visit(before, after, "");
}
export function oneRuleConfig(
  source: S["StrategyConfigV1"],
  cap: string,
): S["StrategyConfigV1"] {
  if (
    !/^(?:0\.\d{1,6}|1(?:\.0{1,6})?)$/.test(cap) ||
    BigInt(cap.replace(".", "")) === 0n
  )
    throw new Error(
      "Use a positive maximum position weight up to1, with at most six decimal places.",
    );
  // Validate and compare decimal lexemes without binary financial arithmetic.
  const normalize = (value: string) =>
    value.includes(".") ? value.replace(/0+$/, "").replace(/\.$/, "") : value;
  if (normalize(cap) === normalize(source.portfolio.max_position_weight))
    throw new Error(
      "Change the maximum position weight to create a one-rule challenge.",
    );
  return {
    ...source,
    portfolio: { ...source.portfolio, max_position_weight: cap },
  };
}
export const sortMetrics = {
  cumulative_return_fraction: { label: "cumulative return", ascending: false },
  max_drawdown_fraction: { label: "maximum drawdown", ascending: true },
  sharpe_ratio: { label: "Sharpe ratio", ascending: false },
  turnover_fraction: { label: "turnover", ascending: true },
} as const;
export type SortMetric = keyof typeof sortMetrics;
export type Period = keyof S["MetricsPeriods"];
export function sortRuns(
  runs: Run[],
  period: Period,
  metric: SortMetric,
): Run[] {
  return [...runs].sort((a, b) => {
    const left = a.report?.portfolio[period].metrics[metric].value ?? null;
    const right = b.report?.portfolio[period].metrics[metric].value ?? null;
    if (left === null || right === null)
      return left === right ? a.id.localeCompare(b.id) : left === null ? 1 : -1;
    return (
      (sortMetrics[metric].ascending ? left - right : right - left) ||
      a.id.localeCompare(b.id)
    );
  });
}
