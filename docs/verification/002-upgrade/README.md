# 0.0.1 → 0.0.2 upgrade verification

The isolated project in `evidence.json` installed the published, checksummed 0.0.1
bundle, set a nondefault locale and labeled synthetic preferences, recorded the workspace JSON and wrote a labeled synthetic artifact. It
stopped the old application without deleting volumes, then started the prepared
0.0.2 application on the same project-scoped stores. Actual migrations advanced
from `0002_jobs` to `0004a_evaluations`. The workspace identity/preferences and artifact
were unchanged; health and the new immutable strategy seed were verified. Only
that randomly named test project's resources were removed afterward.

This is a local arm64 source-image upgrade proof against commit `c33b8ba`. It is
separate from the required final merged-source native amd64/arm64 anonymous
packaged-install checks. No provider data or credentials are present in this proof.


Settings and Dashboard screenshots are from a separate fresh offline-only project,
verified at360/1280 widths after the copy correction. They contain authored
synthetic fixture metadata, no provider data or credentials. They show the current
application version, snapshot/research guidance and honest later-feature states.
