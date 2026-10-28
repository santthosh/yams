# ADR-010: Bounded personal-use Tiingo diagnostics

Status: Proposed for review under #109; accepted when this decision PR merges.
Implements Q16 (real data required before0.0.2), Q17 (overnight cutoff) and the
user's configured free Tiingo token. The user authorized recommended routine
choices while continuing the complete0.0.2–0.0.5 goal. No paid service is selected.

## Evidence and boundary

[Tiingo EOD docs](https://www.tiingo.com/documentation/end-of-day) document separate
raw/adjusted prices and share volume. [General docs](https://www.tiingo.com/documentation/)
permit user-token software without redistribution. [Fundamental metadata](https://www.tiingo.com/documentation/fundamentals)
provides permanent identity, active/ADR and source sector fields; its availability
must be checked on the account, not inferred from an advertised plan. The user's
actual token returned valid metadata and291 historical daily bars, plus sector/
active/ADR metadata, in bounded local probes on2026-10-28. The source directory
contained109150 entries, including stocks/funds/ETFs, historical and reserved names.
This is access/schema evidence, not a completed integrated universe demonstration.

Use Tiingo only for locally displayed diagnostics whose required capabilities are
verified. Keep Yahoo's existing conditional inspection path compatible and blocked
where its bases remain unverified. No broker, subscription, SaaS/auth or portfolio
mutation is introduced. Raw execution prices alone do not establish complete action
accounting. No real provider data or credentials enter public fixtures/images.

## Deterministic, explicit universe scope

Define `tiingo_us_stock_hash20_v1`, a versioned budget-sampled research rule:

1. Pin the entire bounded source directory. Filter USD `Stock` rows on NASDAQ/NYSE
   whose declared coverage spans the requested history; accept only plain alphabetic
   tickers of1–5 characters for this initial identity mapping. Reject ambiguous/
   duplicate identities. This is a disclosed coverage restriction, not full US coverage.
2. Order candidate rows by SHA-256 of `tiingo_us_stock_hash20_v1:<venue>:<ticker>`
   with venue/ticker tie-breaks. Query metadata for a bounded first100 candidates;
   no return/score/performance information participates in ordering.
3. Require matching current supported EOD identity/coverage, active non-ADR primary
   stock metadata, permanent source ID and explicit nonempty source sector. Exclude
   known units, preferreds, warrants, depositary receipts and partnerships with
   reason/provenance; unresolved security classification remains unsupported.
   Never fill an absent sector with an invented `Unknown` value.
4. Select the first configured count (default20, hard cap20) qualifying identities
   in that fixed order. If the bound cannot supply the requested count, fail with
   explicit insufficient coverage. Persist rejected/selected identity evidence and
   the directory/metadata hashes. Every selected instrument must be fetched; a
   failed transport cannot silently shorten the cohort or publish a partial refresh.

The directory pool, eligibility checks, cap and rule version are visible in source
provenance and a `BUDGET_SAMPLED_UNIVERSE` warning. This is an explicit published
selection rule; ADR-002's prohibition on silent truncation remains binding. No
handpicked winners, hidden fallback symbols or tuning the seed to improve returns.
Use a stable namespaced asset ID derived from the provider's permanent security ID;
retain current venue/symbol as an effective-dated observed alias. Do not merge
recycled tickers or infer historical identity/membership from current metadata.

## Closed configuration, calendar and timing

Add `TiingoResearchConfigV1` alongside the existing Yahoo `ResearchConfig`:
`schema_version=1`, `provider="tiingo_eod"`, strict operator local-use assertion/
rights reference, `history_sessions` (default400, range252–2000), `max_assets`
(default20, range1–20), and optional covered `as_of_session`. No token, endpoint,
filesystem path, executable expression or arbitrary strategy code is accepted.
The provider discriminator selects server-owned code; existing source modes/routes
stay unchanged. Regenerate OpenAPI/TS when extending refresh payloads.

Generate a bounded XNYS regular-session calendar with pinned
`exchange_calendars==4.13.2`, record generator and actual timezone-rule identity,
then retain the history sessions plus the immediate next opening. Check independent
holiday/early-close/DST expectations against [NYSE's calendar](https://www.nyse.com/markets/hours-calendars).
A missing/unvalidated session is an error; do not infer weekdays from received bars.
Default as-of is the latest scheduled close that has elapsed; explicit future
sessions are invalid. Q17 cutoff remains next pinned opening minus1 hour, and
actual real-market evaluation requires that cutoff to have elapsed. Preparing an
overnight snapshot before the cutoff does not authorize executing the decision early.

## Normalization and supported claims

Retain raw response hashes/observed times, parse JSON numeric lexemes as Decimal,
and preserve source precision. Map raw OHLC/volume separately from `adjClose`;
never use adjusted volume for raw-share liquidity. Validate finite positive prices,
OHLC bounds, integral nonnegative volume, dates/session coverage, duplicates,
provider/identity alignment and declared adjustment semantics. Failed/invalid inputs
retain the prior registered usable snapshot; no repair, fabricated quote or zero.

For downloaded observations set `available_at=ingested_at=observed_at`,
`availability_basis=observed`, `published_at=null`. A represented session date is
not a publication timestamp. Source sector/alias/current membership are also
available only when observed. Label current-only membership/survivorship and
retrospective availability limitations. Historical downloads cannot populate an
earlier decision cutoff; initial data access is not point-in-time historical proof.

A verified diagnostic snapshot may have warning quality with raw price/share and
adjusted feature bases recorded, while its capability artifact explicitly declares
`supports_diagnostics=true`, `supports_complete_action_accounting=false`. Preserve
provider split/dividend observations; `divCash` ex-dates never invent payable dates
or entitlements. Unsupported raw/action/execution claims remain blocked for later
portfolio/backtest consumers. Their services must inspect capabilities, rather than
mistaking diagnostic support for approval to post financial effects.

## Bounded local operation and verification

Token comes only from worker-side `TIINGO_API_TOKEN`; no token in job/config/browser
or error text. Use fixed HTTPS hosts, Authorization headers, no redirects, bounded
responses/archive expansion and closed symbol parameters. Limit the initial refresh
to the declared cohort and account budget; handle401/403/429/timeouts safely. Typical
20-name refresh needs approximately41 API calls, subject to actual account limits;
this is a budget estimate, not throughput or entitlement proof. Do not evade quotas.

Default Compose remains offline/private. An explicit research override gives only
the worker outbound access and injects the user token; API/Postgres stay internal
and web remains loopback-only. Reuse supervised staging/fenced atomic publication,
registered discovery and the shared diagnostic engine. Exclude local downloads,
credentials and durable artifacts from Git and Docker build contexts. README must
explain local setup, budget/source limits, the actual supported workflow and failure
states. Publishing code does not redistribute a cached real dataset.

Use authored `SYNTHETIC_DATA_ONLY` provider fixtures for parser/error/calendar tests;
these never count as real-source verification. Separately exercise the actual local
API/worker/browser with private data after the cutoff, assert pinned rerun equality,
no ledger/order effects and restart retention. Public evidence contains sanitized
checks/hashes only. Green CI, current-head MergeWatch and completed integrated/native
release gates remain required. This ADR does not itself establish an agent-ready
implementation artifact, a real-data demonstration or a published0.0.2 release.
