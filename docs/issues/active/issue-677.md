# Issue #677

[Story 2.1] Bé Tiền Mascot Personification (3 Versions) — Phase 4.3

## Story 2.1 — Bé Tiền Mascot Personification (3 Versions)

**Parent Epic:** #671 | **Estimate:** 1.5 days | **Priority:** P0 | **Surface:** Telegram | **Depends on:** Story 1.1

### User Story
> Là một mass affluent user, khi tôi nhìn 3 kịch bản tương lai, tôi muốn thấy Bé Tiền mascot phản ánh trạng thái của mỗi kịch bản — để tôi có visual cue cảm xúc, không chỉ con số.

### Requirements
- [ ] 3 mascot versions: 🌧️ Khiêm tốn (áo mưa, bình tĩnh), ⛅ Bình thường (cầm dù, tự tin), ☀️ Lạc quan (kính râm, vui)
- [ ] File size ≤ 100KB mỗi version, publish lên Telegram CDN
- [ ] Mapping `mascot_version_map.yaml` link p_code → asset URL
- [ ] Render trong scenario card top-right
- [ ] Fallback nếu image fail: emoji weather only
- [ ] Tone guard: KHÔNG cute-aggressive, trẻ con quá, patronizing
- [ ] Founder + Vietnamese cultural reviewer approve

### Files Touched
- `content/mascot/mascot_version_map.yaml` (new)
- `assets/mascot/betien_2030_p10_v1.png`, `_p50_v1.png`, `_p90_v1.png` (new)
- `apps/twin_renderer/views/scenario_card.py` (modify)

### Claude Code Implementation Prompt
```
Implement Story 2.1 of Epic #671 (Phase 4.3):
Bé Tiền Mascot Personification (3 Versions)

PR should close #[ISSUE_NUMBER]
```

