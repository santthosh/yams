# 0.0.1 release verification

Implementation for #28. Publication and platform installation evidence remain pending;
this report does not claim that a release exists.

## Tag policy

Live GitHub ruleset readbacks are committed as [creation](tag-creation.json) and
[immutability](tag-immutability.json). Version tags allow creation only through the
repository administrator role. Updates and deletion are blocked with no bypass
actors. GitHub rejected the built-in Actions integration as a creation-rule actor
(HTTP 422), so a verified main dispatch precedes administrator tag creation. The
tag run independently revalidates source CI and native installations before
publishing. Main branch CI/review protections remain active.

## Local checks

`make lint typecheck test contracts-check fixtures-check` passed: 159 Python tests,
42 web tests, strict Python/TypeScript checks, unchanged generated contracts and
23 deterministic synthetic fixture files. Five release tests cover exact main CI,
duplicate/conflicting versions, immutable image references, both native platform
evidence requirements and a real disposable Git branch outside main history.

The packaged Compose renderer was checked with explicitly dummy digest inputs and
`docker compose config --quiet`; it contains no builds, fixed volume/network names,
or published API/database ports. This is rendering evidence, not image installation.

## Required hosted evidence

Pending: current-head MergeWatch/CI, main CI, native candidate builds, anonymous
packaged installs on amd64/arm64, offline browser/job journey, retained workspace
and artifacts after restart, draft recovery, final release asset checksums and
public digest access. The release workflow stores candidate and verification
artifacts for 30 days; final release evidence is included in the release assets.
