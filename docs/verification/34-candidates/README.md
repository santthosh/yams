# Candidate inspection verification (#34)

Captured2026-10-28 from the actual local Compose API, supervised worker,
PostgreSQL and browser. All prices/universe data are authored synthetic fixtures,
visibly labeled `SYNTHETIC_DATA_ONLY`; these are not real investment results.
[Machine-readable evidence](evidence.json) records immutable run identities,
result hashes, approved cutoffs, targets and screenshot hashes.

The populated FIX-01 session2028-07-17 uses cutoff20:15Z and independently
expected20% targets for SYN:AAA/BBB/CCC with40% cash. Separate resource/job IDs
reproduce the same result hash. Session2027-01-04 uses cutoff21:15Z and completes
cash-only because required history is unavailable. Saved runs reload after browser
refresh and remain byte-equivalent through Compose restart and rebuild/recreate.
No orders, recommendations, portfolios or ledger entries are created by this flow.

- [Mobile populated result](candidates-360.png)
- [Desktop populated result](candidates-1280.png)
- [Mobile cash-only result](candidates-empty-360.png)
- [Desktop cash-only result](candidates-empty-1280.png)

Actual verification commands: `python scripts/smoke.py` and
`python scripts/test_integration.py` under the locked environment. Smoke passed in
`yams-smoke-8b4f19710cd3`; PostgreSQL passed55 tests plus2 restart checks in
`yams-it-533dba67cbfc`. Both harnesses removed only their own disposable resources.
The supervised worker rejects a different build/config/calendar/snapshot or cutoff
before publication. Independent numerical/target tests, timestamp boundary tests,
late-evidence mutation tests and publication fences provide complementary proof.

Separate mocked-browser tests cover network/failed/unknown/stale/research-empty
states, keyboard, mobile width and accessibility. They are transport checks, not
financial oracles or a substitute for the real Docker journey above.

This evidence establishes the scoped synthetic diagnostic flow. Current-head
GitHub Actions and MergeWatch must still pass before merge. A verified0.0.2
release additionally needs its epic's provider-derived universe and immutable
native-platform packaging evidence; no milestone release is claimed here.
