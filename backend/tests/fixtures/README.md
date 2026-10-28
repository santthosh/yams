# Synthetic fixture handoff

All files under `data/fixtures/` are **SYNTHETIC_DATA_ONLY**. They contain no provider downloads, real investment results, broker operations or user portfolios. The suite is delivered by #21 for later consumers; passing its checks proves fixture consistency, not that those future features work.

Run `make fixtures` to regenerate and `make fixtures-check` to compare committed bytes. `make test-backend` includes two-directory regeneration, schema validation, hash/identity checks, independent arithmetic and mutation controls. The generator uses only the standard library and locked NumPy 2.5.4; it imports no production financial calculation. Normal fixture generation requires no network after the locked environment is installed. Never regenerate expected results from a future engine to make its tests pass.

## Files and reproducibility

`data/fixtures/manifest.json` is the suite index, including SHA-256 and byte size for every generated artifact, the full snapshot hash and its UUIDv5 identity. It is distinct from `snapshot/manifest.json`, which is a complete ADR-007 manifest validated by `SnapshotManifestV1`. That manifest's exact compact canonical bytes hash to the suite's `snapshot_sha256`. Its six JSON artifacts contain assets, bars, calendar, provenance, universe membership and an explicit empty action table. File relocation leaves identity unchanged.

The snapshot has five assets across four years (2027–2030), enough for a 252-session warmup followed by multi-year research. AAA and BBB have identical smooth prices for deterministic ties; CCC has an alternating volatile component; ZERO is flat; SYN:SPY is a synthetic benchmark, not historical SPY data. Raw/adjusted prices coincide because this base snapshot has no corporate actions. FIX-05 separately supplies explicit split/dividend input traces. Volume is one million raw shares. Every row is schema-valid, available one second after its synthetic close, and sorted by asset then session.

The calendar is explicitly `SYNTHETIC_XNYS_LIKE_V1`: weekdays excluding Jan 1 and Dec 25, with authored post-2007 US daylight-saving rules. It is **not** a validated XNYS calendar and intentionally lacks other exchange holidays. Its generator and timezone-rule versions are in the hashed calendar artifact; no host timezone database or current date affects generation. FIX-06 contains its own abbreviated calendar to exercise holidays, missing opens and DST boundaries. Production calendar validation remains with feature owners.

`scripts/fixture_cases.json` is the reviewed source for ten `fix-NN/case.json` artifacts. Each case records inputs, fixed expected values, derivation, tolerance, later owning issues and named negative mutations. Small operator examples are labeled separately from production-length inputs. `scripts/fixture_strategy.canonical.json` is an independently authored ASCII canonical config vector. Its expected SHA-256 is `2093c63d190815eba052508d6d42d8ae0c93400cf777602d2c5f759627f43f21`; the schema's canonicalizer is tested against these bytes, rather than creating the oracle itself.

FIX-08 includes 5,000 × 13 non-circular PCG64 block starts as little-endian int64, the initial RNG state and NumPy version, and 252 × 2 constant anti-correlated return vectors as little-endian float64. Starts range from 0 through 247; block length is five; truncate the final two excess rows for the explicitly supplied 63-session **sampling probe**. This count must never replace the calendar-derived 90-day production horizon. Exact array/index hashes and first-row integers are frozen in the case oracle. The suite manifest fingerprints the complete probe artifacts; the metadata explicitly does not claim a full production forecast fingerprint with calendar, portfolio and engine lineage.

## Independent expectations

| Case | Derivation and later proof owner |
|---|---|
| FIX-01 | Population z-scores for [1,2,3], constant-vector zeros, exact 60/50−1 momentum, stable ID ties, zero-volatility exclusion before top-N and simultaneous cap examples. Full snapshot AAA at index400 uses prices `50+i/20`; 60 log returns, sample denominator59, SMA200 and 20-observation liquidity have committed scalar oracles. #32/#33 must run their engine against these inputs. |
| FIX-02 | Filter evidence at the original cutoff before calculation; future-only mutation leaves the two retained prices and .2 momentum unchanged. The short operator trace is not a valid warmup window. #29/#32/#48 own actual as-of engine enforcement. |
| FIX-03 | Exact Decimal 1000→799.80→999.60 at adverse10bps and zero commission; affordable .999000 shares; half-even tie cases; minimum-trade and immediate posted-sale cash traces. #35/#44 own execution. |
| FIX-04 | Duplicate event key has one200.20 debit, two shares and one revision increment. The deliberately wrong double posting gives599.60. #44/#46 must prove database uniqueness/concurrency. |
| FIX-05 | 2:1 split doubles two shares and halves100 basis, preserving200 total basis. Four-share entitlement ×1.25 yields one5.00 payable credit even after sale. Flat adjusted closes already incorporate actions. #29/#35/#44 own ingestion/execution. |
| FIX-06 | Strictly later opening excludes approval equality; no invented session or stale substitute price. Ninety local dates from Jan1 crosses DST to Apr1 at20:00Z; three explicitly supplied future closes qualify. #29/#35/#46 own calendar and fill enforcement. |
| FIX-07 | NAV[100,120,90,108] yields8% return and25% drawdown. Three return periods annualize with exponent84; sample variance .0675, meanreturn .05, gross100/meanNAV104.5 turnover. The extremely large annualized return is an arithmetic probe, not an investment claim. #39/#40 own metrics. |
| FIX-08 | Chosen blocks give row indices[1,2,0]; paired vectors cancel at50/50. Five-path linear quantiles are−.16/0/.16 with loss2/5. Cash cost10 reduces1000 to990 once. Constant75/25 weights yield `.005` per step and `(1.005)^63−1`, ending1369.18; all5,000 paths are identical in that specific probe. #48 owns the full sampler/engine. |
| FIX-09 | Fenced old attempt publishes zero results; new attempt publishes one. Redelivery after committed fill cannot post again. Cancel-first and fill-first have distinct authored outcomes. #23/#44/#46 must execute crash/recovery tests against real storage. |
| FIX-10 | Equal initial capital/start/policy; only A's ledger changes to799.80 and two shares, while B stays1000 and zero shares. This does not preempt later launch authorization or promotion semantics. #55/#56 own Arena integration. |

Cash is exact cents with HALF_EVEN; quantities are exact through six decimals. Complete weights tolerate absolute1e-8; small statistical oracles absolute1e-12; full float64 forecast paths follow ADR-006 absolute/relative1e-10, with indices and provenance exact. Decimal60-digit calculations independently supplied the full-feature, annualization and constant-vector scalar literals; tests cross-check them with standard-library arithmetic. No production engine exists in this PR.

Mutation controls currently demonstrate that changed bytes fail regeneration, altered artifacts change snapshot identity, a future-aware calculation disagrees with FIX-02, duplicate accounting disagrees with FIX-04, and inclusive-open comparison disagrees with FIX-06. Other named mutations are handoffs for future consumers, not claimed passing execution tests. PostgreSQL restart, atomic publication, DuckDB reads, real queue recovery and UI/offline Compose verification remain with their owning issues.


## Alternative template extensions (#38)

`template_extensions/` adds independent mean-reversion/low-volatility canonical
config vectors and a full252-session as-of probe extending FIX-01/02 at index401.
Authored sources are `scripts/template_oracles/`; generator copies/indexes their
bytes without calling the engine. Existing snapshot and FIX-01–10 artifacts stay
byte-identical; only the suite index and new files change. The case records exact
Decimal60 derivations, scalar/rank/cap/cash expectations and tolerances. See
[template operations](../../../docs/operations/strategy-templates.md) and
[reviewed worked probes](../../../docs/verification/37-templates/README.md).
