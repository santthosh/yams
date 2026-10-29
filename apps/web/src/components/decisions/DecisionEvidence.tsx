import type { components } from "../../api/generated/schema";
import { Card, Money, Quantity, ReturnPercent } from "../evidence";
type S = components["schemas"];
const percent = (value: number | null | undefined) =>
  value == null
    ? "Unavailable"
    : new Intl.NumberFormat("en-US", {
        style: "percent",
        maximumFractionDigits: 2,
      }).format(value);
export function DecisionEvidence({
  decision: d,
}: {
  decision: S["RecommendationDetailV1"];
}) {
  const f = d.forecast;
  return (
    <>
      <Card title="2. Target allocation and risk">
        <p>
          <strong>{d.summary_action.replaceAll("_", " ")}</strong> · Cash target{" "}
          <ReturnPercent value={d.cash_target_weight} />
        </p>
        <p>
          Estimated trade costs{" "}
          <Money value={d.estimated_total_trade_cost_usd} />. Quantities and
          costs are estimates; only posted fills change holdings.
        </p>
        <p>
          Position cap{" "}
          <ReturnPercent
            value={d.strategy_config.portfolio.max_position_weight}
          />
        </p>
        <p>
          Sector cap{" "}
          <ReturnPercent
            value={d.strategy_config.portfolio.max_sector_weight}
          />{" "}
          · Minimum cash{" "}
          <ReturnPercent value={d.strategy_config.portfolio.min_cash_weight} />
        </p>
        <details>
          <summary>Complete target weights</summary>
          <ul>
            {d.target_weights.map((t) => (
              <li key={t.asset_id}>
                {t.asset_id}: <ReturnPercent value={t.weight} /> ·{" "}
                {t.reason_codes.join(", ")}
              </li>
            ))}
            <li>
              Cash: <ReturnPercent value={d.cash_target_weight} />
            </li>
          </ul>
        </details>
        <div
          className="table-scroll"
          role="region"
          aria-label="Proposed actions"
          tabIndex={0}
        >
          <table>
            <caption>Current → target, supplied by the shared engine</caption>
            <thead>
              <tr>
                <th scope="col">Asset</th>
                <th scope="col">Action</th>
                <th scope="col">Current</th>
                <th scope="col">Target</th>
                <th scope="col">Estimated shares</th>
                <th scope="col">Estimated notional</th>
                <th scope="col">Why</th>
              </tr>
            </thead>
            <tbody>
              {d.actions.map((a) => (
                <tr key={a.asset_id}>
                  <th scope="row">{a.asset_id}</th>
                  <td>{a.side}</td>
                  <td>
                    <ReturnPercent value={a.current_weight} />
                  </td>
                  <td>
                    <ReturnPercent value={a.target_weight} />
                  </td>
                  <td>
                    <Quantity value={a.estimated_quantity} />
                  </td>
                  <td>
                    <Money value={a.estimated_notional_usd} />
                  </td>
                  <td>
                    {a.explanation}
                    <p>{a.reason_codes.join(", ")}</p>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!d.actions.length && (
          <p>
            No security actions. The complete cash allocation remains visible
            above.
          </p>
        )}
        <details>
          <summary>Inspect candidate evidence and exclusions</summary>
          {d.candidates.map((c) => (
            <article key={c.asset_id}>
              <h3>{c.asset_id}</h3>
              <p>
                Score {c.score ?? "Unavailable"} ·{" "}
                {c.exclusion_reasons.join(", ") || "Eligible"}
              </p>
              <ul>
                {c.features.map((v) => (
                  <li key={v.name}>
                    {v.name}: {v.value ?? v.unavailable_reason}
                  </li>
                ))}
              </ul>
              <p>
                Contributions:{" "}
                {c.contributions
                  .map((v) => `${v.name}: ${v.value ?? v.unavailable_reason}`)
                  .join("; ")}
              </p>
            </article>
          ))}
        </details>
      </Card>
      <Card title="3. Historical scenarios · 90 calendar days">
        <p>
          Historical scenarios are not calibrated predictions or guaranteed
          returns. Both allocations use common shock paths, constant weights and
          zero cash yield. Proposed upfront costs are estimated once.
        </p>
        {!f && (
          <p role="status">
            Scenario job {d.forecast_job.status}. No numerical outcome is
            available yet.
          </p>
        )}
        {f && (
          <>
            <p>
              {f.horizon_calendar_days} calendar days ·{" "}
              {f.horizon_trading_sessions ?? "Unavailable"} pinned trading
              sessions · End {f.horizon_end_at ?? "Unavailable"}
            </p>
            {f.status === "unavailable" ? (
              <p className="notice notice-warning" role="status">
                Forecast unavailable:{" "}
                {f.unavailable_reason?.replaceAll("_", " ")}. No zero return is
                substituted.
              </p>
            ) : (
              <>
                <p>
                  Initial value <Money value={f.initial_value_usd} /> · Proposed
                  cost <Money value={f.proposed_allocation.upfront_cost_usd} />{" "}
                  · Hold cost{" "}
                  <Money value={f.current_allocation.upfront_cost_usd} />
                </p>
                <div
                  className="table-scroll"
                  role="region"
                  aria-label="Scenario comparison"
                  tabIndex={0}
                >
                  <table>
                    <caption>
                      Shared-assumption historical scenario comparison
                    </caption>
                    <thead>
                      <tr>
                        <th scope="col">Allocation</th>
                        <th scope="col">P10 return</th>
                        <th scope="col">P50 return</th>
                        <th scope="col">P90 return</th>
                        <th scope="col">Loss probability</th>
                        <th scope="col">Median ending value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[
                        ["Hold unchanged", f.hold_unchanged],
                        ["Proposed", f.proposed],
                      ].map(([label, outcome]) => {
                        const o = outcome as S["ForecastOutcome"] | null;
                        return (
                          <tr key={label as string}>
                            <th scope="row">{label as string}</th>
                            <td>{percent(o?.p10_return_fraction)}</td>
                            <td>{percent(o?.median_return_fraction)}</td>
                            <td>{percent(o?.p90_return_fraction)}</td>
                            <td>{percent(o?.probability_of_loss)}</td>
                            <td>
                              <Money
                                value={o?.median_ending_value_usd ?? null}
                              />
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <p>
                  Proposed minus hold median return:{" "}
                  {percent(f.median_return_delta_fraction)} (server comparison).
                </p>
              </>
            )}
            <details>
              <summary>Scenario assumptions and reproducibility</summary>
              <p>
                {f.simulation_count} simulations · {f.lookback_sessions} return
                sessions · {f.block_length_sessions}-session blocks · Seed from
                original canonical request below
              </p>
              <p>{f.limitations.join(" · ")}</p>
              <p>
                Fingerprint <code>{f.fingerprint ?? "Unavailable"}</code>
              </p>
            </details>
          </>
        )}
      </Card>
      <Card title="Original decision evidence">
        <p>
          Version <code>{d.strategy_version_id}</code> · As-of {d.as_of_session}{" "}
          · Cutoff {d.decision_cutoff_utc}
        </p>
        <p>
          Actual computation {d.computed_at} · Portfolio revision{" "}
          {d.portfolio_revision} · Engine <code>{d.engine_version}</code>
        </p>
        <p>
          Snapshot <code>{d.snapshot_id}</code> · SHA-256{" "}
          <code>{d.snapshot_sha256}</code>
        </p>
        <details>
          <summary>Canonical original inputs</summary>
          <pre className="decision-json">{d.inputs_canonical_json}</pre>
          <pre className="decision-json">
            {d.forecast_inputs_canonical_json}
          </pre>
        </details>
      </Card>
    </>
  );
}
