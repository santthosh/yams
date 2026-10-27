# CI verification

Issue #26, PR #93. This record distinguishes controlled failures from successful
delivery. The passing PR and actual main runs must be recorded before closure.

| Probe | Hosted evidence | Observation |
|---|---|---|
| Cancellation | [40601868198](https://github.com/santthosh/yams/actions/runs/40601868198) | Quality/runtime cancelled; `CI / required` failed |
| Deliberate Python type mismatch | [40601987707](https://github.com/santthosh/yams/actions/runs/40601987707) | Mypy rejected `str` assigned to `int`; required aggregate failed |
| Deliberate OpenAPI drift | [40602354519](https://github.com/santthosh/yams/actions/runs/40602354519) | Contract check rejected the edited schema; runtime passed and required aggregate failed |

Type-probe artifacts identify tested candidate
`ad81fbeab3a198c6d7e24270f80c27e2c5e57412`; drift-probe artifacts identify
`32a6b1f3151018849181b121f11402a50cf7d792`. These are PR merge candidates, not
the source branch head. Each job uploads the actual tested SHA alongside logs.
Temporary fault probes must not appear in the final merged tree.

The type-probe run additionally exposed three worker integration tests whose
one-second wall budget expired during process spawning on hosted Linux. The
timeout case keeps its one-second deadline. Memory/crash/invalid-output cases
now allow ten seconds to reach the intended failure, retain exact error-code
and no-publication assertions, and remain bounded. Production budgets were not
changed. All 37 local integration/restart checks then passed in disposable project
`yams-it-ab94f2524dc3`; hosted verification is tracked separately.

Local Ruff, strict typing, 152 Python unit tests and content/local-link checks
passed before deliberate faults. The aggregate unit tests reject failure,
cancellation, unexpected skip, missing/extra jobs and invalid applicability for
both runtime and documentation paths. They also verify the explicit docs-only
allowlist. These tests complement hosted runs; they do not claim an unexecuted
GitHub job passed.

Python is explicitly provisioned by setup-python before uv 0.8.0 installs locked
dependencies. The first hosted attempt showed that setting `UV_PYTHON` alone did
not provide the pinned interpreter. Actions are SHA-pinned; PR permissions remain
read-only and runtime checks need no provider credentials.

Hosted Linux integration then passed all 37 checks in `yams-it-cb7b6403282b`.
The full hosted smoke passed in `yams-smoke-85679115e71e`, including deliberate
migration failure and recovery (the retained failure log is expected evidence).
The contract probe was restored with the normal OpenAPI generator; local
`make contracts-check` then passed.

## Passing implementation PR

[Run 40603003538](https://github.com/santthosh/yams/actions/runs/40603003538)
passed scope, docs, quality, runtime and the actual emitted `CI / required` check.
The tested merge candidate was `bdf1046feed14a8d797ad6109d9743e6bae0c8cb`.
Quality included 152 Python tests, 42 web tests, ten browser tests, both builds,
separate type checks and contract/fixture drift checks. Runtime included all 37
PostgreSQL/process/restart tests and the full isolated offline Docker journey.

MergeWatch reviewed head `a2c0d9bf549632545dc85bc01eda72526ad83b43` with SUCCESS,
5/5 and no findings. PR #93 merged as `b8a3119`; its main run is recorded in the
issue tracker after completion. This follow-up changes only documentation so it
also exercises the explicit docs-only hosted path. Issue closure still requires
that path and the actual main run to pass; no runtime skip is described as a
runtime test pass.
