# ADR-007: Immutable snapshot manifests and artifact provenance

Status: Proposed for review under #18; accepted when this PR merges. Consumes [ADR-002](0002-data-normalization.md). #20 implements schema contracts; #21 supplies independent fixtures; #29/#30 implement storage/publication and #63/#70 recovery/operations. This ADR does not claim a filesystem/database integration has already passed.

## Manifest v1 and identity

A published snapshot consists of `manifest.json` plus explicitly enumerated immutable artifacts beneath one content-addressed directory. The complete required manifest inventory follows; reject unknown fields at every defined object level. IDs are canonical strings, hashes lowercase64-hex SHA-256, dates exchange-local YYYY-MM-DD, timestamps RFC3339 UTC Z. Nonfinite values are forbidden. Optional values below are required keys with explicit null when unknown, not omitted defaults.

| Field | Value / identity meaning |
|---|---|
| `schema_version` | Integer1 |
| `mode` | `synthetic_fixture` or `research_market_data` |
| `source` | Object: `provider`, `adapter_version`, `normalization_version`, `rights_reference` (string or null), `rights_status` (`synthetic_owned`, `verified_local_use`, `unverified`), `capabilities_sha256`; source capability record is an enumerated provenance artifact |
| `price_basis` | Object: `ohlc` (`raw_as_traded`, `provider_unverified`), `adjusted_close` (declared method/version string), `volume` (declared share basis/version string), `currency` (`USD` initially), `corporate_action_policy` (versioned ADR-001/002 policy identifier) |
| `calendar` | Object: `id`, `timezone`, `version` (schedule content hash), `artifact_path`; artifact hash must equal version, timezone library/version retained in schedule metadata |
| `coverage` | Object: sorted unique `asset_ids`, `first_session`, `last_session`, `latest_completed_session` (dates or null), `missing_sessions` (sorted `{asset_id, session_date}` objects), `membership_basis` (`point_in_time`, `current_only`, `synthetic`); actual effective/availability intervals reside in universe artifact |
| `quality` | `usable`, `usable_with_warnings`, or `blocked`; immutable assessment at publication |
| `warnings` | Sorted unique reason-code strings; fixture mode requires `SYNTHETIC_DATA_ONLY`, current-only membership requires `SURVIVORSHIP_BIAS_RISK` |
| `artifacts` | Nonempty list sorted by path. Each object has `path`, `role`, `format`, `schema_version`, `sha256`, `size_bytes`, `row_count`; counts nonnegative integers, row_count null only for a non-tabular artifact |

Artifact roles are `bars`, `assets`, `actions`, `universe`, `calendar`, `provenance`, `coverage`; formats are `parquet` or `json`. At least bars/assets/universe/calendar/provenance must exist, with coherent cross-references and coverage. An empty action table is explicit evidence of declared coverage, not permission to infer no real actions from a failed source. An independent universe JSON manifest records selection-rule/version, source hash, sorted membership asset IDs and effective/availability intervals with known/unknown status; its file hash participates like every other artifact. Preserve provider-native IDs and alias/sector chronology under ADR-002. No consumer can replace missing universe evidence with today's favorites.

Canonicalize manifest JSON using ADR-003's exact compact UTF-8/key-sorting/number/string rules, extended to ordered arrays. Sort unordered collections as specified above **before** serialization; missing_sessions sorts by asset_id then date. Preserve ordered row/session sequences in referenced artifacts. Hash the canonical manifest bytes, excluding no declared manifest field. The manifest must not contain its own digest, UUID, machine paths or runtime registration timestamps. File SHA-256 hashes cover exact bytes; size and role/schema metadata are also part of identity. Store `manifest_sha256` and snapshot UUID in the database envelope outside the hashed manifest.

Derive snapshot UUID with UUIDv5 using the standard URL namespace `6ba7b811-9dad-11d1-80b4-00c04fd430c8` and exact ASCII name `urn:yams:dataset:sha256:<manifest_sha256>`. Thus copying the same manifest/artifacts to another machine preserves ID; UUID is an identifier, while SHA-256 is the integrity check. Database rows require unique manifest hash and UUID. Verify an existing UUID matches the complete digest rather than trusting UUID alone. A hash collision/inconsistent record is an integrity failure, not overwrite permission.

