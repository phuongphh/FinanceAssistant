# Issue #1073

Remove migrated shared Loop Engineering core from product repository

The shared controller and schemas are installed from the merged private fleet-engineering platform (0.2.0). FinanceAssistant still carries about 5,799 lines of duplicate Python controller/tests, CI references to their requirements, stale local invocation docs, and Docker COPY includes controller code.

Maintenance scope:
- Remove the migrated scripts/delivery Python core, its duplicate Python contract tests, copied shared schemas/examples and obsolete .github/delivery.json policy snapshot.
- Retain product-specific Node publisher/Projects regression tests, the named contract CI job, existing legacy agent-loop compatibility and protective forbidden paths.
- Stop application/legacy worker CI from installing the removed requirements; shared Python tests are maintained and run by platform CI, not silently skipped.
- Point operational references to the shared platform and retain Finance-specific delivery semantics. Prevent controller/legacy coding infrastructure from entering application image context.

Acceptance: no remaining executable dependency on removed paths; required Finance pytest, review and product contract checks pass on the exact PR head; application source, migrations, runtime state, deployments and secrets are unchanged. No shared platform code is reintroduced as a product shim.

This is authorized extraction maintenance, not a local coding task or deployment approval. Do not set agent:ready. Stop at a maintenance PR for owner review/merge.
