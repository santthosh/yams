# ADR-008: Progressive first-run behavior and API ownership

Status: proposed for review in [#11](https://github.com/santthosh/yams/issues/11); accepted when its contract PR merges.

## Context and decision

First-run prose originally required recommendations and Journal behavior before their implementation milestones. Optional editable-draft wording also conflicted with immutable versions. The API document owns transport; the blueprint owns financial semantics; UX owns presentation. Preserve FR-01–FR-15 and the complete 0.0.5 core gate while delivering the increments below. Illustrative technology examples do not create competing contracts.

## First-run increments

| Release | Available journey | Staged capabilities |
|---|---|---|
| 0.0.1 | Four local services, singleton workspace, labeled fixture metadata, accessible shell, health/basic settings and restart persistence | No computed ranks, persisted strategy registry, experiments, portfolios, recommendations, fills or Journal outcomes |
| 0.0.2 | Select snapshot/default strategy; inspect computed eligibility, ranks, evidence and feasible targets | No account recommendations or posting |
| 0.0.3 | Publish/fork versions, run/cancel experiments, inspect reports and comparisons | No interactive paper approval flow |
| 0.0.4 | Create cash-only account, inspect valuation/ledger and durable batch services | Pending/fill browser states use labeled service fixtures until public approval in 0.0.5 |
| 0.0.5 | Recommendation → forecast → review → approve → pending → eligible fill → restart, plus historical experiment evidence | Journal maturity and optional later features remain staged |
| 0.0.6 | Prospective Arena with independent frozen entrants | No fabricated retrospective participation |
| 0.0.7 | Immutable original decision beside matured outcome and counterfactual | No rewriting original forecasts |
| 0.0.8 | Visual/manual authoring and optional opt-in AI proposals | No executable model output or automatic publication |
| 0.0.9 | Full diagnostics, consistent backup/restore, exports and approved historical-source hardening | No unapproved paid source or hosted application runtime |

Foundation fixtures are inputs, expected-value tables and contract examples, not fake persisted experiments or account state. #20/#22 expose fixture metadata through workspace/health contracts; the later data API is not pulled forward. Hide unavailable navigation/actions; explanatory roadmap copy is allowed without inert buttons. No signup, broker, real-money or cloud runtime is introduced. Builds may download dependencies; packaged fixture operation must work offline.

## Immutable publication

V1 creates published immutable strategy versions directly. Unsaved UI edits are local form state; publication creates a new identity and canonical config hash. There is no editable draft backend or update-in-place version endpoint. Existing references stay pinned. Strategy metadata is distinct from versioned config; no metadata-update route is introduced here.

Strategy names are trimmed, 1–120 characters, contain no control characters, and are unique within the singleton workspace under Unicode casefold comparison. Invalid names return `422 VALIDATION_ERROR`; duplicates return `409 STATE_CONFLICT`. #36 enforces normalization and concurrency-safe uniqueness; #71's initial registry follows the same rules. Display labels inside config are not separate unique strategy identities.

## Diagnostic evaluation

API §6.1 defines the two `/strategy-evaluations` routes owned by #34 in 0.0.2. They compute candidate/allocation evidence through the worker without portfolio, recommendation, forecast or ledger writes. #20 generates schemas; #34 implements handlers/UI. Empty eligible universe is a legitimate cash-only result. This fills the research inspection gap without depending on 0.0.5.

## Deferred lifecycle contracts and handoffs

Each owner below must ratify method/path, complete request/result schema, state and concurrency/idempotency behavior, errors and generated-client tests **before exposing the action**. These rows assign responsibility, not functioning endpoints.

| Operation | Owner / release | Required boundary |
|---|---|---|
| Dismiss recommendation | #50 / 0.0.5 | Change disposition only; retain original content/cutoff; no posting; truthful stale/terminal race response |
| Cancel unposted orders | #50 transport, #12 policy, #46 service / 0.0.5 | Serialize against posting; never reverse a posted fill to simulate cancellation |
| Recover approval after response loss | #50 / 0.0.5 | Same key/payload retrieves original durable result; define lookup before UI use; changed payload conflicts |
| Cancel background job | #23 internal, #41 public / 0.0.3 | Cooperative cancellation and sealed-output rules; #31 hides cancel until public endpoint exists |
| Arena launch/pause/resume/promotion | #54 contract, #55 service, #56 UI / 0.0.6 | Q08 launch authorization is scoped to frozen competition; promotion preserves history and does not rebind unrelated portfolios |
| Full settings/diagnostics mutations | #64 / 0.0.9 | Bounded local values, secret redaction, atomic persistence; #24 supplies only foundation presentation |
| Backup/restore/reset | #63 / 0.0.9 | Consistent DB/artifact closure, validate before activation, explicit reset separate from startup; #28 still supplies early manual backup/upgrade guidance |
| Evidence export | #70 / 0.0.9 | Bounded managed-artifact selection, provenance/rights checks; export is not full backup |
| Additional strategy operators | #37 / 0.0.3 | Formalize Q07 formulas/defaults and independent fixtures before #38 implementation |
| Optional AI proposal lifecycle | #76 contract, #62 implementation / 0.0.8 | Q10 opt-in, minimized selected rules/metrics, closed config validation and explicit publication |

API §6 inventories every existing route plus candidate diagnostics with response, release and primary implementation owner. Parent epics and this ADR do not create runtime dependencies on later milestones.

## Verification and consequences

Review the route inventory for unique method/path pairs and preservation of all original routes. Compare staging with every milestone exit and UX test journey. No runtime test or financial computation is claimed by this document-only change. Implementation tests must prove immutable history, duplicate-name conflicts, diagnostic empty/failure states and truthful staged UI. Later contract owners coordinate API, client, docs and tests instead of inventing isolated UI endpoints.

## Public paper lifecycle ratification (#50)

[ADR-015](0015-public-paper-controls.md) specifies the concrete apply, keyed
recovery, dismiss, batch inspection, cancel and explicit fixture-step contracts.
It preserves the policy/service ownership above and separates actual operator
audit from durable synthetic replay. The generated OpenAPI exposes only implemented
methods; scheduling and Decision Center screens remain separately owned.
