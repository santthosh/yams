# Approved overnight decision cutoff

Q17 supersedes the earlier Q15 default for new evaluations. The cutoff is one
hour before the next pinned session opens, using explicit calendar lookahead.
No weekday/open is invented. Completed earlier results retain their original
cutoff/build/hash; a queued old-build job fails rather than running under a newer
policy. Tests cover both behaviors in PostgreSQL.

Full local Compose verification passed in `yams-smoke-f3be17d9e523`. Six actual
API/worker/browser runs at360/1280px cover populated evaluation/rerun and cash-only
insufficient history, equal rerun hashes and complete envelope retention through
restart and rebuild/recreate. All prices/universe values here are explicitly
`SYNTHETIC_DATA_ONLY`, not actual Tiingo data or market forecasts.

- [Machine-readable run evidence](evidence.json)
- [Mobile result](candidates-360.png)
- [Desktop result](candidates-1280.png)

Independently expected fixture cutoffs: as-of2028-07-17 -> next opening
2028-07-18T13:30:00Z -> cutoff12:30Z; as-of2027-01-04 -> next opening
2027-01-05T14:30:00Z -> cutoff13:30Z. Targets remain20% each for SYN:AAA/BBB/CCC,
40% cash in the populated fixture; insufficient history remains100% cash.
Boundary tests verify available_at equality and ±1µs, late ingestion, DST, holiday
weekends, early closes and absent/invalid next sessions. Future/late price mutation
cannot change earlier candidates/targets. Explicit next-calendar coverage errors
are typed422 INSUFFICIENT_MARKET_DATA.

Local checks passed286 backend unit/contract tests,56 PostgreSQL tests plus2
restart checks,49 web tests, Python/web lint/type checks, contracts, fixtures,
documentation links and actual Docker build/browser smoke. Exact-head CI and
MergeWatch remain required before merge. Real-data integration and the0.0.2
release gate remain with #109/epic #3; this is not release publication evidence.
