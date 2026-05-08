# Issue #263

[Epic] Phase 3.9 — Epic 1: Foundation & Provider Abstraction

## Phase 3.9 — Epic 1: Foundation & Provider Abstraction

> **Type:** Epic | **Days:** 1-3 | **Stories:** 3

## Context
Phase 3.9 thay thế stub market data (giá giả) từ Phase 3.7 bằng real-time integration với SSI/VNDIRECT (stocks), CoinGecko (crypto), SJC/PNJ (gold), RSS (news). **Blocker cho soft launch tháng 6.**

## Tại Sao Epic Này Quan Trọng
User mở app thấy portfolio giá đứng yên → niềm tin sản phẩm hỏng. Morning briefing hiển thị số liệu thật là moment of trust.

## Mục tiêu
Setup module structure, base classes, cache layer, error handling — nền móng cho mọi provider.

## Stories in this Epic
_(Sẽ update sau khi tạo Story issues)_
- [ ] [Story] P3.9-S1: Module skeleton + BaseProvider abstract class
- [ ] [Story] P3.9-S2: Redis price cache layer
- [ ] [Story] P3.9-S3: Provider dispatcher + circuit breaker

## Reference
`docs/current/phase-3.9/phase-3.9-detailed.md` § Foundation
