# Strategy Lab: inspect, edit and publish (#73)

The development source for 0.0.3 adds the browser workflow at `/lab/strategies`;
`/lab` redirects there. Open **Strategy Lab** from desktop or mobile navigation.
Published 0.0.2 bundles remain immutable and retain their earlier capabilities;
source implementation does not itself establish a 0.0.3 release.

## Work from a saved version

1. Inspect a stock template or named fork. More strategies and older version pages
   load explicitly; every version has its own ID, ordinal, complete rules and
   backend config hash. SPY remains benchmark-only, with no publishable card.
2. Choose the source version to inspect or copy. The default is the latest; an
   earlier version keeps its original content. Selecting another source replaces
   unsaved edits, as labeled beside the selector and form.
3. Edit supported fields for that family. Choose another template to work with
   another family. The closed family/operator, inverse-volatility allocation,
   monthly rebalance and execution-policy constants remain inspectable in the
   complete rules. There is no arbitrary-code field or editable backend draft.
4. Review the before/after changes. Fraction inputs use `0.20` for20%; a displayed
   config difference is not a forecast or computed portfolio. Representation-only
   trailing zeros do not change a decimal rule. The backend owns final validation,
   canonical bytes and hashes; the browser computes no allocations, returns or
   money ledger. Required history must cover lookbacks, and momentum score weights
   must satisfy their existing contract.
5. **Publish new version** appends under the same strategy identity. **Create named
   fork** creates a separately named strategy with an initial version. Its metadata
   name can differ from the rule display name. Both publish only on explicit form
   submission; original records remain inspectable and portfolio bindings/holdings
   do not change. Identical config can still create a new immutable version.

Only actual saved server responses supply IDs, ordinals and config hashes. Unsaved
form edits remain local. History reloads retain current edits and temporarily
disable publication while source/history availability is checked. Empty registry,
missing history, unavailable storage, validation and duplicate-name failures have
explicit states and retry controls. Errors preserve the current form values.

If a publication response is lost or unconfirmed, **inspect saved strategies and version history before
trying again**. Reload strategies to find an unconfirmed named fork, or reload
its version history for an append. Strategy publication has no idempotency key: a retry could append
another version. No automatic retry is performed. A fork name conflict asks for a
different name; no existing strategy is renamed or overwritten.

The page needs saved rules, not current market data. It links to existing candidate
inspection for data-derived diagnostics; public experiment submission/reporting
belongs to #74/#41 and comparison/challenge to #43. Unsupported actions are staged
honestly rather than represented by fabricated results.

## Verification and implementation boundary

Generated TypeScript types and the existing bounded same-origin proxy carry
complete config; decimal amount/weight lexemes stay strings. Only bounded integer
and statistical JSON-number fields are converted for transport. Field validation
and representation comparison do not implement portfolio math. The backend remains
the authority for cross-field/range/financial validation and immutable publication.

Unit checks cover exact decimal transport, supported family fields, immutable
source configs, numeric display-name semantics and lossy-number rejection.
Production browser scenarios cover typed fork/append payloads, original version
inspection, both pagination controls, invalid inputs,422/409/unconfirmed failures,
retained drafts after history reload, empty/missing states, keyboard/mobile and
accessibility. The offline Docker browser journey additionally creates and appends
real mean-reversion/low-volatility forks and verifies all versions through actual
restart/rebuild. Native release smoke uses the same journey when its owner runs
it; source proof does not claim release publication or platform verification.
