import type { components } from "../../api/generated/schema";

type Reasons = components["schemas"]["ExperimentDetailV1"]["warnings"];
const benchmarkTerms = new Set([
  "BENCHMARK_ADJUSTED_TOTAL_RETURN_APPROXIMATION",
  "BENCHMARK_DIVIDEND_RECOGNITION_DIFFERS",
  "BENCHMARK_FRICTION_FREE_FULLY_INVESTED",
  "BENCHMARK_INITIAL_CLOSE_DIFFERS_FROM_NEXT_OPEN",
]);
const explanations: Record<string, string> = {
  INSUFFICIENT_HOLDOUT:
    "The holdout has fewer than 252 sessions. Treat it as a short sample.",
  LIMITED_WARMUP:
    "Initial history is shorter than the strategy requires; early candidates may be excluded.",
  HOLDOUT_REPEATED_SELECTION_CAVEAT:
    "Repeated selection after viewing holdout results weakens independent evidence.",
  ZERO_CASH_RETURN: "Cash earns 0% in this simulation.",
};
export function ExperimentWarnings({ warnings }: { warnings: Reasons }) {
  if (!warnings.length) return null;
  return (
    <div className="notice" role="note">
      <strong>Data and method limits</strong>
      <ul>
        {warnings
          .filter((code) => !benchmarkTerms.has(code))
          .map((code) => (
            <li key={code}>
              {code === "SYNTHETIC_DATA_ONLY" ? (
                <>
                  <code>SYNTHETIC_DATA_ONLY</code> · Authored prices, not real
                  investment performance.
                </>
              ) : (
                (explanations[code] ??
                `Source warning: ${code.replaceAll("_", " ").toLowerCase()}.`)
              )}
            </li>
          ))}
        {warnings.some((code) => benchmarkTerms.has(code)) && (
          <li>
            SPY assumes adjusted prices, full investment and no trading costs.
            Its initial-close and dividend conventions differ from the strategy.
          </li>
        )}
      </ul>
      <details>
        <summary>Exact warning codes</summary>
        <ul>
          {warnings
            .filter((code) => code !== "SYNTHETIC_DATA_ONLY")
            .map((code) => (
              <li key={code}>
                <code>{code}</code>
              </li>
            ))}
        </ul>
      </details>
    </div>
  );
}
