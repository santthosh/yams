# Strategy registry and immutable versions

Issue #71 adds the initial `strategy` and append-only `strategy_version` tables in
migration `0004_strategies`. #36 extends them with publication/fork APIs for 0.0.3,
using the existing schema and immutable triggers. No scores, forecasts, orders or
ledger entries are seeded or computed by the registry.

## Startup and immutable publication

The existing serialized bootstrap transaction migrates, creates/loads the singleton
workspace, validates `backend/strategies/default_momentum.json` and seeds one
published momentum version. Missing files, unsupported rules or a config hash
different from the approved FIX-01 hash fail bootstrap atomically. The packaged
default is parameters only, independent of runtime market data or fixture access.

The template key is `risk_adjusted_momentum_v1`. Stable UUIDv5 identities are
`DEFAULT_STRATEGY_ID` and `DEFAULT_VERSION_ID` in `backend/strategies/registry.py`.
The strategy ID derives from namespace URL plus
`https://yams.local/strategies/risk-adjusted-momentum`; version 1 derives from that
strategy ID plus `1`. These identifiers are local names, not network endpoints.
Repeated/concurrent startup preserves IDs, content and original timestamps.
Existing incompatible records fail visibly; seed never overwrites them.

The canonical config SHA-256 is
`2093c63d190815eba052508d6d42d8ae0c93400cf777602d2c5f759627f43f21`.
This is the ADR-003 default: 126/63 momentum, 60-return volatility, SMA200 trend,
top 8, 20% position cap, 40% sector cap and 5% cash floor.

PostgreSQL rejects updates/deletes of published versions. A changed rule requires
a new published version; it cannot reinterpret old references. Strategy names
follow ADR-008 trimming/control-character rules, with a workspace-scoped unique
casefold key. Publishers must use `strategy_name(name).casefold()` for that key.
No metadata-update or mutable draft endpoint is activated here.

## Read contract

`GET /api/v1/strategies?limit=25&cursor=<UUID>` returns a `Page[StrategyV1]` with
`items` and nullable `next_cursor`. Limit is 1–100. Stable UUID ascending order
and an existing strategy ID cursor provide keyset pagination. Unknown or malformed
cursors/invalid limits return the standard `422 VALIDATION_ERROR` envelope.

Each strategy includes `id`, `name`, `is_template`, nullable `template_key`,
`created_at`, and the latest immutable `published_version`. The version includes
its own ID, strategy ID, ordinal, `published` status, complete validated
`StrategyConfigV1`, canonical hash and publication timestamp. Reads verify the
stored config/hash; missing storage or integrity failures return sanitized
`503 NOT_READY`, never fabricated defaults. An empty registry returns an empty
page; it does not trigger seed or trading from a read request.

## Create, inspect and publish (#36)

The same-origin `/api/v1/strategies` proxy supports creation, detail and immutable
version browsing/publication. Send `Content-Type: application/json` and an `Origin`
matching the browser's authority for writes; no request key is required. Requests
are capped at 1 MiB. It forwards no cookies, user authorization or provider tokens.

1. Read the complete `published_version.config` from the chosen strategy or its
   version history. The initial default is a documented hypothesis, not evidence
   of profitability.
2. To create a separately named fork, POST `{ "name": "My momentum fork", "config":
   <complete config> }` to `/api/v1/strategies`. The response201 includes the new
   strategy and immutable version1. This is JSON notation: substitute the entire
   config object, never the `<complete config>` placeholder.
3. To change parameters under an existing identity, POST the complete config
   **without a wrapper** to `/api/v1/strategies/<strategy-id>/versions`. A successful
   response201 allocates a fresh UUID and next ordinal. Identical input also appends;
   a lost-response retry may create another version. Review history before retrying.
4. GET `/api/v1/strategies/<strategy-id>` for metadata/latest version; GET its
   `/versions?limit=25` for ascending ordinal history. Follow `next_cursor` as the
   final version UUID; cursors must belong to that strategy. Limits are1–100.

Use the generated `StrategyCreateRequest` and `StrategyConfigV1` types rather than
hand-maintained browser models. Every config field is required. Syntax validation
runs independently of current market-data availability; execution is separate.
Unknown/unsupported keys/operators, invalid caps/names and invalid/cross-strategy
cursors return422 VALIDATION_ERROR. Unicode-casefold duplicate names return409
STATE_CONFLICT, unknown strategies404 NOT_FOUND, storage/integrity faults503 NOT_READY.
No partial root/version survives failure. Row-level locking serializes publication;
DB uniqueness protects name conflicts. Completed writes return only after commit.

Original version IDs/config/hashes remain inspectable after changes. Evaluations
and future experiments/accounts must pin a version ID, never resolve “latest” for
an existing run. New identity forks record their own root/version lineage; v1 has
no parent-version field. No update/delete API, editable backend draft, metadata
rename, new template formulas or Lab authoring UI is included in #36.

## Verification and handoff

Unit checks compare packaged bytes/hash against the independent FIX-01 oracle,
reject missing/unsupported/drifted defaults, and cover name and API validation.
Real PostgreSQL integration checks cover fresh/repeated/concurrent seed, exact
metadata, immutable versions, pagination, casefold conflicts, hash corruption,
atomic rollback on a failed default and an actual PostgreSQL container restart.
The Compose smoke checks the real same-origin registry at fresh boot, restart and
rebuild/recreation. Generated-client tests preserve decimal config strings.

#34 consumes immutable version IDs/config hashes for snapshot diagnostics. Tests
prove a persisted diagnostic remains pinned after appending to its source strategy;
existing immutable triggers and FK restrictions prevent referenced deletion. Public
experiment persistence belongs to #39/#41 and is not fabricated here. Publication
races, Unicode conflicts, failure rollback and actual PostgreSQL restart are tested.
The offline Compose smoke exercises the real proxy and retains all versions across
restart/rebuild. #73 owns the version-authoring UI; #44 later consumes version IDs
for portfolios. OpenAPI/schema goldens and generated TypeScript are synchronized.
