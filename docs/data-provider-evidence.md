# Data-provider evidence

Reviewed 2026-10-27 for #13 and [ADR-002](adr/0002-data-normalization.md). This is documentation research, not a successful provider integration or a legal determination. No market dataset was downloaded or committed. Q11 permits free sources and permitted user inputs; no subscription is authorized.

| Source / interface | Documented evidence | Supported conclusion and limits |
|---|---|---|
| [NYSE calendar](https://www.nyse.com/markets/hours-calendars) | Official holiday, early-close and core-session schedule | Reference for validating ADR-001's pinned XNYS calendar. The page covers named years, not a perpetual historical calendar or symbol-specific halt history. |
| [yfinance PriceHistory](https://ranaroussi.github.io/yfinance/reference/yfinance.price_history.html), `history`, `get_actions`, `get_splits`, `get_dividends` | Daily history and action interfaces; automatic OHLC adjustment defaults on; missing rows may be dropped; date end is exclusive | Optional research acquisition candidate. Explicitly request `auto_adjust=False`, `back_adjust=False`, `repair=False`, `keepna=True`, `rounding=False`, `actions=True`, `raise_errors=True`. These options do not prove raw historical execution prices, action completeness, dividend payable dates or historical publication timestamps. All remain unsupported until independently evidenced for the adapter/version and coverage. |
| [yfinance repair documentation](https://ranaroussi.github.io/yfinance/advanced/price_repair.html) | Repairs may reconstruct prices, alter action interpretation and produce false positives | Disable automatic repair in canonical input. A correction requires separate provenance/version and availability; repaired values must not silently enter past decisions. |
| [yfinance project notice](https://ranaroussi.github.io/yfinance/) and [Yahoo terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html) | Project describes research/educational use, no Yahoo affiliation and personal-use scope, and refers users to Yahoo terms | Library availability is not data permission. Yahoo terms could not be fetched in this review (HTTP 999); current permission and redistribution rights are **unverified**. No Yahoo data in fixtures, images or releases. Optional adapter activation must establish applicable terms; failure leaves it disabled. |
| [Nasdaq Symbol Directory definitions](https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs), `nasdaqlisted.txt`, `otherlisted.txt` in the documented symbol-directory FTP location | Broad listings, venue/symbol fields, test-issue flags and file creation timestamp; files updated during the day | Preferred published-directory candidate for broad universe discovery, subject to rights verification. Current files do not establish historical membership, delistings or permanent identity. Generation time is not proof of first public availability. Sector and ordinary-equity classification need separate evidenced inputs. Redistribution permission is not established by this format specification. |
| [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | Company submissions and extracted XBRL interfaces | Alternative public issuer/filing context candidate, not evidence of complete exchange membership, daily OHLCV or delisting returns. No SEC adapter selected for foundation. |
| YAMS synthetic fixture adapter | Authored data, explicit calendar/actions/availability and generation recipe under repository control | Mandatory offline baseline; all outputs labeled `SYNTHETIC_DATA_ONLY`. Fixtures validate software behavior, never real returns or provider reliability. |
| User-supplied dataset | No specific dataset reviewed | Conditional future input only: require provenance, permission, schema and coverage validation. User possession alone does not establish redistribution rights. |

## Selection and coverage

The foundation selects the synthetic adapter. For later network research, prefer a permitted broad directory plus optional yfinance price acquisition over a handpicked ticker list. The alternatives above were evaluated by capability, not assumed interchangeable. No currently reviewed external source establishes the complete raw-price/action/point-in-time-membership contract. #29/#30 must verify those capabilities before claiming them; #65 owns deeper free-source research.

Persist a source capability record with source URL, retrieval date, adapter version, rights assessment/reference, coverage period, price/volume basis, action-date semantics, publication-time evidence, membership history and explicit unsupported fields. Preserve source errors and quality flags. Network availability or successful parsing does not upgrade a capability.

Sector history, historical alias intervals, complete delistings, dividend entitlement/payable dates, raw-price reconstruction and point-in-time revisions are **not verified** for the external candidates in this review. Use the restrictions and synthetic acceptance traces in ADR-002. No implicit paid-source fallback is permitted.


## Overnight timing review (Q17,2026-10-28)

Approved Q16 retains verified real-data evidence as a0.0.2 release requirement.
Approved Q17 replaces close-plus15 minutes with one hour before the next pinned
session opens. These are documentation findings, not successful live API checks.
No external data or credentials are committed. The user configured a free Tiingo token locally. Bounded authenticated metadata
and291 ordered daily bars passed response-shape checks on2026-10-28; raw responses
remain in ignored local downloads. Full universe/account capabilities, publication
chronology and application integration remain to be verified under #109.

| Candidate | Primary evidence | Consequence |
|---|---|---|
| Tiingo EOD | [EOD documentation](https://www.tiingo.com/documentation/end-of-day) describes raw/adjusted OHLC and share volume; most US bars arrive17:30 ET with possible later corrections. `divCash` identifies an ex-date, not a verified payable date. [General documentation](https://www.tiingo.com/documentation/) permits software where users supply their own token without redistributing its data. [Pricing](https://app.tiingo.com/pricing/) lists a free personal tier with account limits. | Suitable candidate for overnight diagnostic verification; no retrospective availability, complete action-accounting or live entitlement claim yet. Query current metadata rather than treating reserved directory entries as supported assets. |
| Twelve Data | [US coverage guide](https://support.twelvedata.com/en/articles/9935903-us-equities-market-data) says consolidated daily history arrives after midnight on the next trading day. Its default real-time venues cover only a fraction of US volume. [API docs](https://twelvedata.com/docs) list adjustment modes; separate action endpoints require higher plans. [Terms](https://twelvedata.com/terms) restrict use, caching and redistribution by tier. | The earlier15-minute deadline cannot be justified using the consolidated daily feed. Personal-use/free-plan documentation is not proof that a specific account, price basis or action contract is enabled. |
| Alpha Vantage | [API docs](https://www.alphavantage.co/documentation/) distinguish free compact daily history100 points from premium full/adjusted history. | The free compact response cannot satisfy the default252-session strategy history. No paid fallback is authorized. |
| EODHD | [EOD docs](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes) describe raw OHLC, split/dividend-adjusted close, split-adjusted volume, US updates within15 minutes and free-plan history/request limits. | Update timing is not proof of local ingestion by the cutoff. Split-adjusted volume cannot be relabeled raw shares; a supported conversion would require its own evidenced method. No acquisition or permission claim is made. |

A new adapter must prove bounded source-derived universe selection, venue/type
identity, price/volume basis, explicit sector evidence, complete declared coverage,
pinned calendar lookahead, provenance and safe errors. Historical downloads use
observed availability and cannot populate an earlier cutoff by assumption. Keep
unsupported execution/action capabilities blocked and never substitute fixtures
for absent research data. Live integration and its ADR belong to the0.0.2 release
integration work; this timing correction does not enable an unverified provider.
