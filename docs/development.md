# Development and continuous integration

Use the pinned Python, uv, Node and pnpm versions in the repository manifests.
`make install` installs locked dependencies. See [local operations](operations/local-compose.md)
for `make dev`, Docker startup and data-preserving shutdown.

## Required validation

`.github/workflows/ci.yml` runs on every PR targeting `main` and every push to
`main`. PRs test GitHub's candidate merge commit; pushes test the actual merged
SHA. Each job retains its tested SHA, logs and available browser/runtime evidence
for 14 days. Uploaded paths exclude environment files and credential directories.

- Quality: `make lint typecheck test contracts-check fixtures-check build`, then
  `make test-e2e` with Playwright Chromium. Separate type commands remain in Make.
- Runtime: `make test-integration` and `make smoke`, with isolated Docker volumes,
  migrations, offline fixture/browser checks and persistence after restart.
- Documentation: `python3 scripts/ci.py docs` checks nonempty/conflict-free Markdown
  and local inline file links. External URL availability and heading anchors need
  review; this checker does not claim to validate them.

Changes consisting only of `README.md`, `AGENTS.md` or Markdown under `docs/`
explicitly make quality/runtime jobs not applicable. All other changes, unknown
bases and empty change sets require runtime checks. The workflow itself has no
path filter. `CI / required` always evaluates dependency results: any applicable
failure, cancellation or unexpected skip fails the aggregate. An interrupted
whole workflow cannot supply a successful required check. Unit tests exercise
the result matrix. Superseded PR runs are cancelled; main runs are retained.

Actions are pinned to full upstream commit SHAs. Repository permissions are
read-only, checkout credentials are not persisted, jobs have timeouts and no
publishing secrets or provider credentials are passed. Shell pipelines use Bash
pipefail so retained logs cannot hide a failed command.

## Delivery evidence

Issue [#26](https://github.com/santthosh/yams/issues/26) records controlled failure,
passing PR and merged-main runs. Workflow presence alone does not establish CI
delivery. Issue #27 owns enforcement of the actual emitted required-check names;
issue #28 owns release publication and exact-source verification.

References: [GitHub workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax),
[artifact retention](https://github.com/actions/upload-artifact),
[uv setup action](https://github.com/astral-sh/setup-uv).
