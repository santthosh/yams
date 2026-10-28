# #43 — Fair comparison and controlled strategy challenge

The [operational handoff](../../operations/experiment-comparison.md) defines the
supported flow and limitations. All committed examples are `SYNTHETIC_DATA_ONLY`.
Observed HTTP results are not additional golden financial expectations: those
remain the independent FIX-07/core-case and pre-authored Q12 reporting vectors.

## Local checks

- 377 backend tests pass (94 PostgreSQL cases deselected in the fast suite).
- 64 frontend unit cases pass, including exact full-range seed transport,
  complete alignment-term differences and an immutable single-field copy.
- 44 production Playwright cases pass across desktop and 360px. The 14 comparison
  cases cover actual chosen-metric ordering,2–4 selection bounds, invalid IDs,
  incomplete/missing reports, mismatch blocking, exact-seed challenge publication,
  uncertain submission/retained accepted jobs, paging, genuine empty samples,
  recovery, keyboard/full Axe/table alternatives and no page overflow.
- Production build, web lint/format/separate typing, strict Python typing 172 files,
  Python lint/format 174 files, unchanged generated API/client drift and 30-file
  fixture reproduction pass. Documentation links and whitespace are checked.

## Real Docker journey

Full offline Docker smoke `yams-smoke-ab9ea25a6333` passes all16 checks,
including restart/rebuild and migration-failure recovery. The executable comparison browser journey consumes
real reports created by the preceding editor→form→worker flow. It verifies:

- Aligned completed original/rerun reports, numerical NAV chart axes, exact session
  tables, chosen sorting, keyboard/full Axe and 360px/desktop layout.
- Explicit one-rule fork publication and real worker completion, matching backend
  comparison fingerprint, exact canonical input settings/full uint64 seed and
  unchanged original report bytes. The source/target link opens the new pair and
  derives exactly one stored-rule difference.
- A genuinely different-capital run, visible exact incompatibility, no silent
  ranking/curves, explicit common-setting reruns, matching original artifact
  fingerprints and unchanged originals.
- Saved reports, original strategies and versions, both newly published challenge
  roots, and their histories survive restart/rebuild and migration-failure recovery.
  The runner uses only its disposable Docker project and does not read provider
  credentials or change the user's private Tiingo volumes.

The first actual Docker run reproduced a client navigation regression: following
another comparison query URL retained the previous selected pair. The route now
keys the mounted comparison by immutable IDs; dedicated browser coverage verifies
the transition. A later persistence run exposed the harness's earlier registry
snapshot, which preceded the two intended challenge publications. The snapshot now
follows all writes while asserting all original rows/versions are unchanged and
both new roots map exactly to challenge versions. Assertions remain strict.

There is no new comparison backend, financial calculation/default, request/schema,
migration, provider capability or durable account/order/fill. A constrained maximum
position weight is the supported one-rule control; multi-field changes remain full
Strategy Lab forks. No 0.0.3 release is claimed by this source-only verification.

## Reviewed images and observed evidence

Passing real Docker UI: [aligned desktop](aligned-desktop.png),
[aligned mobile](aligned-mobile.png), [challenge desktop](challenge-desktop.png),
[challenge mobile](challenge-mobile.png), [incompatible desktop](misaligned-desktop.png)
and [incompatible mobile](misaligned-mobile.png). All six were visually reviewed.
[Observed responses](observed.json) retain exact Python-decoded uint64 inputs from
original HTTP text; no screenshot or observed vector is financial oracle data. Required
current-head CI, actual MergeWatch review and matched merged-state verification
are recorded separately in the PR/tracker rather than assumed from local tests.
