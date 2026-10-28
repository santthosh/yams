# ADR-002: Provider normalization and data rights

Status: Accepted for implementation under #13; runtime verification remains with consumers. Date: 2026-10-27. Scope: foundation contracts, not a live-feed delivery.

## Decision and evidence

Use a replaceable adapter with an offline synthetic baseline. The [dated provider evidence](../data-provider-evidence.md) compares broad directory, issuer-data and price interfaces and records unsupported capabilities and rights. Optional Yahoo/yfinance research input is conditional on verified terms and capability; it is not required for offline startup. Do not redistribute external data without evidenced rights. Public images and fixtures contain code and authored synthetic data only (Q06/Q11).

## Identity and normalization

1. Assign an immutable internal `asset_id`; retain provider-native identifier, venue/MIC, currency and effective-dated aliases. `{venue}:{symbol}` is the display/selection key at a specified time, not a permanent identity. A reused ticker or overlapping ambiguous alias is quarantined until resolved; never join by ticker alone. Venue changes require evidenced identity mapping, not automatic merging.
2. Keep original source payload hash, source schema/version, retrieval timestamp and normalization version. Store daily session dates separately from UTC timestamps. Match sessions to the pinned ADR-001 calendar; do not interpret midnight provider labels as publication times. Reject unsupported currency/instrument/venue for the initial USD ordinary-equity strategy.
3. Bars contain positive finite decimal OHLC/adjusted close, nonnegative integral volume, declared price and volume adjustment bases, and availability metadata. Validate low <= open/close <= high and low <= high. Missing values remain missing; do not forward-fill OHLCV or convert errors into zero. Statistical inputs must be finite. Preserve provider precision until the consuming contract applies rounding.
4. Identical duplicates for the same source/asset/session/revision deduplicate with an audit count. Conflicting duplicates quarantine that bar; do not choose last-row-wins. Extreme discontinuities require an explained action or explicit quality exclusion, not guessed repair. Corrections create a new immutable snapshot and retain their later availability.
5. Sector must be supplied with source and availability. An explicit `Unknown` classification is valid and shares one capped bucket; an absent field is invalid candidate metadata, not silently converted into `Unknown`. Missing sector does not erase an existing holding.

## Prices, actions and accounting

Keep raw as-traded OHLC and adjusted-close return series as separate named bases. `auto_adjust=False` alone is not proof that a vendor's historical OHLC is raw. An adapter must prove the basis, action completeness and conversion method for its coverage before raw execution is enabled. Do not reverse-engineer raw opens by multiplying an unexplained adjustment factor. Unproven bars can be retained as provider observations, but cannot masquerade as validated raw bars.

Under [ADR-001](0001-execution-semantics.md), a split multiplies units by its ratio and divides unit basis before the effective session; retain total basis. Require an evidenced effective date, ratio and event identity. Dividends require currency, per-share amount, entitlement evidence and reliable payable/recognition date. An ex-date alone is not an authorized cash-posting date. Missing dates or entitlement leave the event unresolved and the affected accounting run incomplete; no invented zero dividend, liquidation or cash credit. Event replay is idempotent. Fractional precision/cash-in-lieu cases without a supported policy are explicitly unsupported rather than rounded away.

Adjusted-close ratios are used only for compatible return/feature calculations and the disclosed benchmark approximation. Never add dividends again to an adjusted total-return series. Raw holdings valuation plus explicit action cash is a separate accounting path. If reliable raw/action coverage is missing, allow labeled data inspection and supported diagnostics, but block affected execution and claims of a complete accounting backtest. The fixture path supplies known action facts and remains independently testable.

## Availability, membership and failures

`available_at` identifies when evidence could be used; `ingested_at` identifies local receipt. Preserve provider `published_at` only when documented and reliable. Without it use first observed ingestion as a conservative availability proxy, with `availability_basis=observed`; never backdate to session close. For synthetic replay, declare fixture availability explicitly. Actual live use requires both available evidence and local ingestion by the decision cutoff. A historical download observed today cannot prove what was known years ago. Strict historical decisions exclude evidence later than their cutoff; unavailable chronology must be reported rather than relaxed to produce results.

