# Strategy Lab verification (#73)

**SYNTHETIC_DATA_ONLY.** Source development toward0.0.3; no release publication
or historical performance claim. The [summary](summary.json) contains actual
server IDs/config hashes and version-history digests from isolated offline Docker
project `yams-smoke-a6642bfdb30a`. Screens show the completed saved forks:
[mobile360px](strategy-editor-360.png) and [desktop1280px](strategy-editor-1280.png).
Both were visually inspected; forms, labels, Paper-only badge, original/saved rules
and responsive layout remain usable without page overflow.

The real browser used Enter in the new-name field to create a mean-reversion fork
at360px and a low-volatility fork at1280px, each with position cap0.15. An explicit
append changed only the cash floor from0.05 to0.10 (backend-normalized0.1), creating
version2 with a new ID/hash. The browser inspected version1 again and the original
template's0.2 cap. Exact saved histories, including timestamps/rules, survived
actual container restart and rebuild. Test-owned volumes were removed; no existing
user project, provider token or market dataset was touched.

Local gates passed:56 web unit tests,22 production browser tests (keyboard/mobile,
Axe accessibility, invalid input/no publication, both pagination controls,
422/409/unconfirmed failures with preserved edits, history reload and empty/missing
states), frontend lint/separate typing, production Next build and contract drift.
Full offline Docker smoke also retained all ten candidate/worker evaluations,
version histories, health/resource/private-network and migration/recovery proofs.
No backend financial logic, schema migration or domain model changed. Python
integration remains an applicable existing CI gate; it was not claimed as a new
local #73 test run. Native release smoke uses the same flow when its owner runs it.

A new keyboard regression was reproduced before correction: Enter in the fork-name
field invoked the form's default append action. The corrected handler submits the
fork button explicitly, preserving validation/pending guards. The production
browser suite and final real Docker keyboard journey both passed afterward.
Unconfirmed named forks direct the operator to reload strategies; append recovery
uses version history. Publication never retries automatically or changes portfolio
bindings/holdings. Runtime source assumptions remain those of the existing APIs.
