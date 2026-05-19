# Database Model

The model must do three things well: move fast for prototype, keep permissions auditable, and scale without painful migrations.

## Principles

- Wiki is immutable snapshots; no in-place update.
- JSONB for fast-changing payloads: message content, agent config, wiki content.
- Add indexes only for real queries.
- Locale-aware rendering data must be explicit (`language_code`, `date_format`, `timezone`) to avoid frontend guesswork.

## Key improvements over old version

```mermaid
erDiagram
```

### `agent_runs`
- `id`, `organization_id`, `user_id`, `status`, `period_start`, `period_end`, `input_token`, `output_token`, `error`, `result_version_id`, `run_at`, `created_at`
- Index: `(organization_id, status, run_at DESC)`

### `user_preferences` (for i18n foundation + UI consistency)
- `id`, `organization_id`, `user_id`, `language_code`, `date_format`, `timezone`, `created_at`, `updated_at`
- `date_format` is locale-driven token (example: `dd/MM/yyyy` for `vi-VN`, `MM/dd/yyyy` for `en-US`).
- Unique: `(organization_id, user_id)`

### `navigation_events` (for fallback telemetry + UX audit)
- `id`, `organization_id`, `user_id`, `event_type`, `source_menu`, `target_menu`, `fallback_reason`, `metadata`, `created_at`
- Event `event_type = menu_fallback` is emitted whenever route recovery is triggered.
- Index: `(organization_id, event_type, created_at DESC)`

### `access_grants`
- `id`, `organization_id`, `grantor_user_id`, `grantee_user_id`, `resource_type`, `resource_id`, `action`, `expires_at`, `revoked_at`, `created_at`
- Index: `(organization_id, grantee_user_id, resource_type, resource_id)` where `revoked_at is null`
