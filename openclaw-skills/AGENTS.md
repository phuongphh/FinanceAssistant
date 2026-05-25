# AGENTS.md — Operating rules for automation agents

Rules for **any** automation agent acting on this repo or the prod server:
the OpenClaw Telegram bot (`finance-devops` skill), Claude Code, CI bots, etc.
Read this before running shell commands or editing files. For architecture and
coding conventions see [CLAUDE.md](CLAUDE.md).

---

## ⛔ NEVER touch `.env` — production secrets, NO backup

- **`.env`** (repo root, and the prod copy at `$PROD_PROJECT_DIR/.env`) holds
  real production secrets: DB password, API keys, Telegram bot token,
  `ADMIN_JWT_SECRET`. It is **gitignored, dockerignored, and backed up
  NOWHERE** — if it is overwritten or deleted, the secrets are gone for good.
- ❌ NEVER create, overwrite, truncate, move, or delete `.env`.
- ❌ NEVER run `cp .env.example .env`, `> .env`, `mv … .env`, `rm .env`, or any
  command that writes `.env` — **not even to "initialize" or "set up" the
  project**. This is exactly how the prod `.env` was once destroyed.
- ✅ `.env.example` is a **key-name reference only** (placeholders, never real
  values). If `.env` is missing or looks like the unfilled template, **STOP and
  ask the admin** — do not attempt to recreate it.

> Recovery note: a running container created with `env_file: .env` carries the
> values in its `Config.Env` (`docker inspect <container>`). That is the only
> fallback — do not destroy such a container before secrets are recovered.

---

## Destructive / irreversible actions — confirm first

Get explicit admin confirmation **in the same request** before:

- `rm -rf`, `git reset --hard`, `git push --force`, `git clean -f`
- `docker volume rm`, deleting containers/volumes that hold data
- `DROP TABLE` / destructive SQL — the DB has **no auto-revert** on migration;
  treat every schema change as irreversible.

When you hit an obstacle, find the root cause — do not bypass safety checks
(`--no-verify`, force flags) or delete state to "make the error go away".

---

## Prod / deploy operations

- Run prod operations **only** through the `finance-devops` skill scripts
  (`openclaw-skills/finance-devops/scripts/*.sh`). Do not run ad-hoc commands
  that mutate prod state (files, containers, volumes, config) outside them.
- Only admins (`ADMIN_USER_IDS`) may trigger devops actions.
- Deploys go `main → prod` via PR; never push substantive changes straight to
  `main`/`prod`. See [CLAUDE.md](CLAUDE.md) → *Forbidden Actions*.
