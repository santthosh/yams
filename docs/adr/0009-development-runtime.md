# ADR-009: developer runtime and worker enforcement

Status: **Proposed — awaiting Q14 in issue #72.** Do not treat this proposal as an
approved exception or claim that `make dev` exists.

## Conflict

Technology Strategy §3 requires web/API/worker to run natively with hot reload
while only infrastructure runs in Docker. The delivered worker verifies Linux
cgroup v2 CPU/memory/swap/PID limits, uses Linux parent-death protection and runs
each handler under process limits. Native macOS does not provide those mechanisms.
Removing the verification would contradict ADR-005's enforced resource contract.

The full-container application works in Docker Desktop's Linux VM. That satisfies
the authoritative application runtime but does not fulfill the separate native
developer-mode requirement.

## Proposed decision

For macOS development, run web and API natively with hot reload and keep the worker
inside a bounded Linux container. PostgreSQL remains containerized. The development
configuration would expose PostgreSQL only on loopback for the native API, separate
from the default production Compose network which publishes only web. Use separate
development project/volume names and preserve all worker enforcement.

Fully native Linux worker execution, if provided, must discover and verify its own
bounded cgroup and preserve subprocess limits; an unbounded host process is not an
equivalent implementation. Full-container mode remains the reproducible reference.

## Alternative under consideration

Require fully native macOS worker execution too. This needs a designed and measured
macOS enforcement mechanism for the same guarantees, additional process/recovery
tests, and a coordinated ADR-005/worker change. It is not a switch that disables
checks in developer mode.

## Required follow-through after the answer

Record Q14, update Technology Strategy's developer-mode wording and the issue
handoff, implement the selected development command/configuration, verify hot
reload plus the real database/job journey, and retain the environment limitations.
Keep #25 open until that scope and its other review gates are delivered.
