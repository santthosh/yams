# #74 — Experiment builder and immutable report

The [operational handoff](../../operations/experiment-lab.md) describes the supported
flow and limits. All committed evidence is `SYNTHETIC_DATA_ONLY`, not investment
performance. [Observed results](observed.json) come from real Docker/browser HTTP
responses, decoded without JavaScript integer rounding. Independent financial
expectations remain FIX-07 and its pre-authored Q12 metrics extension.

## Verification

- 377 backend tests and 61 web unit cases pass. The proxy regression first reproduced
  `18446744073709551615` becoming `18446744073709552000`; successful response text
  now remains unchanged, and all 22 proxy/security/error tests pass.
- 90 PostgreSQL tests plus 4 actual restart checks pass in disposable project
  `yams-it-e0ea49eba080`, including raw max-uint64 create/read/rerun, matching
  artifacts and unchanged stored files. The canonical-input projection validates
  against typed inputs and reads an earlier completed report without a migration.
- 30 production Playwright tests pass at 360px and desktop. New cases cover bounded
  form validation, exact seed transport, covered/lookahead-safe defaults, pending/
  cancelled/failed/unknown, discovery failure versus genuine empty/blocked quality,
  unavailable benchmark gaps, sample errors/retry, pagination/windows, keyboard,
  full Axe and no horizontal page overflow.
- Host/Linux strict typing 172 source files, Python/web lint and formatting,
  generated API/client drift,30-file fixture reproduction and production web build
  pass. Documentation links and whitespace are reviewed.

The full offline Docker smoke `yams-smoke-dbef3ff39df3` passes 15 checks. Its actual
mobile/desktop UI consumes the immutable forks/versions published by the existing
editor journey, follows **Run selected version**, creates reports and verifies
pinned version/configuration identity and unchanged original version history.
This provides the fork→run→report integration evidence for parent #42.

The same real UI submits the independent FIX-07 window, checks all four exact NAV
values, draws three numeric charts with accessible tables, reruns seed 42 and the
maximum uint64 seed, preserves original results, and cancels a default-window job
without publishing partial financial output. Exact HTTP response text is retained
before parsing, so the recorder cannot silently round the seed either. Service
restart, rebuild and migration-failure recovery preserve these reports and refs.
No external browser request or page error occurs. Only the smoke's randomly owned
project resources are removed; user credentials/private volumes remain untouched.

The real browser checks exposed an invalid default that included the last pinned
calendar session without a later decision-cutoff session. The builder now leaves
a covered session as lookahead; the backend clock policy is unchanged. Full Axe
also exposed a shell label/landmark issue, and mobile review caught warning-code
overflow. These were fixed, with readable method limits and inspectable exact
codes. Earlier harness failures (query matching and browser context ownership) are
resolved; assertions were retained.

## Reviewed screenshots

Real Docker UI: [mobile builder](builder-mobile.png), [desktop builder](builder-desktop.png),
[mobile report](report-mobile.png), [desktop report](report-desktop.png),
[cancelled mobile report](cancelled-mobile.png).

Production UI with labeled transport fixtures: [mobile equity chart](equity-mobile.png),
[desktop equity chart](equity-desktop.png), [failed mobile report](failed-mobile.png),
[empty sample window](empty-mobile.png). These negative fixtures test presentation;
they are not additional financial oracles.

Comparison/challenge remains #43. Current real providers remain diagnostic-only;
this adds no accounting capability, fee override, paper-ledger posting or 0.0.3
release publication. Required exact-head GitHub Actions/MergeWatch and merged-state
results are recorded in the PR and the single #74 shipping tracker.
