# Mascot Assets

Bộ mascot cho bot. Chưa có file chính thức — cần design phase riêng.

## Yêu cầu

| File             | Tình huống dùng                                        |
| ---------------- | ------------------------------------------------------ |
| `happy.png`      | Xác nhận giao dịch thành công, milestone nhỏ           |
| `worried.png`    | Gần chạm trần ngân sách, streak bị gãy, 7 ngày vắng   |
| `celebrating.png`| Đạt mốc đặc biệt (100 ngày, first 1tr / 10tr / 100tr) |

## Spec kỹ thuật

- Format: PNG 24-bit, nền trong suốt (alpha)
- Kích thước: 512×512 (cho Telegram sticker set) + 200×200 (inline)
- Style: chibi vector, minimalist, 1-2 accent color
- Palette chủ đạo: `#4ECDC4` (primary) + `#FF6B6B` (accent)
- File `bot_avatar_512.png` — ảnh đại diện bot (BotFather), nền trắng clean

## Cách tạo

### Option A — Thuê Fiverr / 99designs ($50-100)
Search: "chibi mascot finance", "savings character illustration".

Brief:
> Cute chibi piggy bank character, 3 expressions needed (happy / worried /
> celebrating). Minimalist vector style. Primary color #4ECDC4, accent
> #FF6B6B. Vietnamese finance assistant app. Transparent PNG, 512×512.

### Option B — Midjourney / Nano Banana
Prompt mẫu:
```
cute chibi piggy bank mascot character, minimalist vector illustration,
primary color #4ECDC4, accent #FF6B6B, vietnamese finance assistant,
three expressions on one sheet: happy smile, worried face, celebrating
with confetti, clean white background, simple shapes, flat design
```

### Option C — OpenArt / tự vẽ
Nếu nội team có designer, brief thẳng theo style guide trên.

## Sau khi có file

1. Commit 3 file `.png` vào thư mục này.
2. Update `backend/config/mascot.py` (chưa tồn tại — tạo khi có file) với
   map `{expression: path}`.
3. Upload lên Telegram sticker set qua BotFather `/newstickers`.
4. Phase 2 `empathy_rules.py` sẽ dùng mascot theo trigger.

## Status

- [ ] `happy.png`
- [ ] `worried.png`
- [ ] `celebrating.png`
- [ ] `bot_avatar_512.png`
- [ ] Upload Telegram sticker set
