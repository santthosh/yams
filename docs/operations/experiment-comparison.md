# Experiment comparison and one-rule challenge (planned 0.0.3, #43)

Open `/lab/compare` from navigation or a report. Select two to four completed
experiments from bounded history; load more pages explicitly. The shareable
`?ids=<source>,<target>[,...]` URL opens immutable identities directly, even when
those reports are outside the loaded history page. Missing, failed, cancelled and
running reports have explicit states and report links; refresh after completion.
A history/storage error is distinct from an empty result.

## Fair comparison

The backend's stored `comparison_sha256` and complete comparison terms own
alignment. The UI displays exact incompatible fields, including dates/session
sequence, snapshot, universe, capital, costs, benchmark, source, split and engine
policies. It withholds curves and metric sorting while terms differ. Strategy
parameters are the controlled experimental difference and are not alignment terms.

Reference dates, universe, capital, costs, benchmark, split, source and exact seed
remain visible. Expand each original report's evidence for complete policies,
configuration and fingerprints. Source modes are explicit; current historical
runs are `SYNTHETIC_DATA_ONLY`, and real providers remain diagnostic-only.

**Rerun all with reference settings** explicitly creates a fresh run for each
selected immutable strategy version using the reference's snapshot, dates,
capital, benchmark, execution policy, split and seed. It does not edit originals
or tune parameters. The UI retains accepted jobs if a later submission fails.
An uncertain response disables duplicate submissions and directs the operator to
history. Known rejected requests retain the accepted subset for an explicit retry.

Sharing request settings cannot rewrite a strategy's universe or the engine that
produced an older report. Create compatible versions or rerun all versions under
the current engine as needed; only newly completed matching backend fingerprints
establish comparability. No success is inferred from merely queuing jobs.

## Inspect results

For aligned reports, choose full, development or holdout metrics and an explicitly
named sort metric/direction. Undefined metrics retain reasons and sort last;
return sorting does not select a prospective investment. Drawdown, Sharpe,
turnover, fees/slippage and cash remain beside return. Cash is labeled by the
loaded original close; it is not a selected-period average.

The lazy-loaded local Plotly chart shows original-date portfolio NAVs plus the
reference SPY and zero-yield cash curves. Money/exposure strings and statistics
come from backend artifacts; the browser performs no authoritative portfolio,
return, drawdown or allocation calculation. Exact keyboard-scrollable session
and execution evidence remains available. Pages are bounded 25 rows; explicit
load-more controls retain cursor terms. Partial curves/cash rows are labeled;
period selection does not recompute the original full-session curve. Chart failure
retains tables, empty samples are explicit and unavailable benchmark points remain
gaps. The individual report links retain complete trade evidence.

SPY is the adjusted-close, friction-free, fully invested approximation defined in
ADR-013; strategy raw execution, dividend cash timing and next-open friction differ.
Short synthetic examples and annualized metrics are not forecasts. Repeated
parameter tuning and holdout selection weaken independence; the warning remains
visible throughout comparison and challenge.

## Controlled challenge and traceability

**Change one rule** supports the maximum single-position weight. Enter a different
positive decimal weight up to 1 with at most six fractional digits (0.10 means 10%),
and a new strategy name. Review the before/after field. Publish explicitly,
then submit the challenge with the source experiment's exact settings. The backend
validates the complete configuration and can reject infeasible/invalid rules.
No other configuration field, original version or original result is rewritten.

The published immutable fork is retained if run submission fails; uncertain
publication/submission directs the operator to inspect stored history before
retrying. Source/target experiment and version identities and the stored-config
diff make the comparison trace reproducible. The comparison URL retains both
experiment identities across restart. This uses the existing API, which has no
parent-version field; it adds no new persistence lineage or comparison endpoint.
A pair with multiple stored configuration differences is labeled a full fork,
not a one-rule challenge. Other edits belong in the full Strategy Lab editor.

Canonical request serialization preserves the complete uint64 seed range through
challenge and common-setting reruns. The browser never reconstructs a seed from
its potentially rounded JSON number. See [exact experiment reruns](experiment-lab.md).

No backend financial method, cost default, provider capability, schema, migration,
account, order or durable paper fill is introduced. This source capability alone
does not claim a published0.0.3 release.
