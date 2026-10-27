---
name: ship
description: Carry a YAMS issue or scoped change through implementation, verification, PR review, and merge when authorized. Use when the user asks to ship work or invokes $ship; honor requests to stop at a draft or review-ready PR.
---

# Ship

Adapted from the `/ship` workflow in `mergewatch.ai`. Deliver the requested outcome with evidence, a maintained checklist, and a reviewable diff. Read the repository's `AGENTS.md` and relevant strategy documents first.

## Scope and authority

Accept an issue URL/number or a concrete description. If neither the invocation nor conversation identifies the work, ask what to ship before changing anything.

An explicit request to use this skill to ship a change authorizes task-related commits, branch pushes, PR creation, one maintained issue tracker comment, review replies, and merge after the gates below. Honor narrower instructions such as “draft only” or “open a PR.” Automatic selection of this skill for an ordinary coding request does not itself authorize publishing, commenting, or merging; complete local work first and obtain any missing authorization before those actions. Do not ask again for actions already authorized.

Never force-push shared branches, bypass branch protection, weaken checks, delete persistent data, or expand into cloud deployment. YAMS is a local application. This skill does not install a persistence hook or create an automatic goal; do not claim it will keep running after the session stops.

## 1. Establish the actual task

- Inspect the working tree, branch, remotes, applicable instructions, and available tooling. Preserve unrelated edits and untracked files.
- For an issue, read its body and comments. Verify its claims against the current code before adopting them as requirements. Separate verified acceptance criteria from suggestions and outdated claims.
- Identify the target repository and base branch from configuration; do not assume an owner or copy MergeWatch's repository names.
- State the intended outcome and measurable acceptance criteria. Resolve material architecture questions through the project's ADR process before dependent work.

## 2. Keep a living plan

Maintain a checklist of concrete implementation and verification steps using available task tools or a local plan. For an authorized issue workflow, mirror it into one tracking comment and edit that same comment as work progresses. Record its ID; never edit another author's comment or guess the target with “edit last.” Use structured tool arguments or a UTF-8 body file for multiline GitHub content.

Prefer one focused PR. Use a dependency-ordered stack only when the scope benefits from it; each phase must be independently reviewable and testable. Track phase dependencies, PR links, and actual completion. Only the final PR should close an issue spanning multiple phases.

## 3. Implement and verify

Create or reuse a task branch before committing; never commit directly to the default branch. Implement the smallest complete solution consistent with existing patterns and YAMS invariants. Stage named task files only.

For a bug fix, demonstrate the regression test failing against the prior behavior when practical, then passing with the fix. Use an isolated worktree or temporary copy if necessary; do not stash, reset, or revert the user's working tree to manufacture failure evidence. Distinguish a reproduced regression from a new behavior test or an additional guard.

Every financial-code change requires deterministic fixture tests and an inspectable example. Exercise the affected time, ledger, allocation, execution, or forecast invariants specified in `AGENTS.md`. Do not weaken assertions merely to make the suite pass.

Discover real validation commands from manifests, scripts, and CI. Run applicable formatting, lint, type, test, build, and contract checks separately where required. Exercise migrations and restart persistence for durable-state changes; exercise the relevant user journey and offline fixture path for application changes.

The initial repository contains planning documents only. Do not invent pnpm commands, a test harness, deployment workflows, or successful checks. Documentation changes require content/link/diff review. If implementation needs missing infrastructure, build the necessary foundation within scope or report the gap as a blocker.

## 4. Publish and address review

After local gates pass, inspect the complete diff, commit, push, and open the authorized PR. Describe the problem, resulting behavior, verification evidence, assumptions, limitations, and issue/stack relationship. Never copy another model's co-author identity.

Monitor checks for the current PR head commit. Read review findings as well as check conclusions: a successful check can still contain unresolved concerns. Use whatever review services are actually configured; MergeWatch is not assumed to be installed.

Verify each finding against the code. Fix valid findings, explain disagreements with evidence, and rerun affected checks after changes. Update the single tracker with completed work and PR links. Avoid repeated review-trigger comments or unrelated fixes.

If CI fails, diagnose before retrying. Retry an unchanged run at most once for a demonstrated transient infrastructure failure. Persistent failures, unavailable required review, credentials, or unmet branch protections are blockers; report the precise condition rather than bypassing it or polling indefinitely. Keep waits bounded and provide progress updates.

## 5. Merge and verify the delivered state

When merge is authorized, all required checks must pass for the latest head, required reviews must be satisfied, and material findings must be resolved. Use the repository's allowed merge method and auto-merge if available. Recheck status immediately before a direct merge. Enabling auto-merge is not proof that a PR merged.

Confirm the merged commit and any configured post-merge checks. For runtime changes, verify the applicable local Docker/fixture smoke journey against the merged state without disturbing user work or resetting volumes. Report missing runtime verification honestly; there is no cloud production deployment milestone for YAMS.

For a stack, advance in dependency order and update subsequent branches safely after merges. Close the issue only when the complete acceptance criteria are met. Do not mark deferred work complete.

## Completion report

Report the PR link(s), merge status/commit when applicable, checks actually run and their results, review disposition, and local smoke-test result. Distinguish passed, failed, skipped, unavailable, and no applicable tests. Include any remaining blocker and the next required action.

“Shipped” means the requested scope is delivered and the authorized endpoint is verified. A local patch, an open PR, and a confirmed merge are different states; name the actual state.
