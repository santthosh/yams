# Experiment API (planned 0.0.3, #41)

The source checkout exposes historical synthetic experiments through the API and
same-origin web proxy. The report UI is owned by #74; this API does not activate
paper orders or mutate a durable portfolio. A merged implementation is separate
from a published milestone release.

## Create and observe

`POST /api/v1/experiments` accepts the versioned `ExperimentRequest` and returns
`202 {experiment_id, job_id}`. Discover immutable version IDs using the strategy
registry and snapshot IDs through `/api/v1/data/snapshots`. Inputs are a half-open
session interval, positive USD capital, benchmark, execution policy, random seed
and chronological holdout split. The default supported execution policy remains
`us_eod_next_open_v1`; request bodies cannot override fees or financial rules.
The pinned calendar, source capabilities and workload limits are checked before
admission. Future research decision cutoffs are rejected; authored synthetic
fixtures can intentionally contain future dates.

Poll `GET /api/v1/jobs/{job_id}` or `GET /api/v1/experiments/{experiment_id}`.
History is available at `GET /api/v1/experiments?limit=25`. Only completed public
experiments contain metrics, report summary and all three managed artifact
references (curve, trades and reproducibility). References contain UUID, SHA-256
and schema version; they never expose filesystem paths. Internal `backtest_core`
resources remain separate and are not exposed as public completed experiments.

The detail response includes immutable configuration, input fingerprints,
core/report engine versions, source/provider, comparison controls, period metrics,
SPY availability and warnings. SPY is an adjusted-close, fully invested,
friction-free proxy; its dividend and initial-close conventions differ from the
strategy's raw-price next-open accounting. Cash has zero return. Neither fixture
statistics nor backtest results are predictions. All committed examples and
verification data are labeled `SYNTHETIC_DATA_ONLY`.

## Bounded series and trades

- `GET /api/v1/experiments/{id}/series` returns NAV, cash, held positions, SPY/cash
  samples, drawdown and exposure weights on the original pinned sessions.
- `GET /api/v1/experiments/{id}/trades` returns simulated execution outcomes,
  including skipped/reduced quantities and their original decision/next-open
  lineage. These are backtest records, not posted paper fills.

Both endpoints accept `start_session`, `end_session_exclusive`, `limit` and
`cursor`. The default window is the original run; narrower windows are half-open
and must be contained in it. Nontrading windows can be empty. Page size defaults
to25 and is capped at100. A returned opaque cursor is bound to the experiment,
artifact hash, role, window and page size; keep those parameters unchanged on the
next request. History uses descending creation-time/UUID keyset pagination.
Missing benchmark samples remain explicitly unavailable on the original dates.
Money, quantities and exposure weights are decimal strings; finite statistical
metrics include explicit null reasons. Clients do not recalculate financials.

Invalid IDs, windows and cursors return the common422 envelope; unknown resources
return404. Series/trades before successful completion return409. Failed or
cancelled runs retain null results. Storage/integrity failures return a safe503,
with no provider credentials, submitted payloads or server paths in the response.

## Cancellation and durability

`POST /api/v1/jobs/{id}/cancel` requires an explicit empty JSON object. Queued jobs
become cancelled; running jobs become cancel_requested and are cooperatively
stopped by the supervisor. Those accepted requests return202, including a repeated
request while cancellation remains pending. Already terminal jobs return409;
unknown jobs return404. Completion and cancellation acquire the same job row
lock, so a successful completed result cannot be reversed by a late cancel.
Browser writes require same-origin JSON through the closed proxy routes.

One bounded `backtest` job reuses the shared strategy, allocation, execution and
Q12 reporting code. It stages core and report files, then the supervisor checks
its current lease and cancellation state before and after durable filesystem
publication. Core registration, report registration and job completion commit in
one transaction. A crash can leave unregistered files, never a completed partial
report; a fresh identical recomputation can reuse verified immutable files.
Rerunning creates a new experiment identity while identical inputs and installed
engine produce matching financial artifact hashes. An engine upgrade is captured
in provenance and does not reinterpret queued inputs from another build.

Migration `0005a_experiment_reports` adds an immutable report seal after the
existing experiment/core schema, preserving workspace, versions and jobs. Normal
startup/rebuild retains the database and artifact volumes. Do not reset volumes
to upgrade. Files are fixed-role, hash verified, capped at64MiB per report and read
through contained descriptors that reject symlinks, hardlinks and nonregular
files. No user-supplied filesystem path is accepted.

Tiingo remains diagnostic-only: current capabilities do not establish historical
raw execution/action/publication/membership support. This API rejects unsupported
real accounting sources rather than guessing those facts. No token or provider
download is required for the offline synthetic path.
