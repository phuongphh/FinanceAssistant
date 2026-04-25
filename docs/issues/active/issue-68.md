# Issue #68

[P3A-10] Create briefing_templates.yaml (4 wealth levels)

## Epic
Epic 2 — Morning Briefing | **Week 2** | Depends: P3A-5 | Blocks: P3A-11

## Description
Content file với templates cho từng wealth level. **Content work**, quan trọng hơn code. YAML là single source of truth — không hardcode string trong Python.

## Acceptance Criteria
- [ ] File `content/briefing_templates.yaml`
- [ ] 4 level sections: starter, young_prof, mass_affluent, hnw
- [ ] Mỗi level có:
  - `greeting` — 2-3 variations
  - `net_worth_display.template` với placeholders
  - `net_worth_display.no_change` cho case không đổi
- [ ] Starter extra: `progress_context.template`, `educational_tips` (3-5 tips)
- [ ] Young Prof extra: `action_prompts`
- [ ] Mass Affluent extra: `market_intelligence.template` (placeholder)
- [ ] HNW extra: `detailed_breakdown`
- [ ] Common sections: `spending_reminder`, `storytelling_prompt`
- [ ] Content review với 2 native VN speakers — không sến súa, không formal quá
- [ ] `yamllint content/briefing_templates.yaml` passes

## Placeholders Standard
`{name}`, `{net_worth}`, `{change}`, `{pct}`, `{period}`, `{breakdown_lines}`, `{threshold}`

## Tone Rules (bắt buộc)
- Tối đa 2-3 emoji per section
- Xưng "mình" / "bạn"
- Không phán xét, không dạy đời

## Estimate
~1 day (content-heavy)

## Reference
`docs/current/phase-3a-detailed.md` § 2.1
