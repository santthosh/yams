# Issue #24: accessible foundation shell and transport

The implemented routes are Dashboard (`/`) and read-only Settings (`/settings`).
Lab, Portfolios, Arena and Journal stay hidden until functional. The global shell
shows Paper only, source mode, source as-of and last-checked job status. No
portfolio, market rank or investment result is seeded into the UI.

## Interfaces and handoff

- App Router files live in `apps/web/src/app`; the earlier `apps/web/app` scaffold
  was moved as one change. Root layout owns workspace state and the responsive
  shell. Generated client imports remain in `src/api/generated`.
- `WorkspaceProvider` fetches health and workspace through the generated client.
  Loading, not-ready and transport errors are distinct. A successful health read
  does not hide a failed workspace read. Refresh retries explicitly.
- `src/lib/proxy.ts` is used only by the server route. `API_INTERNAL_ORIGIN` defaults
  to `http://api:8000`, or `http://127.0.0.1:8000` for native development. Do not
  prefix it with `NEXT_PUBLIC_`. The browser uses only its own origin.
- The proxy permits GET health/workspace and GET job UUIDs. Other destinations,
  methods and query strings fail before fetching. Credentials/cookies and upstream
  Set-Cookie headers are not forwarded. Redirects fail; the timeout is three
  seconds including response-body reads. Non-JSON/transport/upstream failures
  become safe correlated errors; health's documented not-ready shape is retained.
- Job lookup uses a known UUID and the generated `JobV1`. Active jobs poll every
  two seconds; terminal states stop polling. Leaving the page aborts/cleans up
  polling, and transport failure stops automatic retries until another lookup.
  A global last-checked state is not a claim that the whole queue is idle.
  No enqueue, cancel or rerun control is exposed.
- `components/evidence.tsx` owns `Money`, `Quantity`, `ReturnPercent`, provenance,
  warnings, version identity, empty/error and job components. Props refer to
  generated contracts. Decimal-string formatting uses BigInt scaling/grouping;
  it never converts a whole monetary/quantity value to binary float. Display-only
  rounding is half away from zero; no allocation, valuation or forecast math is
  performed. USD displays two decimals, quantities up to six, percentage fractions
  up to two. Null/invalid values are `Unavailable`. Locale controls separators.
- Tailwind 4.3.3 supplies tokens/utilities. Locally owned shadcn-style Button uses
  Radix Slot/CVA; the modal uses Radix Dialog's focus management. `components.json`
  records the local baseline. No chart dependency or remote font is loaded.

Relevant primary documentation: [Tailwind PostCSS integration](https://tailwindcss.com/docs/installation/using-postcss),
[shadcn components](https://ui.shadcn.com/docs/components/button), and
[Radix Dialog](https://www.radix-ui.com/primitives/docs/components/dialog).

## Verification

Verified on 2026-10-27, macOS arm64, Node22.17.0/pnpm10.23.0, Next16.4.3,
React19.3.1, Playwright1.64.1 with Chromium and axe-core/playwright4.14.0.

- `pnpm install --frozen-lockfile`: passed with exact dependency pins.
- `make lint typecheck test contracts-check fixtures-check build`: passed;
  149 Python tests, 42 web tests after the partial-workspace-read regression fix,
  all 23 synthetic fixture files, generated client/contracts and production builds.
  The affected web lint/type/test/build gates were rerun after final UI changes.
- `make test-e2e`: ten production-build browser tests, five each at 1280×900 and
  360×800. Covers keyboard skip link/navigation, visible focus, mobile menu,
  modal focus trap/Escape/return, generated job polling and missing-ID state,
  initial loading, actual three-second server-proxy timeout and recovery,
  not-ready checks, sanitized upstream error and useful 404.
- Browser assertions verify no horizontal overflow on Dashboard, no JavaScript
  page errors in the navigation journey and no browser requests to the internal
  API or another origin. Proxy unit tests separately enforce the allowlist and
  credential/header boundary.
- Automated accessibility scans for WCAG2A/AA, WCAG2.1AA and WCAG2.2AA tags run on
  Dashboard, Settings and the open modal at both widths. They found navigation
  marker contrast during development; the colors were corrected. No violations
  remained in the final scanned states. This is scoped automated/keyboard/visual
  evidence, not a claim of comprehensive accessibility certification.
- Formatting cases include `9007199254740993.01` → `$9,007,199,254,740,993.01`,
  six-decimal large quantities, negatives, null, malformed values, German locale
  and `0.20` → `20%`. Provenance tests distinguish synthetic, research, stale and
  unavailable. All six job states are checked without a fake successful result.

The web regression for successful health plus failed workspace first failed
because no alert was rendered, then passed after readiness was corrected. The
first browser selector failure involved Next's separate route-announcer alert;
assertions now scope to the application's main region without suppressing either
alert. Standard upstream Starlette/httpx and Playwright color-environment warnings
remain visible; none are presented as test failures or silently disabled.

## Controlled transport and screenshots

`apps/web/tests/transport-fixtures.json` is explicitly SYNTHETIC_DATA_ONLY. Fixture
metadata comes from the committed synthetic snapshot; workspace/job IDs and job
transitions are controlled transport examples, not persisted records or market
results. Its snapshot hash is
`fb8a7f7765a98040ec0c004d73d86bb2be262a3811d86626a2f04c1c11396502`.

The test-only server runs on loopback3118 and production Next on loopback3117;
set `YAMS_E2E_API_PORT` / `YAMS_E2E_WEB_PORT` if those ports are occupied. Existing
servers are never reused. Playwright owns/cleans up these processes. The control
route is not application code and is rejected by the production proxy. Browser
binaries require one initial `pnpm --filter @yams/web exec playwright install chromium`.

Screenshots were visually inspected for wrapping, overflow, source labels,
responsive stacking, error visibility and modal focus:

- [Desktop Dashboard](dashboard-desktop.png)
- [Mobile Dashboard](dashboard-mobile.png)
- [Mobile Settings](settings-mobile.png)
- [Mobile modal](dialog-mobile.png)
- [Mobile timeout/error](timeout-mobile.png)
- [Mobile loading](loading-mobile.png)

Additional screenshots, failure traces and the HTML report are kept under ignored
`apps/web/test-results/e2e` and `apps/web/playwright-report` when the suite runs.

## Boundaries

This suite exercises the real Next proxy against a controlled local HTTP server.
It does not prove four-service Docker startup, persisted PostgreSQL workspace
identity across app restarts, aggregate resource responsiveness or packaged image
installation. Those remain #25–28; the existing backend/PostgreSQL evidence is
unchanged. No database migration or financial engine changed in #24. Settings
mutation, provider selection, financial routes and public cancellation remain
with their owning later issues. No release is claimed here.
