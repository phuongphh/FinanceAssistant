# Issue #927

Tier 3 reports leak English category/jargon tokens into Vietnamese output

## Problem

Tier 3 LLM-generated reports echo English tokens straight from DB codes and from the system prompt itself, breaking the Vietnamese-only UX rule and the Bé Tiền persona.

### Observed leakage

**Spending-by-category report** (user: "chi tiêu cho cái gì nhiều nhất?"):
- Renders "Transfer", "Other", "Food", "Transport" instead of "Chuyển khoản", "Khác", "Ăn uống", "Di chuyển".

**Monthly report** (user: "báo cáo các khoản tiền vào"):
- Output contains "NW", "rental", "passive income", "allocate", "reply" — English finance jargon mirrored from the prompt.

## Root cause

1. Agent tools (`get_transactions`, `get_income`, `get_assets`) return raw English codes from the DB (`category="food"`, `stream_type="rental"`, `asset_type="real_estate"`) in their Pydantic schemas. The LLM has no Vietnamese label to use, so it echoes the code.
2. `backend/agent/tier3/prompts.py` `_LEVEL_FOCUS` and `backend/services/report_service.py` `_LEVEL_GUIDANCE` contain English jargon (NW, passive income, allocation, rental, cashflow, DCA) which the LLM mirrors in user-facing replies.
3. `report_service.py` builds the breakdown/income strings directly from raw codes (lines ~254 and ~420).

## Fix plan

- Enrich tool schemas with `*_label` fields populated from `get_category().name_vi`, `income_types.get_label()`, `asset_types.get_label()`.
- Translate categories/stream-types in `report_service._build_wealth_context`.
- Add an explicit "Vietnamese-only output + translation table" hard rule to the Tier 3 reasoning prompt.
- Sanitize `_LEVEL_FOCUS` and `_LEVEL_GUIDANCE` jargon.
- Cover with unit tests.

Violates `CLAUDE.md` rule: *"All user-facing strings in `content/*.yaml`"* and the Bé Tiền persona contract.
