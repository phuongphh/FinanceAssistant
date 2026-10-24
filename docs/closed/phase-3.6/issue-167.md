# Issue #167

[Story] P3.6-S7: Add wealth-level detection to MenuFormatter

**Parent Epic:** #159 (Epic 2: Adaptive Polish & Integration)

## User Story
As a Starter user, tôi muốn menu encouraging và educational. As HNW, tôi muốn nó professional và respectful. Cùng buttons nhưng intro và tone adapt theo wealth level.

## Acceptance Criteria
- [ ] Update `MenuFormatter.format_main_menu()`:
  - Call `NetWorthCalculator().calculate(user.id)` → get total
  - Call `detect_level(total)` từ Phase 3.5 ladder logic
  - Lookup correct intro từ YAML bằng level
  - Format với `name=user.display_name`
- [ ] Update `MenuFormatter.format_submenu()` similarly
- [ ] Cache wealth level per user 5 phút (tránh recalculate mỗi menu interaction)
- [ ] Fallback về `young_prof` nếu `NetWorthCalculator` fails (không có assets)

### Visual Test (manual):
- [ ] Run /menu cho 4 personas, screenshot 4 main menus + 5 sub-menus = **24 screenshots**
- [ ] Store trong `tests/test_menu/visual/`
- [ ] Verify:
  - Starter Minh: "Trợ lý tài chính" + encouraging intro
  - Mass Affluent Phương: "Trợ lý CFO cá nhân" + professional intro
  - HNW Anh Tùng: "Personal CFO" + advisor-level intro
  - **Buttons identical** across all 4 levels

- [ ] **Performance:** wealth-level detection thêm <100ms vào menu render

## Test Plan
```python
async def test_starter_intro():
    user = mock_user_minh()  # 17tr net worth
    text, _ = await formatter.format_main_menu(user)
    assert "Trợ lý tài chính" in text
    assert "Personal CFO" not in text

async def test_hnw_intro():
    user = mock_user_anh_tung()  # 13 tỷ
    text, _ = await formatter.format_main_menu(user)
    assert "Personal CFO" in text
```

## Estimate: ~1 day
## Depends on: Epic 1 complete
## Reference: `docs/current/phase-3.6-detailed.md` § 1.3
