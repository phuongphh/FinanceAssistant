# Issue #1065

[Fleet] Ask PO to approve Dev deployment after application PR merges

## Problem
The PM monitor's merged notification says no action is needed and does not ask for Dev approval. It also discovers only open PRs, so a PR created/merged between polls can be missed.

## Outcome
For application changes, send one explicit Dev-approval question after an actual GitHub merge, persist the fixed merge SHA/Dev environment and pending decision, and let an authorized PM session record the PO's reply before handing off to Op Dev. Discover recent merged PRs as well as tracked/open ones. Do not request application Dev deployment for docs/controller-only changes.

## Acceptance
- One clear question with a PR-specific reply, durable dedup and immutable version/environment.
- Open/provisional merge SHA cannot create a deployment request.
- Recent unseen merges are discovered; previous generic merged notices can upgrade once.
- Matching authorized-session decisions are idempotent and never deploy automatically.
- No live merge/deployment performed for this fix. Existing #1054 is currently open; #1064 is controller maintenance, not an application deployment.

Explicit maintenance authorized by current user request; do not label agent:ready.
