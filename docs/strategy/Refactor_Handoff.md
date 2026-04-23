# Refactor Handoff Document

## Mục tiêu refactor
Trước khi implement các issue tiếp theo của phase 2, tôi cần bạn đóng vai trò là một kiến trúc sư phần mềm có nhiều kinh nghiệm, là chuyên gia trong thiết kế hệ thống, bạn hãy xem lại kiến trúc của hệ thống phần mềm Finance Assistant, refactor để code có thể không bị nhầm lẫn giữa các tầng layer service của sản phẩm, cũng như không có conflict gì giữa hệ thống backend service và hệ thống handler/router của sp. Hãy review lại một lượt đồng thời tự hỏi là có thể làm gì tốt hơn nữa để hệ thống chạy với performance tốt nhất (hiện tôi đã muốn sản phẩm bước dần sang hệ thống Production phục vụ cho mass-user như một sản phẩm SaaS), làm sao để hệ thống Scale được tốt nhất. Đồng thời, hãy nhìn lại hệ thống webhook khi làm việc với telegram, cũng như việc gọi LLM API như thế nào để hiệu quả và tiết kiệm nhất.

## Architectural Audit (kết luận)
1. Phát hiện chính (theo mức độ rủi ro)
🔴 Critical — chắn scale 1K users
1.1. LLM call đồng bộ trong webhook path
backend/bot/handlers/message.py:82-87 gọi call_llm() bên trong handler của webhook, trước khi FastAPI trả 200. Mỗi tin nhắn = 2-10s chờ DeepSeek. Ở 1K users, 10 uvicorn workers sẽ hết slot sau vài chục message đồng thời — webhook timeout → Telegram retry → spiral.

1.2. Không có dedup update_id
backend/routers/telegram.py verify secret nhưng không track update_id. Telegram retry khi mạng chập → cùng một expense được tạo 2-3 lần. Không phải lý thuyết: 1-3% traffic retry là tỷ lệ thực tế.

1.3. Connection pool quá nhỏ
backend/database.py:19-22: pool_size=5, max_overflow=10. Với 1K users + morning report + webhook đồng thời, pool sẽ exhaust → deadlock cascade. Đây là default dev, không phải production setting.

1.4. Services gọi db.commit() bừa bãi
onboarding_service.py, dashboard_service.py, milestone_service.py đều commit ngay trong service function. Flow nhiều bước (ví dụ step_3_ask_goal → set_primary_goal + set_step) có thể partial commit nếu lỗi giữa chừng. Nguyên tắc đúng: services flush, routers commit.

🟠 High — lãng phí tiền + chậm ở 10K
1.5. Cache LLM thiếu user_id trong key
llm_service.py:73-74 dùng hash(prompt) làm key. User A và User B nhắn cùng nội dung → cùng cache entry. Khi prompt nhúng tên/goal của user (về sau), kết quả sẽ lẫn lộn giữa users. Security bug tiềm ẩn khi có personalization.

1.6. Morning report gửi tuần tự
backend/jobs/morning_report_job.py for user in users: await send(...). 1K users × 2s = 33 phút. Tin đến 7:00 sẽ thành 7:30 — mục tiêu "habit forming" hỏng.

1.7. Không có batch LLM
Gmail poll: mỗi email = 1 LLM call. 1K users × 10 email/ngày = 10K calls. Nếu gộp 50 emails/call thì chỉ còn 200 calls — giảm 98% chi phí cho task này.

🟡 Medium — technical debt
1.8. Handler callbacks.py:53-60 duplicate _get_user_by_telegram_id (đã có trong dashboard_service). Giống bug onboarding_service đã fix — drift sẽ quay lại.

1.9. Services gửi Telegram trực tiếp (morning_report_service.py:221,232,239). Transport nên ở service layer riêng, không trong domain service.

1.10. Thiếu composite index cho query path phổ biến: goals(user_id, is_active, deleted_at), income_records(user_id, deleted_at). Ở <10K users vẫn nhanh, >10K bắt đầu full scan.

1.11. Không có DLQ / retry cho scheduled jobs. Một user fail = mất report hôm đó, không re-attempt.

2. Kiến trúc đề xuất (target Phase 1)
┌─────────────────────────────────────────────────────────────┐
│  Telegram webhook  →  Router (≤100ms: verify + enqueue)     │
│                          ↓                                   │
│                   Redis queue (update_id dedup)              │
│                          ↓                                   │
│                   Worker pool (async, LLM/DB work here)      │
│                          ↓                                   │
│   Service layer (pure business logic, flush only — never     │
│   commit, never send Telegram, never call LLM directly —     │
│   uses ports: LLMPort, NotifierPort, CachePort)              │
│                          ↓                                   │
│   Infrastructure (db, telegram, deepseek, anthropic)         │
└─────────────────────────────────────────────────────────────┘
Ranh giới layer cần cứng hóa:

routers/ — chỉ parse HTTP, verify auth, enqueue, trả 200
workers/ (mới) — consume queue, gọi services, commit một lần ở boundary
services/ — pure business logic, nhận db, flush + return; KHÔNG commit, KHÔNG send, KHÔNG call LLM trực tiếp
adapters/ (đổi tên từ infrastructure/services/telegram_service.py) — transport
Pattern này giữ được codebase hiện tại (không phải rewrite), chỉ cần thêm queue + di chuyển commit/send lên handler/worker layer.

3. Ưu tiên thực hiện — 3 giai đoạn
Giai đoạn	Mục tiêu	Changes	Thời gian	Block Phase
A. Stop-the-bleeding	Webhook không chết ở 1K users	update_id dedup, pool tuning, LLM ra background task (dùng asyncio.create_task trước, chưa cần Redis)	2-3 ngày	Phase 1 go-live
B. Cleanup layers	Code không drift khi team lớn	Gom db.commit() về router, xóa duplicate lookup, tách Notifier port, cache key thêm user_id	3-4 ngày	Bất kỳ issue nào mới
C. True SaaS scaling	Chạy mượt 10K users	Redis + Celery/RQ, batch Gmail LLM, DLQ, observability (OpenTelemetry), rate limiter per-user	1-2 tuần	Phase 2 SaaS launch
Giai đoạn A + B là must-do trước khi làm issue Phase 2 tiếp. C có thể song song hoặc sau.

## Các quyết định đã thống nhất
- Q1: Queue technology — Cho giai đoạn A:

(a) In-process asyncio.create_task + task table trong Postgres (không cần infra mới, single-node OK cho <1K users)
(b) Redis + ARQ/RQ (cần Redis container, dễ scale, nhưng thêm một dependency)
(c) Dùng luôn Celery + RabbitMQ như CLAUDE.md đã plan sẵn cho Phase 2
Tôi nghiêng về (a) trước (1-2 ngày), (b) ở giai đoạn C (tránh over-engineer sớm). Bạn OK? → [OK]

- Q2: Backward compat — Khi refactor db.commit() ra khỏi services:

(a) Big-bang refactor tất cả services trong 1 PR (sạch nhưng rủi ro)
(b) Đổi convention mới + tạo @transactional decorator cho router; services cũ giữ commit() để không break, migrate dần issue-by-issue
Tôi nghiêng về (b). Bạn OK? → [OK]

- Q3: Phạm vi review này — Bạn muốn tôi:

(i) Viết detailed design doc cho từng thay đổi (không code) để bạn review và phê duyệt từng phần, hoặc
(ii) Implement giai đoạn A ngay (3 fix critical: dedup, pool, LLM background) thành 3 PR nhỏ, sau đó bàn giai đoạn B? → [tôi muốn bạn detail design doc cho từng giai đoạn : A (critical issues) và B (high + medium issues), update ngay trong file mô tả CLAUDE.md (với việc bạn note các điểm chính quan trọng của hệ thống) hoặc thêm vào 1 file mới như file strategy.md. Sau đó, ngay lập tức implement giai đoạn A ngay (3 fix critical issues)]

## Todo List (8 tasks)
1. [task 1 - docs/strategy/scaling-refactor-A-B.md] ← đang ở đây
2. Add architecture direction note to CLAUDE.md
3. Phase A2 — env-configurable pool + pool_pre_ping
4. Phase A1 — telegram_updates table + model + migration
5. Phase A3 — refactor webhook to enqueue + process via asyncio.create_task; extract route_update fn
6. Phase A3 — lifespan hook picks up orphaned 'processing' rows on startup
7. Unit + integration tests for dedup, async processing, recovery
8. Commit + push Phase A changes
...

## Trạng thái hiện tại
- Branch: [claude/phase-2-implementation-JqFFU], đã sync với main (fast-forward commit e7f8d12)
- Chưa có code change nào
- Task đang làm: #1 - viết design doc

## Lưu ý cho Claude session mới
- Đọc file này + git log trước khi bắt đầu
- KHÔNG viết output dài, mỗi lượt làm 1 đơn vị nhỏ
- Dùng Edit tool thay vì Write khi có thể