Identity includes asset/membership rows, effective/availability evidence, calendar, source capability/rights assessment, quality, price/action basis and file bytes. A changed bar or membership row changes its file digest and therefore manifest digest. Reordered input object keys or relocated root directories do not change canonical identity. Regenerating semantically equal Parquet with different writer metadata/compression may change bytes and identity; do not claim cross-writer byte determinism. Pin writer version/settings when generating fixture goldens. Deduplication is by exact recorded content, not guessed semantic equivalence.

## Retrieval and availability diagnostics

Keep a separate append-only retrieval/publication audit containing job/attempt token, request bounds, redacted source endpoint, retrieval start/end, ingested time, validation report, local registration time, original payload hashes and failures. Absolute local paths, worker IDs, progress and local retry times are diagnostics outside snapshot identity. Provider credentials, cookies and signed URLs are never stored in public provenance.

This exclusion does **not** strip temporal evidence from bars or memberships: source `published_at`, `available_at`, availability basis and observation/ingestion fields required by ADR-002 remain in their hashed artifacts. If ingestion is the only availability proxy, a later observation changes semantic evidence and may change identity. Copying an existing immutable artifact preserves that original observation time; import time is a new local audit entry, not a rewrite of the source row. Snapshot API `published_at` is local publication time and is not proof of when individual market facts were available. Fresh/stale is computed from pinned coverage and the requested clock, not by mutating manifest quality.

## Paths and read-only readers

Paths are POSIX-style relative names with ASCII letters/digits, underscore, dash, dot and `/` only. Reject empty names/components, `.`/`..` components, absolute paths, drive letters, backslashes, URL schemes, control/NUL characters, duplicate/case-colliding paths and `manifest.json` as an artifact path. Resolve beneath the configured data root; reject symlinks at every traversed component and nonregular artifact files. Do not follow hard-linked external content or accept arbitrary uploaded host paths; publication creates its own regular files. Use contained file descriptors/no-follow protections and exclusive staging ownership to avoid check/open races. Never interpolate request strings into SQL or a filesystem glob.

Readers obtain a registered complete snapshot ID, validate its manifest and requested artifact integrity, and pin that immutable directory for the whole operation. They never read staging, discover “latest” mid-query, or combine files from different versions. DuckDB is embedded read-only analytics with server-owned parameterized queries over the explicit validated file list. Disable arbitrary external access/extension installation and writable SQL in user-controlled paths; load only needed trusted capabilities at startup. Read-only connection mode alone is not a sandbox. A checksum mismatch or missing file yields an integrity/unavailable error and blocks use, not silent redownload or substitution. Record health/quarantine state separately without rewriting immutable evidence.

## Publication and crash recovery

Use a private attempt-scoped staging directory on the **same filesystem** as the final snapshot store. Write complete artifacts; flush/fsync files; validate schema/coverage/availability/rights and cross-references; derive file hashes and canonical manifest; flush/fsync it and the staging directory. A blocked-quality diagnostic snapshot may be registered for inspection, but never advertised as execution-usable. Structurally corrupt or incomplete files cannot be published at all.

Acquire a publisher/advisory lock keyed by digest, verify the current job lease/fencing token, and atomically rename the sealed directory to `snapshots/<manifest_sha256>` without overwriting an existing destination. Hold coordination through registration. If a destination already exists, verify every byte/hash and reuse it; on mismatch fail/quarantine, never replace it. A plain overwrite-capable rename is insufficient: #29 must implement and test exclusion/no-clobber behavior for its supported filesystem. Fsync the parent directory after rename. Never fall back to a non-atomic cross-filesystem copy into the published location.

