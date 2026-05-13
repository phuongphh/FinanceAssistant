# ADR: Financial Twin Channel Abstraction

## Status
Accepted for Phase 4A Epic 6.

## Context
Financial Twin starts on Telegram, but the product roadmap expects Zalo support later. The Twin code path must avoid coupling domain/query logic to any single chat channel so future adapters can reuse the same snapshot, chart, and trust-framed copy.

## Decision
Use a small `ContentRenderer` port in `backend/ports/content_renderer.py`:

- handlers/services prepare read-model snapshots;
- renderers produce `ChannelContent(text, images, buttons)`;
- notifiers/adapters deliver that content to the external channel.

Telegram now uses `TelegramContentRenderer`. Zalo has an explicit stub that raises `NotImplementedError` until Phase 5+ wires a real adapter.

## Consequences
- Twin handlers no longer build Telegram-specific caption/photo/button payloads for the main trajectory view.
- Channel-specific differences stay in adapters, while trust copy remains YAML-driven.
- The abstraction is intentionally minimal to avoid premature complexity: no dependency-injection container and no channel registry until a second real channel exists.

## Security and UX notes
- API and Mini App auth stay at HTTP boundaries; renderers do not authenticate users.
- Renderers must never recompute projections or perform writes, keeping user-facing paths fast.
- User-facing Twin strings remain probabilistic and must avoid deterministic claims.
