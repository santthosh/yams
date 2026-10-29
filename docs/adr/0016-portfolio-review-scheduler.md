# ADR-016: Monthly portfolio reviews and honest restart catch-up

Status: Proposed for ratification by the owning #51 implementation PR. This
contract extends ADR-005/008 and delegates financial work to ADR-001/004/014/015.
It changes no cutoff, strategy formula, execution price, fee or posting policy.

## Scope and clock

Active paper portfolios use their immutable strategy's existing monthly review
frequency. The single local supervisor observes due work while Docker runs. No
approval, order, fill or future fixture time is created by merely scheduling a
review. Paused/closed/reconciliation-blocked accounts are not evaluated.

A monthly anchor is the last pinned trading session before the first pinned
session in the next calendar month. Both sessions must exist; the last row in a
truncated calendar is not automatically a month end. Its intended due instant is
ADR-001's canonical next opening minus one hour. Begin with the first covered
anchor whose due instant is not before account creation; unavailable historical calendar/coverage is
reported, never filled with weekdays or fabricated occurrences. Each accepted
occurrence retains its original session/cutoff and observation provenance.

Real clocks use actual database UTC, but current real sources remain unsupported
for portfolio accounting. Synthetic clocks use ADR-015's durable floor of posted
ledger chronology, explicitly accepted fill observations and the canonical cutoff
of an explicitly requested manual synthetic review. Selecting that session in a
manual request is a durable virtual-clock observation, including for a cash-only
portfolio with no batch to advance. It changes no money, holding or authorization.
The immutable accepted run retains its evidence; an additive monotonic target
projection retains the maximum explicit cutoff. Database guards prevent that
observation or a handled-session checkpoint from rewinding or being erased. Exact request retry does not
advance twice. Accepted failed/cancelled reviews still retain the requested
observation, like failed/cancelled explicit fill steps. Existing manual cutoffs are
backfilled on upgrade without modifying their original payloads.

Background scheduled admission never updates that explicit observation and must
prove its cutoff has already elapsed under the prior clock. Consequently a
worker restart, wall-clock passage, forecast, GET or newer future-dated fixture
publication cannot advance the synthetic clock. Status distinguishes logical replay time, actual UTC
observation and unknown/unavailable clocks.

## Due opportunities and missed periods

Generate intended occurrences oldest first within the existing bounded catch-up
budget. Target observation is bounded and fair; among the observed targets,
process the oldest intended occurrence first, with strict order within each
portfolio. Independent portfolios do not acquire an invented financial dependency.
Retain each missed/skipped/unavailable outcome and its intended cutoff;
no coalescing of financial events. A new scheduled analysis is eligible only
while its anchor is the latest calendar decision session whose canonical cutoff
has elapsed under the observed clock. Once a later decision session is eligible,
that old review opportunity is missed, rather than a supposedly fresh historical
recommendation. Catch-up may record several missed monthly opportunities; it
never backdates a new approval or evaluates today's holdings as an old portfolio.

For a current opportunity, the existing admission service freezes current posted
state/revision and verifies it was known by the original cutoff. Missing source
coverage/evidence leaves an explicit waiting/unavailable outcome while that
opportunity remains current; a later compatible publication may satisfy it.
Posted state after cutoff, obsolete opportunities and unsupported accounting
cannot produce a decision or invented price. A calendar revision cannot silently
move an already stored cutoff; report incompatibility instead.

The actual admission time remains in the run/job audit. For newly admitted
synthetic evaluations, the private payload's request clock is the later of actual
UTC, the selected canonical cutoff and the durable observed replay instant, so
original recommendation creation cannot masquerade as an earlier logical observation. Its as-of/cutoff remain the
original intended decision. Existing immutable payloads and stored results
retain their original bytes and timing; a reused manual analysis keeps its actual
original provenance. Actual computation/publication time remains separate.

## Atomic admission and deduplication

Persist a stable portfolio review target, business-session occurrences and their
outcomes. Occurrence identity is stable across restarts and concurrent schedulers.
Link the existing recommendation run/job and the occurrence/checkpoint in one
transaction under the portfolio lock. A crash cannot leave a checkpoint claiming
work that was not admitted. An unresolved earlier review job prevents a later
state-dependent occurrence overtaking it. Terminal failure/cancellation is visible
and does not mutate an original job into a fresh attempt.

An equivalent manual and scheduled evaluation uses the same posted revision,
strategy/config, resolved snapshot/calendar/build, as-of session, clock mode and
seed. Serialize lookup/admission under the existing portfolio lock: scheduler
lookup can reuse matching manual work, and manual lookup can reuse work associated
with a scheduled occurrence. Independent manual reruns without an associated scheduled occurrence retain
their previous behavior.
Only compatible queued/running or completed-reviewable work can be reused; failed,
cancelled, dismissed or expired results are not silently resurrected.

A new explicit manual request key that reuses existing scheduled work retains its
own original input/result binding in an additive immutable request alias. Exact
retry resolves that binding before freshness, and changed inputs under that key
still conflict. Existing pre-alias request identities and source results remain
recoverable. Resolved snapshot equivalence does not change an original request's
canonical input bytes. No browser or route owns financial computation.

At most one new review job is admitted per scheduler tick, within the existing
catch-up limit. Missed metadata may consume the remaining bounded allowance.
Existing FIFO/manual queue work is allowed to run between ticks. Heavy review
source preparation runs only between handlers; lightweight supervisor observations
continue during handler heartbeats. Continue using
existing lease recovery and approved-fill catch-up; original approval/eligibility,
explicit observation clock, event uniqueness and committed-sale funding remain
unchanged. Scheduler failure on one target does not starve unrelated work.

## Observability and public read transport

`GET /api/v1/portfolios/{id}/schedule` returns a typed readonly projection for the
#52 screen: monthly policy, next intended due session/cutoff or an explicit
unavailable reason, current durable clock, last supervisor observation/clock, latest explicit review
cutoff, latest outcome and linked job, bounded
recent occurrence history/backlog indication, and active approved batch identity.
Unknown portfolios return404; unavailable storage/integrity503. GET never creates
schedules, enqueues, repairs or advances time. A target not yet observed reports
that state explicitly. There is no public arbitrary schedule/clock mutation.

Persist actual supervisor observations and the last unobserved interval. Refresh
observation during both idle ticks and supervised handler heartbeats so numerical
work is not mislabeled as downtime. A gap starts at the last observed heartbeat,
not a fictitious exact shutdown instant. Disclose that observation limitation,
worker freshness and `Monitoring paused while YAMS was closed`; do not promise
24/7 monitoring or claim a stopped process is currently alive. Completed catch-up,
waiting data, skipped work, unresolved jobs and next due time remain distinct.

## Verification and ownership

Additive migrations retain existing portfolios, jobs, approvals, forecasts and
immutable canonical payloads. Coordinate generated API types and operational,
blueprint/UX/README documentation. Keep financial fixtures independently authored.
FIX-06/09 proofs include multiple missed periods, manual/scheduled races in both
orders, original key conflict/recovery, atomic admission/checkpoint rollback,
per-target ordering, bounded catch-up yielding, no automatic future replay,
missing/stale/provider evidence, original approved-fill chronology and duplicate
posting protection. Actual PostgreSQL restart, the bounded worker and fresh Docker
status/recovery evidence are required. #52 owns UI and #53 the integrated/native
0.0.5 release. No later milestone is authorized by this contract.
