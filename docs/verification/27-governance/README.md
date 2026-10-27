# Governance verification

Issue #27; implementation PR #95 and controlled evidence PR #96.

## Active policy

Main protection was applied and read back through the GitHub API. The versioned
payload is `infra/github/main-protection.json`; the read-back is
`docs/verification/27-governance/protection.json` in PR #95. Required contexts are
`CI / required` from GitHub Actions app 15368 and `MergeWatch Review` from app
3052814. Current base, PRs, conversation resolution and linear history are
required. Administrators are included; force pushes and deletion are disabled.
Q05 requires no separate human or CODEOWNER approval. CODEOWNERS routes changes
to actual repository maintainer @santthosh.

## Controlled blocked merges

Both calls used the normal merge endpoint, exact expected head and squash method,
with the repository owner's existing credentials. No admin bypass was requested.

| Case | Exact PR head | Result |
|---|---|---|
| PR #95 while CI and review were outstanding | `0e11924ace9a7a29e1e324207a61fc3c984eae1b` | HTTP 405: Required status check "CI / required" is expected |
| PR #96 after deliberate documentation failure | `4ca2fe81b2c34fc5e6e86b20053ab2c96bf8f2fa` | HTTP 405: Required status check "CI / required" is failing |

[Red probe run 40605031011](https://github.com/santthosh/yams/actions/runs/40605031011)
failed docs and required after a deliberately missing local file link. Runtime
was explicitly not applicable. The probe link is removed from this final record.
No runtime behavior or operator data was changed for this test.

## Review enforcement

GitHub accepts neutral required checks, and MergeWatch can emit neutral while a
review is in progress. The CI guard in PR #95 therefore checks the exact source
head, latest check ID and verified app ID, and requires completed SUCCESS for
code changes. Only the exact configured "Only docs changed" neutral skip is
accepted for verified docs-only changes. Tests reject missing/stale/wrong-app,
pending, failure, draft-skip and a newer pending check following old success.
Conversation resolution remains a separate server-enforced requirement.

MergeWatch reviewed implementation head `0e11924ace9a7a29e1e324207a61fc3c984eae1b`
with SUCCESS, 5/5 and no findings. Local lint, strict typing and 154 Python tests
passed. Hosted current-head and merged-main runs, the allowed normal merge path,
and final read-back are recorded in #27 before closure. No destructive force-push
or deletion probe was attempted; those restrictions were inspected in settings.

Reference: [GitHub required-check semantics](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks).
