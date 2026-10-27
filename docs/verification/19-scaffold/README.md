# Scaffold verification — #19

Verified on 2026-10-27, macOS arm64, Python 3.13.12, uv 0.8.0, Node 22.17.0 and pnpm 10.23.0. These are native scaffold checks, not Docker or release-platform proofs.

| Check | Observed result |
|---|---|
| `make install` in a fresh `/tmp/yams-scaffold-19-*` copy without virtualenv/node_modules | Locked Python and pnpm installs succeeded; pnpm skipped dependency resolution |
| `make lint` | Ruff check/format and ESLint/Prettier passed |
| `make typecheck` | Strict mypy and separate Next typegen/TypeScript passed |
| `make test` | 2 API tests and 1 UI render test passed without DB/provider credentials |
| `make build` | Python sdist/wheel and production Next build passed in the clean copy |
| Deliberate negative probes in temporary copy | Unused Python import, Python type mismatch, unused TS variable and TS type mismatch each caused its respective Make target to exit nonzero; probes removed afterward |
| Production browser smoke | Chromium at widths 1280 and 390: HTTP 200, one h1, no horizontal overflow or browser errors; Tab did not trap/crash the static shell; unknown route returned 404 |
| Visual review | [Desktop](desktop.png) and [mobile](mobile.png) screenshots inspected; paper-only scope and unavailable results readable |

The clean source build exposed an overly broad sdist default; explicit includes now restrict the Python distribution to backend sources and build/lock metadata. The corrected clean build passed. Vitest's current configuration rejected an obsolete esbuild option during typing; removing it retained automatic JSX from tsconfig and both typing/render tests passed.

Known warning: Starlette's TestClient currently emits a deprecation warning for its supported httpx transport. Tests pass; this is not a suppressed test failure. Full API error envelopes, DB readiness, fixture loading, persistent settings, worker execution, Docker smoke, automated browser journeys and CI remain with their assigned foundation issues. The static shell has no interactive controls, financial state or data-provider connection to test.
