# Decision Center and actionable dashboard

Source increment for issue #52, planned 0.0.5. The published 0.0.4 bundle remains unchanged;
#53 owns the integrated core/native release gate. Everything here is Paper only.

1. In Settings & data, explicitly load offline fixture data. Creating the workspace
   alone does not register a financial snapshot or invent accounts.
2. Create a paper account at `/portfolios` (default synthetic $1,000 USD and published
   momentum version). Open its Decision Center at `/portfolios/{id}/decisions`.
3. Review actual posted holdings and select a pinned as-of date. The server suggests
   the earliest covered session with252 calendar return intervals and supported90-day
   calendar horizon, without inspecting performance. Calendar support is not complete
   price evidence: the worker still validates prices, features, eligibility and history.
   Submitting a later synthetic session explicitly observes that cutoff without trading;
   the durable replay clock cannot rewind. Background scheduling never advances it.
4. Generate a real cancellable review job or inspect an original cached decision.
   Targets, constraints, explanations, candidate exclusions, quantities, costs and
   forecasts all come from the shared engine. No browser allocation/ledger math.
5. Inspect proposed vs hold P10/P50/P90 returns, loss probability and median ending
   money over 90 calendar days (not 90 trading sessions). Common-shock historical bootstrap
   scenarios assume constant weights, zero cash yield and one estimated upfront cost.
   They are not calibrated predictions or guaranteed performance. Missing history,
   stale marks and unavailable forecasts keep explicit reasons/null values.
6. Review the confirmation, including portfolio/revision/version/as-of, estimated
   quantities/costs and indicative eligible opening. Authorize paper orders explicitly.
   The opening is not reserved by the readonly preview; approval revalidates state.
   Preview and approval do not mutate cash/holdings. HOLD/cash-only decisions with no
   executable orders stay inspectable and cannot create an empty batch.
7. Inspect real pending/partial/filled quantities. Synthetic replay requires an
   explicit next-close action; unavailable original opening bars can keep orders
   pending. Only the worker posts durable fills. Refresh posted state to see them.
   Cancel remaining orders to close outstanding intent while preserving posted fills.

The dashboard reads actual accounts, valuation/provenance, pending batch and monthly
review status. Unknown data/next-due/worker observations remain unknown. Monitoring
only runs while Docker is active; observed gaps are not exact shutdown times. The
first 25 accounts are summarized, with a link to the paginated account browser.

## Retry and evidence

Review and approval keys/bodies are stored in browser local storage before their
first POST. Storage failure prevents submitting a replacement request. Double-click
has an immediate in-flight guard. An uncertain approval is reconciled using readonly
`apply-result` and its original key before any retry. Reload retains the key and can
recover an accepted pending batch. Changed inputs never silently reuse a key. Fixture
steps likewise preserve their original key until the accepted response is received;
after acknowledgement, a later explicit action may create the next step once no job
is active. Cancellation/dismissal are target-idempotent existing server operations.

Original decision/history/scenario artifacts survive later approvals, fills, source
changes and restart. The UI shows current eligibility separately. Exact money/shares
are formatted from decimal strings, never binary-float ledger calculations. Canonical
inputs preserve large seeds without reserializing them through browser numbers.

Additive readonly transports: `GET /portfolios/{id}/decision-inputs` and
`GET /recommendations/{id}/approval-preview`. Existing admission, forecast, paper
control and schedule contracts remain authoritative. No migration or provider token
is needed. Real provider feeds remain diagnostic-only for accounting.