Select a broad permitted directory, snapshot its membership and rules, then apply the strategy eligibility filters. Current-only membership carries `SURVIVORSHIP_BIAS_RISK`; it does not authorize presenting today's constituents or classifications as known at an earlier cutoff. Retrospective current-universe inspection must disclose its limitation and cannot claim point-in-time validity. Historical membership is supported only when effective intervals and availability are evidenced. A symbol disappearing from a directory or an HTTP 404 is not a verified delisting. Preserve prior identity/history, mark coverage unknown and block unsupported current trading. A confirmed delisting closes the membership interval; never fabricate a liquidation price or erase holdings.

Expected sessions come from the pinned calendar, including holidays and early closes. Missing scheduled sessions are quality gaps, not zero-volume holidays. A missing required feature window excludes the candidate; a missing eligible execution open stays pending as ADR-001 specifies. Stale/partial data cannot generate new current fills. Provider timeout, throttling, parse error, missing fields or denied access fails the refresh with a structured reason; retain the prior immutable snapshot and expose its age. Never silently substitute fixtures for live data or publish a partial refresh as complete. Snapshot publication/hashing is specified by ADR-007 (#18).

## Independent synthetic acceptance traces

These are authored inputs, not downloaded observations. #21 materializes them; #29/#30 implement adapter validation. Exact identity/count/cash assertions have zero tolerance; return comparisons use the consuming numerical contract.

| Fixture | Input and independently expected result |
|---|---|
| FIX-02 identity | `XNYS:DEMO` and `XNAS:DEMO` have different internal IDs. A provider alias without venue matching both is rejected as ambiguous. A later reuse of `XNYS:DEMO` by a different issuer creates another ID with nonoverlapping alias intervals. |
| FIX-02 quality | Two identical bars yield one bar plus duplicate count 1; differing closes for the same revision produce a conflict and no eligible bar. Missing sector excludes the candidate; explicit `Unknown` remains eligible for the shared sector cap if all other filters pass. |
| FIX-05 split | Two units with unit basis $100 become four units with unit basis $50 on an evidenced 2:1 split: total basis remains $200. Raw price $100 before/$50 after gives unchanged $200 value, not a 50% loss. |
| FIX-05 dividend | Four entitled units × $1.25 payable dividend = $5 cash exactly once. If raw value falls from $200 to $195, value plus cash remains $200. An independently supplied adjusted-close pair 50/50 has return 0; adding $5 to that return path would double count. Without payable date the $5 remains unresolved, not posted. |
| FIX-06 chronology | A bar observed at 21:05Z is excluded at cutoff 21:00Z even if its session closed earlier. A revised bar observed the following day cannot replace the prior snapshot in an earlier decision. Missing next open leaves the order pending. |
| FIX-06 calendar | Reference schedule: NYSE 2026-11-26 is a holiday and 2026-11-27 closes at 13:00 America/New_York, per the official calendar. A missing bar on the former is not a gap; a missing completed-session bar on the latter is a gap. Pin schedule and timezone versions in the implemented fixture. |
| Provider failures | Timeout/429/404 or malformed payload leaves the old snapshot hash unchanged, records failure and exposes stale status. A 404 cannot synthesize a delisting or zero-price bar. |

## Handoff and limits

#18 owns immutable manifests and capability lineage; #20 owns versioned schemas; #21 owns executable synthetic fixtures; #29/#30 own later provider/universe implementation; #65 owns stronger historical/free-source coverage. Foundation ships contracts and offline metadata, not a claim that external research data now meets this contract. Runtime, provider-access and redistribution checks have not been run by this documentation decision.


Approved #29 decision (2026-10-27): flag and exclude unexplained one-session adjusted-close moves strictly greater than 50% in either direction. Exactly ±50% remains within this guard. Compare consecutive pinned calendar sessions with visible evidence using Decimal arithmetic; do not fill gaps or infer price repairs. A split alone does not explain a jump in an already adjusted series.
