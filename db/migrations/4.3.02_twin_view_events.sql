-- Phase 4.3.02 — Twin Storytelling analytics events.
CREATE TABLE IF NOT EXISTS twin_view_events (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type VARCHAR(40) NOT NULL,
    screen_id VARCHAR(40),
    flow_mode VARCHAR(20),
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_twin_view_events_user_created ON twin_view_events(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_twin_view_events_type_created ON twin_view_events(event_type, created_at);
CREATE INDEX IF NOT EXISTS idx_twin_view_events_screen_created ON twin_view_events(screen_id, created_at);
