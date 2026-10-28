# Immutable market refresh

The supervised worker handles `refresh_market_data` jobs; the source-aware API and
Settings UI are delivered by #31. Use `POST /api/v1/data/refresh` with a UUID
idempotency key. Trusted internal callers can also use `Queue.enqueue`.

For offline fixture acquisition, payload is:

```json
{"schema_version":1,"source_mode":"synthetic_fixture","expected_manifest_hash":"<trusted fixture manifest SHA-256>"}
```

Research mode accepts a closed provider-specific configuration. The personal-use
Tiingo path uses `TiingoResearchConfigV1`, a pinned real calendar and a declared
budget-sampled universe; see the [local Tiingo workflow](tiingo-research.md) for the
worker-only token/egress override, quotas and diagnostic-only capabilities. It is
included in the default backend image but requires explicit operator opt-in.

## Conditional Yahoo inspection path

For optional Yahoo acquisition, use `source_mode: research_market_data` and a
`research_config` validated by `backend.market_data.research_config.ResearchConfig`.
Do not supply an output manifest hash: the immutable configuration is pinned in the
job and its canonical hash is recorded in the resulting provenance. Configuration
requires reviewed local-use rights for both directory and prices, source references,
explicit provider/venue/internal identity mappings and sector/alias evidence, a pinned
calendar and requested session coverage, and a broad venue selection rule reference.
Every non-test directory listing selected by that rule must match the configured
inventory exactly. No silent first-N truncation, missing-name omission or ticker-only
identity assignment is allowed. Unsupported venue mappings fail explicitly.

This Yahoo network path is inactive during normal fixture startup. To install its pinned
library in a development environment run `uv sync --locked --extra research` and run
commands with `uv run --locked --extra research ...`. Default Docker images exclude
the extra; a research-enabled operator image must export/install the same locked extra
and have deliberately configured outbound access. Default Compose isolation is retained.
This document does not authorize or implement a cloud deployment.

`rights_verified_local_use` is a strict operator assertion backed by the supplied
references, not a finding made by YAMS. Yahoo terms retrieval was unavailable during
implementation. Library installation, successful parsing and HTTP access do not establish
permission. No real provider dataset is committed or bundled. Test provider-shaped
responses are authored synthetic data and cannot substitute for research inputs.

Directory downloads use fixed HTTPS endpoints, reject redirects and compressed responses,
and cap each file at 8 MiB and each request at 10 seconds. Acquisition admits at most
1,000 assets and 2,520 sessions per job under ADR-005. Oversized selections fail rather
than silently narrow the universe. Historical downloads retain actual observation time;
current membership carries survivorship limitations. Unverified raw-price and action
capabilities produce blocked inspection snapshots, never an execution-usable current
pointer. Ex-dates do not invent dividend payable dates. No holdings or cash are mutated.

## Shared publication and recovery

The child stages files beneath `/artifacts/snapshot-staging/<job>-<attempt-token>`.
Only the supervisor may publish: validate hashes and payload, acquire digest lock,
verify active lease, perform no-replace rename/fsync, recheck lease, then atomically
register snapshot/artifacts/publication audit, optional current pointer and job result.
Current pointers are separate by source mode. Blocked snapshots remain inspectable.

A crash before rename leaves an unregistered stage; a crash after rename leaves an
unregistered content-addressed orphan. Neither appears in registered results or becomes
current automatically. An explicit authorized retry validates every byte before reuse.
Corrupt existing content fails without replacement. Retain failed stages/orphans for
operator diagnosis; there is no automatic garbage collection or destructive repair.
Normal startup/migrations never delete snapshot history. Migration 0003 adds immutable
metadata guards; downgrading requires restoring a verified backup.

Job failures expose a fixed reason in `error.details.reason` and attempt diagnostics.
Rights, schema, coverage and identity failures are terminal. Explicit network unavailability,
timeout and rate-limit failures retry at most three total attempts with persisted backoff;
provider text, credentials and arbitrary response bodies are never returned. Inspect job
status/attempts and source coverage age; a failed refresh leaves the previous pointer intact.

Verification commands: `make lint`, `make typecheck`, `make test`, `make build`,
`make contracts-check`, `make fixtures-check`, `make test-integration`, `make smoke`.
Offline tests cover the actual bounded worker, database restart, immutable rows,
lease expiry, digest contention, no-clobber publication, valid/corrupt orphans and blocked
snapshot pointer preservation. Live provider acquisition stays outside offline CI;
the0.0.2 release epic separately requires actual verified real-source evidence.

## Settings / Data and discovery API

Open Settings → Manage market data and snapshots (`/settings/data`). Choose the source
explicitly. The sample refresh pins the committed fixture hash; advanced research refresh
accepts the selected provider's closed configuration above. Queue admission requires a UUID idempotency key;
the browser retains it after an uncertain network result. The page polls persisted job
status, retains prior same-mode coverage on failure and never offers public cancellation.
Research coverage is not labeled fresh. A blocked inspection snapshot can appear in the
catalog but never becomes the usable current pointer. Empty research mode has no sample
price fallback. Asset search reads the selected immutable inventory and reports empty results.

Reads: `GET /api/v1/data/snapshots?mode=...`, `/data/health?mode=...` and
`/data/assets?mode=...&snapshot_id=...&query=...` (all under `/api/v1`). Pagination defaults
to 25 and caps at 100. Asset cursors bind the source mode, snapshot and query. Snapshot
cursors use the final UUID of the previous page. Invalid inputs return typed 422 errors;
missing/source-mismatched snapshots return 404; database or artifact-integrity failure returns
503 with no filesystem/provider secrets. Files are verified before the catalog returns data.

`POST /api/v1/data/refresh` returns 202 `JobV1`; send `Idempotency-Key` with the body
above. Exact retries reuse the job and changed inputs return 409. Browser traffic stays
same-origin: the Next.js proxy forwards only implemented data paths/query keys and bounded
JSON refresh requests. It strips incoming credentials and requires a same-origin POST.
No arbitrary provider URL is accepted by these routes.
