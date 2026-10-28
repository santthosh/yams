# Local Tiingo diagnostic workflow

This optional path uses the user's own personal-use token and provider account.
Default offline startup needs neither a token nor network access. The current
contract is [ADR-010](../adr/0010-free-research-provider.md); all capital and orders
remain synthetic. Diagnostic support does not authorize paper posting or assert
complete corporate-action accounting.

## Configure and start

Create/edit the repository-root `.env` with `TIINGO_API_TOKEN=your_personal_token`.
Preserve existing configuration, restrict the file with `chmod 600 .env`, and keep
it out of Git, screenshots and browser variables. Then use the explicit override:

```sh
docker compose --env-file .env -f compose.yaml -f compose.research.yaml up --build -d --wait
```

The override injects the token and adds the research egress network only to the
worker. API/PostgreSQL remain on the internal network. Web retains its existing
ingress network and is the only service published on loopback. Normal
`compose.yaml` uses offline fixture data and injects no provider token.
Do not publish `docker compose config` output from a credential-enabled project.

In Settings → Market data, choose Market research data and enter this closed
configuration in Research source configuration, then refresh:

```json
{
  "schema_version": 1,
  "provider": "tiingo_eod",
  "rights_verified_local_use": true,
  "history_sessions": 400,
  "max_assets": 20
}
```

The local-use assertion must match the operator's actual account/terms. No token
belongs in that JSON. The API pins the configuration in a durable refresh job;
poll the real job status. A failed refresh leaves prior snapshots intact. Open
Candidate inspection after successful publication, select the research snapshot,
published strategy and covered as-of session, and evaluate pinned inputs. Repeating
an evaluation reuses its snapshot evidence and does not reacquire provider data.

## Data and timing limits

The versioned `tiingo_us_stock_hash20_v1` rule samples a bounded cohort from the
source directory, verifies current active/non-ADR primary stock identity, source
sector and history coverage, then fetches every selected instrument. The initial
hard cap20 is a visible free-account budget restriction, not complete US coverage
or a handpicked portfolio. Missing/unsupported metadata is excluded with evidence;
if the fixed candidate bound cannot supply the requested count, refresh fails.
Default400-session history is adjustable within252–2000. Optional `as_of_session`
must be an actual completed XNYS session. No guessed weekdays or holiday bars.

Acquisition retains exact source bytes/hashes and observed times in private
immutable artifacts. Raw OHLC/share volume are separate from adjusted-close
features. Current-only membership and metadata carry survivorship limitations;
received historical rows do not establish historical publication times.

The approved cutoff is one hour before the next pinned session opens. A real
evaluation cannot run before that instant, and only evidence available by it is
eligible. Downloading historical data after a cutoff cannot backdate its use.
An initial late setup may therefore require the next supported decision window;
cash-only/unavailable results must remain explicit. Synthetic offline examples
remain available separately and are never substituted into research results.

Missing credentials, denied endpoints, rate limits, malformed/partial data,
unknown identities or missing calendar coverage fail with safe fixed reasons.
A typical20-name refresh requires about41 API calls; actual account quotas apply.
Avoid repeated refreshes when the existing snapshot suffices. No paid upgrade,
subscription change, source repair or quota bypass happens automatically.

`supports_diagnostics=true` does not mean complete action accounting. Provider
split/dividend observations retain limitations; an ex-date never becomes an
invented payable date or cash entitlement. Portfolio/backtest services must reject
unsupported capabilities. No portfolio, order or ledger effects occur here.

Downloaded prices, metadata, response evidence and real screenshots remain in local
ignored artifact/download directories. Public tests/images/releases contain code
and explicitly authored synthetic fixtures only. Do not redistribute cached data.
