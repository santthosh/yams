import type { components } from "../../api/generated/schema";

type Config = components["schemas"]["StrategyConfigV1"];
export type Draft = Record<string, string>;
export type Field = {
  path: string;
  label: string;
  group: string;
  type: "text" | "number" | "checkbox";
  min?: string;
  max?: string;
  step?: string;
};
export class DraftError extends Error {
  constructor(
    public path: string,
    message: string,
  ) {
    super(message);
  }
}
export function fieldsFor(config: Config): Field[] {
  const count = (
    path: string,
    label: string,
    group: string,
    min: number,
    max: number,
  ): Field => ({
    path,
    label,
    group,
    type: "number",
    min: String(min),
    max: String(max),
    step: "1",
  });
  const fraction = (
    path: string,
    label: string,
    group: string,
    min: string,
    max = "1",
  ): Field => ({
    path,
    label,
    group,
    type: "number",
    min,
    max,
    step: "0.000001",
  });
  const money = (path: string, label: string, group: string): Field => ({
    path,
    label,
    group,
    type: "number",
    min: "0",
    max: "999999999999.99",
    step: "0.01",
  });
  const signals: Field[] = [
    count(
      "signals.volatility_sessions",
      "Volatility window (returns)",
      "Signals",
      2,
      2519,
    ),
    count(
      "signals.trend_sma_sessions",
      "Trend average (sessions)",
      "Signals",
      1,
      2520,
    ),
    {
      path: "signals.require_positive_trend",
      label: "Require a positive trend",
      group: "Signals",
      type: "checkbox",
    },
  ];
  if (config.signals.kind === "risk_adjusted_momentum")
    signals.push(
      count(
        "signals.momentum_long_sessions",
        "Long momentum (sessions)",
        "Signals",
        1,
        2519,
      ),
      count(
        "signals.momentum_short_sessions",
        "Short momentum (sessions)",
        "Signals",
        1,
        2519,
      ),
      fraction(
        "signals.z_score_weights.momentum_long",
        "Long momentum score weight",
        "Signals",
        "0",
      ),
      fraction(
        "signals.z_score_weights.momentum_short",
        "Short momentum score weight",
        "Signals",
        "0",
      ),
      fraction(
        "signals.z_score_weights.volatility_penalty",
        "Volatility score penalty",
        "Signals",
        "-1",
        "0",
      ),
    );
  if (config.signals.kind === "mean_reversion")
    signals.push(
      count(
        "signals.mean_reversion_sessions",
        "Mean-reversion average (sessions)",
        "Signals",
        2,
        2520,
      ),
    );
  return [
    {
      path: "display_name",
      label: "Rule display name",
      group: "Strategy label",
      type: "text",
    },
    money("universe.min_price_usd", "Minimum share price (USD)", "Universe"),
    money(
      "universe.min_median_dollar_volume_usd",
      "Minimum median daily volume (USD)",
      "Universe",
    ),
    count(
      "universe.min_history_sessions",
      "Required history (sessions)",
      "Universe",
      252,
      2520,
    ),
    ...signals,
    count(
      "portfolio.max_positions",
      "Maximum positions",
      "Allocation and risk",
      1,
      100,
    ),
    fraction(
      "portfolio.max_position_weight",
      "Position cap (fraction)",
      "Allocation and risk",
      "0.000001",
    ),
    fraction(
      "portfolio.max_sector_weight",
      "Sector cap (fraction)",
      "Allocation and risk",
      "0.000001",
    ),
    fraction(
      "portfolio.min_cash_weight",
      "Cash floor (fraction)",
      "Allocation and risk",
      "0",
    ),
    fraction(
      "portfolio.rebalance_band_absolute_weight",
      "Rebalance band (fraction)",
      "Allocation and risk",
      "0",
    ),
    money(
      "portfolio.min_trade_usd",
      "Minimum trade (USD)",
      "Allocation and risk",
    ),
  ];
}
function leaf(config: unknown, path: string): unknown {
  return path
    .split(".")
    .reduce<unknown>(
      (value, key) =>
        value && typeof value === "object"
          ? (value as Record<string, unknown>)[key]
          : undefined,
      config,
    );
}
export function initialDraft(config: Config): Draft {
  return Object.fromEntries(
    fieldsFor(config).map((field) => [
      field.path,
      String(leaf(config, field.path)),
    ]),
  );
}
export function validName(value: string): boolean {
  const trimmed = value.replace(/^\p{White_Space}+|\p{White_Space}+$/gu, "");
  return (
    Array.from(trimmed).length >= 1 &&
    Array.from(trimmed).length <= 120 &&
    !/[\p{Cc}\p{Cs}]/u.test(trimmed)
  );
}
export function configFromDraft(source: Config, draft: Draft): Config {
  const editable = new Map(
    fieldsFor(source).map((field) => [field.path, field]),
  );
  function update<T>(value: T, path: string): T {
    const field = editable.get(path);
    const text = draft[path];
    if (field && text !== undefined) {
      if (path === "display_name" && !validName(text))
        throw new DraftError(
          path,
          "Use a rule name of 1–120 characters without control characters.",
        );
      if (field.type === "checkbox") {
        if (!["true", "false"].includes(text))
          throw new DraftError(path, "Choose a valid trend setting.");
        return (text === "true") as T;
      }
      if (field.type === "number") {
        const integer = field.step === "1";
        const decimal = /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/;
        if (!(integer ? /^(?:0|[1-9]\d*)$/ : decimal).test(text))
          throw new DraftError(
            path,
            `Use a plain ${integer ? "whole" : "decimal"} number for ${field.label.toLowerCase()}.`,
          );
        // Only bounded integer/statistical JSON numbers are converted. Money and
        // risk weights retain their original decimal lexemes for backend validation.
        if (typeof value === "number") {
          const number = Number(text);
          if (
            !Number.isFinite(number) ||
            (integer && !Number.isSafeInteger(number)) ||
            (!integer && (text.split(".")[1]?.length ?? 0) > 6)
          )
            throw new DraftError(
              path,
              "Use a finite value with at most six fractional digits.",
            );
          return number as T;
        }
      }
      return text as T;
    }
    if (value !== null && typeof value === "object") {
      if (Array.isArray(value))
        throw new Error("Unsupported strategy structure");
      return Object.fromEntries(
        Object.entries(value).map(([key, child]) => [
          key,
          update(child, path ? `${path}.${key}` : key),
        ]),
      ) as T;
    }
    return value;
  }
  return update(source, "");
}
function normalized(value: unknown, field: Field): unknown {
  if (typeof value !== "string") return value;
  if (field.type === "number" && /^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(value))
    return value.includes(".")
      ? value.replace(/0+$/, "").replace(/\.$/, "")
      : value;
  return value.replace(/^\p{White_Space}+|\p{White_Space}+$/gu, "");
}
export function changes(
  source: Config,
  edited: Config,
): { label: string; before: string; after: string }[] {
  return fieldsFor(source).flatMap((field) => {
    const before = leaf(source, field.path),
      after = leaf(edited, field.path);
    return normalized(before, field) === normalized(after, field)
      ? []
      : [{ label: field.label, before: String(before), after: String(after) }];
  });
}
export const familyText = {
  risk_adjusted_momentum:
    "Momentum favors relative strength; trends can reverse.",
  mean_reversion:
    "Mean reversion favors distance below a short moving average; weakness can continue.",
  low_volatility:
    "Low volatility favors historical stability; future losses can still be large.",
} satisfies Record<Config["signals"]["kind"], string>;