Only **after** durable filesystem publication, commit the unique database snapshot row, artifact references, publication audit and optional current-snapshot pointer under the job's valid lease. Filesystem and PostgreSQL are not a single transaction; the ordered protocol deliberately permits recoverable unregistered files but never a registered partial snapshot. A failed transaction leaves the previous current pointer untouched. Recheck a current lease under lock at DB commit; an expired worker can leave an orphan but cannot publish metadata/results.

| Crash point | Required state and recovery |
|---|---|
| During write / validation | Attempt staging remains unregistered; no reader can see it. Recovery reports incomplete attempt; no automatic deletion of user data. |
| Before rename | Previous snapshot readable; validated stage may be revalidated and resumed only under a new authorized claim. |
| After rename, before DB commit | Detectable orphan directory. Verify its manifest, every artifact and original publication intent; a valid retried job can register it idempotently. Startup must not adopt an arbitrary directory as current. |
| After DB commit, before response | Exact retry returns the same UUID/hash and registration; no duplicate snapshot or pointer regression. |
| Missing/corrupt files after registration | Mark operational integrity failure and block consumers; preserve references/audit, restore verified backup or republish as a new snapshot. Never silently change bytes beneath the old ID. |

No normal refresh mutates a completed snapshot, including referenced files or a prior quality assessment. Failed refresh cannot make a usable old version unreadable, though it may now be stale for current decisions. Older queued refreshes must not move the current pointer backward in coverage; serialize/select updates using validated session coverage and publication lineage, not last writer wins. Explicit historical imports need not change the current pointer.

## Retention and backup closure

Retain all registered snapshots/artifacts and referenced evidence by default. No automatic GC/deletion at startup or refresh. Restrictive database foreign keys prevent removal of inputs referenced by strategies, experiments, recommendations, orders/fills, forecasts, Arena or Journal. Unreferenced orphan/staging reporting is safe; deletion/GC is separate later explicit local tooling, never an inferred cleanup permission.

A coherent backup includes a transactionally consistent PostgreSQL dump (schema revision, workspace IDs and reference graph) plus every immutable manifest/artifact transitively reachable from its snapshot/result references, including calendar/universe/forecast index/evidence artifacts. For the initial local backup, pause new job claims/publication and wait for active transactions to settle before taking the dump and copying the pinned reachable closure; immutable files remain untouched. Record backup manifest with file hashes, schema/app versions and missing-reference failures. A backup lacking any reachable file is incomplete, not “successful with warnings.”

Restore into an isolated destination, verify all checksums/IDs and required schema compatibility before reporting readiness, then verify representative reads and exact financial replay where present. Restore DB and artifacts as one verified set; changing an image tag alone cannot reverse a database migration. #63/#70 own operational implementation and restore evidence, without expanding this milestone into those later features.

## Independent FIX-02/06 checks and handoff

- SHA-256 of ASCII bytes `abc` is `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad`; changing one byte to `abd` must change the digest. This tests the digest primitive, not a valid market file.
- Minimal canonicalization oracle: objects `{"b":2,"a":1}` and `{"a":1,"b":2}` both serialize to exact UTF-8 `{"a":1,"b":2}` with no newline and hash `43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777`. This deliberately small object tests serialization, not the full required manifest schema.
- Build a complete synthetic manifest in #21 with independently hashed Parquet/JSON files. Moving its root to another temporary directory preserves manifest hash and derived UUID. Changing one bar, membership interval, calendar or availability timestamp must change a referenced file hash and manifest identity. Changing local registration time alone must not.
- Inject crashes at each publication boundary and enumerate directory/DB visibility independently. After rename but before registration, normal list/read returns no new snapshot; retry registers the verified orphan exactly once. A bad file hash cannot become usable by changing only the DB flag.
- Reader A pins snapshot1 while refresh B fails: A completes entirely on snapshot1. Traversal, symlink, duplicate/case-collision and outside-root artifacts are rejected before any DuckDB read. Complete fixture snapshots carry `SYNTHETIC_DATA_ONLY` through API/UI.

#21 supplies exact full-manifest bytes and digests; #29/#30 test real filesystem/PostgreSQL recovery and read-only analytics. No downloaded licensed dataset is needed for these proofs.
