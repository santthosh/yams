# Default strategy registry

Issue #71 adds the initial `strategy` and append-only `strategy_version` tables in
migration `0004_strategies`. #36 extends them with publication/fork APIs in 0.0.3;
this increment provides only read-only discovery. No scores, forecasts, orders or
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

The same-origin web proxy allows only this read and its `limit`/`cursor` query
fields. Mutation methods remain unavailable. OpenAPI, Pydantic schema goldens and
the generated TypeScript client include the implemented route and models.

## Verification and handoff

Unit checks compare packaged bytes/hash against the independent FIX-01 oracle,
reject missing/unsupported/drifted defaults, and cover name and API validation.
Real PostgreSQL integration checks cover fresh/repeated/concurrent seed, exact
metadata, immutable versions, pagination, casefold conflicts, hash corruption,
atomic rollback on a failed default and an actual PostgreSQL container restart.
The Compose smoke checks the real same-origin registry at fresh boot, restart and
rebuild/recreation. Generated-client tests preserve decimal config strings.

#34 consumes immutable version IDs/config hashes for snapshot diagnostics. #36
must append versions and preserve these identities; #44 may reference version
IDs when its portfolio tables arrive. None of these later workflows is activated
by this registry.
