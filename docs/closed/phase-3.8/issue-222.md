# Issue #222

[Story] P3.8-S14: GoalProjectionService + feasibility analysis

**Parent Epic:** #208 (Epic 5: Goals Management Complete)

## User Story
As a user với mục tiêu mua xe, tôi muốn biết projected completion date và feasibility — nhưng với framing supportive, không harsh.

## Feasibility Levels
| Level | Condition |
|-------|-----------|
| easy | required ≤ 0.5× actual saving |
| feasible | 0.5-1.0× (current saving sufficient) |
| stretch | 1.0-1.5× (cần save 1.5x current) |
| ambitious | 1.5-2.0× |
| needs_revision | >2.0× (unrealistic) |

## Acceptance Criteria
- [ ] `GoalProjectionService` class:
  - `project_goal(goal_id)` → dict với all projection data
  - **If target_date set:** compute required_monthly_savings + feasibility
  - **If no target_date:** compute estimated_completion_months/date từ actual saving rate
- [ ] Helper `_get_avg_monthly_savings(user_id)`:
  - Average savings last 3 months
  - Sử dụng CashflowForecaster baseline
- [ ] **Supportive framing:** không dùng ngôn ngữ harsh, luôn offer alternatives
- [ ] Test:
  - User saves 8tr/tháng, goal "Mua xe 800tr in 2 years" → required 33tr, feasibility=needs_revision + suggest extend timeline
  - User saves 8tr/tháng, goal "Mua xe 800tr in 8 years" → required 8.3tr, feasibility=feasible

## Estimate: ~1 day
## Depends on: P3.8-S13, Epic 4 (cashflow data)
