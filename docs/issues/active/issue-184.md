# Issue #184

[Story] P3.7-S2: Implement GetAssets and GetTransactions tools

**Parent Epic:** #180 (Epic 1: Tool Foundation & DB-Agent)

## User Story
As an agent processing "Mã chứng khoán nào đang lãi?", I need a `get_assets` tool wraps existing AssetService và adds filter/sort/limit capability to return ONLY assets matching criteria.

## ⚠️ Critical Bug Fix
Đây là story fix **critical bug**: hiện tại query "Mã đang lãi?" trả về TẤT CẢ stocks. After this story, nó chỉ trả về winners.

## Acceptance Criteria
- [ ] File `app/agent/tools/base.py` với `Tool` ABC + `ToolRegistry`
- [ ] `Tool` abstract class: name, description, input_schema, output_schema, execute(), to_openai_function()
- [ ] **GetAssetsTool** (`app/agent/tools/get_assets.py`):
  - Wraps existing `AssetService.get_user_assets()` (**KHÔNG rewrite**)
  - Apply filter: asset_type, ticker, value range, gain_pct
  - Apply sort: 8 sort orders
  - Apply limit: 1-100
  - Compute gain/gain_pct on the fly
  - Returns `GetAssetsOutput` (Pydantic validated)
  - **Description có 5+ examples** (critical cho LLM accuracy)
- [ ] **GetTransactionsTool** (`app/agent/tools/get_transactions.py`):
  - Wraps existing `TransactionService.get_by_date_range()`
  - Filter: category, date_from/to, amount
  - Sort: date_desc, amount_desc/asc
  - Limit: 1-200
- [ ] **CRITICAL TEST:**
  ```python
  async def test_get_assets_winners_only():
      # Portfolio: VNM +10%, HPG -5%, NVDA +20%, FPT -3%
      result = await tool.execute(
          GetAssetsInput(filter=AssetFilter(gain_pct=NumericFilter(gt=0))), user
      )
      assert result.count == 2
      assert all(a.gain_pct > 0 for a in result.assets)
  ```
- [ ] All 8 sort orders tested
- [ ] Edge cases: empty result, asset without cost_basis, NULL values
- [ ] Coverage >90%

## Implementation Notes
- **DO NOT modify AssetService** — wrap it
- Decimal arithmetic cho money (no float errors)
- Normalize ticker case: .upper()
- Skip NULL gain_pct assets when filtering by gain_pct

## Estimate: ~1.5 day
## Depends on: P3.7-S1
## Reference: `docs/current/phase-3.7-detailed.md` § 1.2
