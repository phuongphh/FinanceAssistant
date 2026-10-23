# Issue #115

[Story] P3.5-S2: Create test fixtures from real queries

**Parent Epic:** #110 (Epic 1: Intent Foundation & Patterns)

## User Story
As a developer who values TDD, I need a YAML fixture file với real Vietnamese queries và expected classifications, để validate mọi thay đổi mà không cần manual testing.

## Tại Sao Story Này Đến Sớm
Fixtures created BEFORE classifier implementation → test-first thinking. Pattern development = "make this test pass".

## Acceptance Criteria
- [ ] File `tests/test_intent/fixtures/query_examples.yaml`
- [ ] Chứa **11 real queries** từ design phase:
  - "tiết kiệm 1tr" → action_record_saving, amount=1000000
  - "tài sản của tôi có gì?" → query_assets
  - "tôi có tài sản gì?" → query_assets
  - "làm thế nào để đầu tư tiếp?" → advisory
  - "hiện tại có thể mua gì để có thêm tài sản?" → advisory
  - "mục tiêu hiện giờ của tôi có gì?" → query_goals
  - "muốn đạt được việc mua xe tôi cần phải làm gì?" → query_goal_progress, goal_name="mua xe"
  - "portfolios chứng khoán của tôi gồm những mã gì?" → query_portfolio
  - "các chi tiêu cho sức khỏe của tôi trong tháng này gồm những gì?" → query_expenses_by_category, category="health", time_range="this_month"
  - "liệt kê cho tôi mọi chi phí về ăn uống của tôi tháng này?" → query_expenses_by_category, category="food"
  - "thu nhập của tôi là như thế nào?" → query_income
- [ ] **20 edge case queries thêm:**
  - Không dấu, typos, tiếng Anh mixed, out of scope, gibberish, greetings, help
- [ ] Pytest helper `load_query_fixtures()` reads file
- [ ] Format: text, expected_intent, expected_parameters (optional), expected_min_confidence, notes
- [ ] Documentation trong file về cách thêm fixtures

## Estimate: ~0.5 day
## Depends on: P3.5-S1
## Reference: `docs/current/phase-3.5-detailed.md`
