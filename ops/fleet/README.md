# Finance Production application tasks

This product owns the `pro_tasks.py` adapter. The shared `fleet-engineering` platform owns signed requests, immutable receipts, durable task journaling and PM notifications. Ordinary coding workers cannot edit this maintenance path.

The VPS owner installs a verified bundle with one explicit host binding: the existing Finance checkout, Compose project/container identities, Postgres data volume, private backup destination and the immutable adapter hash. Task parameters cannot change a path, container, URL, command or SQL statement. The executor runs as the existing application operator; no SSH key moves to the Mac and no Docker socket is mounted into an LLM agent.

Supported operations:

Git reads use a private temporary metadata view with a fixed, secret-free config.
It references the current index/refs/objects and reads only the current HEAD
value, so a later release is observed without caching an old checkout. The
source `.git/config`, hooks, permissions and credentials are untouched. This
supports the VPS layout where the checkout belongs to the operator but
`.git/config` is root-owned mode 0600. No safe.directory wildcard, root Git
service, chmod/chown or credential migration is needed. The installer root checks
only the configured origin identity in memory; the operator never receives it.
Only rev-parse, status, ls-tree and cat-file are exposed to the fixed adapter.
Git data (HEAD/index/refs/objects) must already be readable by the operator, and
the owner-installed scratch directory must be private. Linked/symlink Git
directories and unsupported modes remain blocked.

- `inspect`: checkout/branch/dirty metadata, registered service identities, migration revision, loopback health and running-container Python source hashes compared with the checkout. Checkout SHA alone is not runtime evidence. No customer SQL is returned.
- `backup`: requires the exact observed checkout baseline, rechecks it after taking the same `/tmp/rebuild-finance-prod.lock` used by deployment, checks the registered Postgres volume and creates a bounded private `pg_dump --format=custom` archive. Nonzero/timeout/invalid/unreadable output is not a valid backup. No existing backup is removed or overwritten. Receipt includes only private reference, size, checksum and verification metadata. `pg_restore --list` is a format/readability check, not a full restore rehearsal.
- `verify`: requires the candidate checkout SHA, a clean tracked tree, healthy/running services and matching backend/scheduler Python source hashes. It does not claim the admin/bot user journey has been exercised or that a release approval exists.

No deploy, migration, restart, restore, downgrade, cleanup, arbitrary shell, arbitrary SQL or broadcast is exposed. Existing approved release PR → `prod` → GitHub Actions deploy remains the deployment path. PM uses preflight/backup receipts before executing an owner-approved merge and post-release verification afterward; a successful task receipt is not itself a release receipt or PO acceptance. Corporate Production stays with its existing external owner.

Before exposing capabilities, run the separate host installer, verify the actual task service, return the public registration/fingerprint to the owner for PM trust pinning, and complete a signed `inspect` round-trip. Test backup first with the isolated synthetic Postgres integration test. A live backup smoke requires the owner-authorized Finance scope and a verified target; never run a rebuild script merely to obtain a backup.
