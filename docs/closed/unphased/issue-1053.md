# Issue #1053

Morning Brief: hiển thị tin tức dạng title=link (clickable), tăng lên 5 tin từ CafeF + VnExpress

## Problem
Phần "news" trong Morning Brief hiện chỉ hiển thị title của bài báo (plain text,
không bấm được). User muốn đọc chi tiết phải tự tìm, làm giảm tính hấp dẫn
của mục tin tức.

Code hiện tại: `backend/briefing/morning_briefing.py::_news_lines()`
```python
def _news_lines(news: list[Any]) -> str:
    if not news:
        return "• Chưa có tin nổi bật cho danh mục của bạn."
    return "\n".join(f"• {item.title}" for item in news[:3])
```

## Expected behavior
1. Mỗi tin hiển thị dưới dạng **title chính là link** (Markdown link format cho
   Telegram: `[title](url)`), bấm vào mở bài báo gốc.
2. Số lượng tin tăng từ 3 → **5 tin** mỗi buổi sáng.
3. Nguồn tin giữ nguyên: CafeF + VnExpress (`DEFAULT_FEEDS` trong
   `backend/market_data/providers/news_rss.py`, không đổi).
4. Giữ nguyên logic relevance ranking hiện có trong `get_relevant_news()`
   (ưu tiên tin liên quan tới mã cổ phiếu/crypto người dùng đang nắm giữ).

## Scope of change
- `backend/briefing/morning_briefing.py`:
  - `_news_lines()`: đổi format thành `f"• [{item.title}]({item.url})"`.
  - Gọi `get_relevant_news(user.id, limit=5)` thay vì `limit=3`.
- Kiểm tra renderer Telegram (nơi gửi tin nhắn) có hỗ trợ Markdown link
  (`parse_mode=Markdown` hoặc `MarkdownV2`) hay cần escape ký tự đặc biệt
  trong title (dấu `_`, `*`, `[`, `]` theo chuẩn MarkdownV2 của Telegram).
  Nếu bot đang dùng MarkdownV2, phải escape title trước khi build link.

## Out of scope
- Không đổi nguồn RSS (không thêm nguồn mới).
- Không đổi logic relevance/ranking tin.
- Không đổi các section khác của Morning Brief (net worth, market, portfolio, insights).

## Acceptance Criteria
- [ ] Morning Brief hiển thị đúng **5 tin** (không còn 3).
- [ ] Mỗi dòng tin có format `• [Title bài báo](URL)` và khi bấm vào mở đúng
      bài báo gốc trên CafeF/VnExpress.
- [ ] Nếu Telegram parse_mode yêu cầu escape ký tự đặc biệt, title phải được
      escape đúng (không làm vỡ format hoặc lộ ký tự `\`).
- [ ] Trường hợp không có tin (news rỗng) vẫn giữ nguyên message fallback hiện tại.
- [ ] Unit test cập nhật: `backend/tests/test_briefing_phase39.py` hoặc test
      liên quan — kiểm tra `_news_lines()` trả về đúng format link + đúng số
      lượng item.
- [ ] Test hiện có (`test_morning_briefing_job.py`, `test_briefing_full_flow.py`)
      vẫn pass.

## Test commands
```
pytest backend/tests/test_briefing_phase39.py -v
pytest backend/tests/test_market_data/test_briefing_full_flow.py -v
pytest backend/tests/test_morning_briefing_job.py -v
```

## Constraints
- Không đổi schema `NewsItem`/`RelevantNews` (đã có `url`, `title`, `source`).
- Không thêm dependency mới.

