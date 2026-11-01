# Thông báo người dùng — Hóng hớt Phase 1 (release 2026-11-01)

> **Tính năng:** Morning Brief tin tức dạng link + "Hóng hớt" (tin MXH/công nghệ/kinh tế do Nuitruc chọn lọc)
> **Tham khảo mẫu:** docs/closed/phase-3.9/phase-3.9-deploy-announcements.md
> **Trạng thái:** Reference copy — operator gửi qua `scripts/broadcast_announcement.py`
> Tone theo tone_guide.md: "mình"/"bạn", ấm áp, gợi ý chứ không ép buộc.

---

## Message 1 — Pre-deploy teaser (tối hôm trước deploy, 19h-21h)

**ID:** `teaser`

```
📰 *Sắp có góc mới trong Bé Tiền!*

Từ mai, buổi sáng mở Bé Tiền bạn sẽ thấy:

🔗 Tin tức thị trường giờ bấm được luôn — không cần tự tìm lại trên báo
🔥 Góc "Hóng hớt" mới: tin hot mạng xã hội + tin công nghệ/kinh tế,
   chọn lọc mỗi ngày

Nhẹ nhàng thôi, không ồn ào — cho buổi sáng của bạn có thêm chút vui 💚
```

---

## Message 2 — Launch announcement (trong vòng 1h sau deploy, đã smoke test)

**ID:** `launch`

```
🎉 *Bé Tiền có góc mới rồi nè!*

*1. Tin tức sáng nay — giờ bấm được luôn*
Trong Morning Brief, mỗi tin giờ là một đường link — bấm vào là đọc
được ngay bài gốc trên CafeF/VnExpress. Không cần tự tìm lại nữa.

*2. Thử ngay góc "🔥 Hóng hớt"*
Gõ /menu → bấm "🔥 Hóng hớt" để xem:
  🔥 MXH hot — chuyện đang được bàn tán
  📰 Công nghệ/Kinh tế — tin đáng chú ý trong ngày

Nội dung được chọn lọc thủ công, cập nhật đều — không phải tin rác
tự động đâu nhé 😊

Mọi thứ khác vẫn như cũ. Cứ hỏi Bé Tiền tự nhiên như mọi khi!
```

---

## Message 3 — Follow-up nudge (+5 ngày, chỉ gửi user chưa thử Hóng hớt)

**ID:** `followup`

```
👋 *Đã ghé "Hóng hớt" chưa?*

Mình để ý bạn chưa thử góc mới — không sao, nhắc nhẹ thôi vì tin được
cập nhật mỗi ngày đó:

🔥 Gõ /menu → "🔥 Hóng hớt" để xem tin hot MXH + công nghệ/kinh tế
   hôm nay có gì mới.

Thử một lần thôi, thấy hợp thì ghé mỗi sáng nhé 💚
```

---

## Broadcast tool

Dùng lại `scripts/broadcast_announcement.py` như các phase trước:

```bash
# Preview trước khi gửi (luôn làm trước)
python scripts/broadcast_announcement.py \
    --file docs/releases/announcement-2026-11-01-hong-hot.md \
    --message teaser --dry-run

# Test trên Telegram ID của chính mình
python scripts/broadcast_announcement.py \
    --file docs/releases/announcement-2026-11-01-hong-hot.md \
    --message teaser --only <YOUR_TELEGRAM_ID>

# Gửi teaser (~24h trước deploy) — BỎ QUA nếu deploy gấp trong ngày
python scripts/broadcast_announcement.py \
    --file docs/releases/announcement-2026-11-01-hong-hot.md \
    --message teaser

# Gửi launch (trong vòng 1h sau deploy + smoke test pass) — BẮT BUỘC
python scripts/broadcast_announcement.py \
    --file docs/releases/announcement-2026-11-01-hong-hot.md \
    --message launch

# Gửi follow-up sau 5 ngày, chỉ cho user chưa thử Hóng hớt
python scripts/broadcast_announcement.py \
    --file docs/releases/announcement-2026-11-01-hong-hot.md \
    --message followup --skip-engaged --launch-date 2026-11-01
```

> **Lưu ý:** Release lần này không có pre-deploy teaser timing dài như
> Phase 3.9 (tính năng nhỏ hơn, không cần "tạo kỳ vọng" nhiều ngày
> trước). Có thể gộp teaser + launch thành 1 message "launch" duy nhất
> nếu PO muốn deploy nhanh gọn — tuỳ PO quyết định khi duyệt gửi.
