# Immutable market refresh

Issue #30 adds internal `refresh_market_data` jobs to the existing supervised worker.
Enqueue through `Queue.enqueue` with a UUID idempotency key. Public snapshot routes
and UI controls belong to #31; this internal service does not claim those are delivered.

For offline fixture acquisition, payload is:

```json
{"schema_version":1,"source_mode":"synthetic_fixture","expected_manifest_hash":"<trusted fixture manifest SHA-256>"}
```

For optional research acquisition, use `source_mode: research_market_data` and a
`research_config` validated by `backend.market_data.research_config.ResearchConfig`.
Do not supply an output manifest hash: the immutable configuration is pinned in the
job and its canonical hash is recorded in the resulting provenance. Configuration
requires reviewed local-use rights for both directory and prices, source references,
explicit provider/venue/internal identity mappings and sector/alias evidence, a pinned
calendar and requested session coverage, and a broad venue selection rule reference.
Every non-test directory listing selected by that rule must match the configured
inventory exactly. No silent first-N truncation, missing-name omission or ticker-only
identity assignment is allowed. Unsupported venue mappings fail explicitly.

The network path is inactive during normal fixture startup. To install its pinned
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
snapshot pointer preservation. A live provider diagnostic is optional and not an offline CI gate.
