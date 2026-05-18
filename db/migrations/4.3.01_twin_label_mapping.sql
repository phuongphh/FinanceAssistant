-- Phase 4.3.01 — Twin weather vocabulary presentation mapping.
CREATE TABLE IF NOT EXISTS twin_label_mapping (
    probability_code VARCHAR(3) PRIMARY KEY,
    vi_label VARCHAR(50) NOT NULL,
    emoji VARCHAR(8) NOT NULL,
    en_fallback VARCHAR(50) NOT NULL,
    description VARCHAR(200) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO twin_label_mapping (probability_code, vi_label, emoji, en_fallback, description)
VALUES
    ('P10', 'Khiêm tốn', '🌧️', 'Conservative', 'Kịch bản thận trọng nhất'),
    ('P50', 'Bình thường', '⛅', 'Expected', 'Kịch bản trung tính Bé Tiền tin tưởng nhất'),
    ('P90', 'Lạc quan', '☀️', 'Optimistic', 'Kịch bản tốt nhất')
ON CONFLICT (probability_code) DO UPDATE SET
    vi_label = EXCLUDED.vi_label,
    emoji = EXCLUDED.emoji,
    en_fallback = EXCLUDED.en_fallback,
    description = EXCLUDED.description;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS twin_show_technical_terms BOOLEAN NOT NULL DEFAULT FALSE;
