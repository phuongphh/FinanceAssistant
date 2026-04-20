# Tone Writing Guide — Finance Assistant Bot

> Kim chỉ nam khi viết bất kỳ tin nhắn nào bot gửi cho user.
> Người đọc: tất cả engineers + content writers của dự án.
> Khi bị kẹt giữa đúng ngữ pháp và đúng tone, chọn tone.

---

## Xưng hô

- Bot xưng **"mình"**.
- Gọi user bằng **"bạn"** hoặc **tên user đã nhập** nếu có (`users.display_name`).
- Với nhóm (household mode, Phase 6): "mọi người" / "các bạn".

**Không bao giờ**: "quý khách", "anh/chị", "người dùng", "user".

---

## 4 nguyên tắc cốt lõi

1. **Ngắn gọn.** 1 ý / 1 dòng. Có khoảng trắng giữa các block ý chính.
2. **Ấm áp.** Viết như bạn bè, không như ngân hàng.
3. **Không phán xét.** Không có từ "sai", "lãng phí", "tệ", "nên/không nên", "đừng".
4. **Cho user lựa chọn.** Đưa option, không ra lệnh. "Muốn thử X không?" > "Bạn phải X".

Dòng test nhanh: nếu đọc tin nhắn lên cho một người bạn nghe mà thấy ngượng, viết lại.

---

## Bảng từ tránh → thay thế

| ❌ Tránh                          | ✅ Thay bằng                                 |
| --------------------------------- | -------------------------------------------- |
| Vui lòng ...                      | (bỏ hẳn, không cần)                          |
| Hệ thống đã lưu / Đã lưu          | Ghi xong rồi! / Mình ghi rồi nhé             |
| Bạn đã tiêu quá ...               | Mình để ý tháng này bạn đã chi ...           |
| Đừng mua cái đó                   | Có thể cân nhắc lại nhỉ?                     |
| Sai rồi / Không đúng              | Hmm, mình chưa hiểu lắm                      |
| Người dùng không tồn tại          | Chưa thấy bạn trong danh sách — thử /start? |
| Lỗi: 500 Internal Server Error    | Có gì đó không ổn — bạn thử lại giúp mình?  |
| Bạn phải nhập số tiền             | Gửi thêm số tiền giúp mình nhé               |
| Cảnh báo: vượt hạn mức            | Ồ! Tháng này chi hơi mạnh tay                |
| Thành công                        | Xong rồi! / Ổn rồi 👌                        |
| Thất bại                          | Chưa được rồi — thử lại giúp mình?           |
| Bạn không có quyền                | Tính năng này mình chưa mở cho bạn nhé       |
| Không tìm thấy dữ liệu            | Chưa có dữ liệu nào — bắt đầu bằng ... nhé? |

---

## Emoji guide

Dùng có chọn lọc. 1-3 emoji mỗi tin nhắn là đủ. Không lạm dụng.

| Nhóm                 | Dùng được                              |
| -------------------- | -------------------------------------- |
| Tích cực / hoàn tất  | ✅ 🎉 🌱 💪 👌 💚                      |
| Trung tính / chỉ dẫn | 📊 💰 📌 🔖 🏷                         |
| Lo lắng nhẹ          | 🫣 😅 ⚠️                                |
| Thời gian            | 🌅 (sáng) 🌙 (tối) ⏰                   |
| Category             | Dùng emoji từ `backend/config/categories.py` — không tự chế |
| **Không dùng**       | 💀 🤬 ❌ 🚫 (trừ khi thực sự cần alert) |

Nguyên tắc: emoji chèn vào dòng, không dùng làm bullet point thay gạch đầu dòng.

---

## Thời điểm và trạng thái

- Chào buổi sáng: 🌅 "Chào buổi sáng ..."
- Tóm tắt cuối ngày: 🌙 "Tóm tắt ngày ..."
- Milestone / ăn mừng: 🎉 "Hay quá! Bạn vừa ..."
- Lỗi kỹ thuật nhẹ: 🫣 "Ồ, có gì đó không ổn — thử lại giúp mình?"
- Lỗi do user input: (không emoji) "Mình chưa hiểu — bạn gõ lại giúp được không?"

---

## Cấu trúc tin nhắn mẫu

**Sau 1 giao dịch:**
```
✅ Ghi xong!

🍜 Phở Bát Đàn  —  45,000đ
📍 Hà Nội  •  12:15

💰 Hôm nay: 215k / 400k
   █████░░░░░ 54%

Còn 185k cho hôm nay 👌
```

**Báo cáo cuối ngày:**
```
🌙 Tóm tắt ngày 15/04

Tổng chi: 485,000đ (4 giao dịch)

🍜 Ăn uống      245k  ████████░░
🚗 Di chuyển    150k  █████░░░░░

So với trung bình: +12% ↑
```

**Alert ngân sách (sắp hết):**
```
⚠️ Sắp chạm trần ngân sách

🍜 Ăn uống: 950k / 1tr
█████████░ 95%

Còn 50k cho tháng này — còn 5 ngày nữa.
```

---

## Empathy moments (Phase 2 dùng)

Khi phát hiện tình huống nhạy cảm (user vượt budget, im lặng lâu, chi lớn bất thường), phản hồi **không phán xét**:

| Trigger                       | ❌ Không dùng                    | ✅ Dùng                                                          |
| ----------------------------- | -------------------------------- | ---------------------------------------------------------------- |
| User vượt ngân sách tháng     | "Bạn đã vượt ngân sách!"        | "Mình để ý có đám cưới / tiệc cuối tháng — những thứ đáng mà 😊" |
| User im lặng > 7 ngày         | "Bạn lâu không dùng bot"        | "👋 Lâu rồi không gặp — mọi thứ ổn không?"                       |
| User chi lớn bất thường       | "Giao dịch rất lớn, kiểm tra!" | "Ồ giao dịch lớn! Mình xếp vào đâu cho hợp lý nhỉ?"              |
| User đạt milestone tiết kiệm  | "Chúc mừng."                    | "Đây là bước ngoặt — nhiều người không đạt được đâu 🎉"          |

---

## Quyết định tên bot (chưa chốt)

Các ứng viên được cân nhắc — cần chọn 1 và update BotFather:

| Tên    | Ý nghĩa / cảm giác                     | Nhược điểm                     |
| ------ | -------------------------------------- | ------------------------------ |
| Xu     | Ngắn, gần gũi, gợi đồng tiền xu        | Có thể bị nhầm với ví Xu       |
| Tiết   | Từ "tiết kiệm", thân mật miền Bắc      | Hơi khô                        |
| Chi    | "Chi tiêu", ngắn, tên người              | Có thể trùng tên người thật    |
| Bông   | Dễ thương, gợi nhẹ nhàng                | Ít liên quan finance            |
| Finny  | Quốc tế, dễ nhớ                         | Không đậm chất Việt             |

**Tiêu chí chọn:** ngắn (1-2 âm tiết), dễ nhớ, thân thiện, không xung đột trademark tại VN.
Khi chốt xong, cập nhật:
- BotFather: `/setname`, `/setdescription`, `/setabouttext`
- `docs/tone_guide.md` section "Bot profile"
- Bot bio / intro trong welcome message

---

## Bot profile (điền khi chốt tên)

- **Tên**: _(TBD)_
- **Bio (`/setdescription`)**: "Trợ lý tài chính cá nhân thông minh — ghi chép nhanh, hiểu bạn sâu 💚"
- **About (`/setabouttext`)**: "Ghi chi tiêu bằng text / ảnh / voice. Báo cáo mỗi sáng. Mini App dashboard ngay trong Telegram."
- **Profile picture**: 512×512, nền trắng, logo mascot.

---

## Mascot

Cần 3 biểu cảm, lưu trong `assets/mascot/`:
- `happy.png` — khi user hoàn thành giao dịch / đạt milestone
- `worried.png` — khi gần chạm trần ngân sách / streak bị gãy
- `celebrating.png` — khi đạt mốc đặc biệt (100 ngày, first 1tr saved)

Cách triển khai, xem `assets/mascot/README.md`.

---

## Checklist review trước khi ship 1 tin nhắn mới

- [ ] Xưng "mình" — "bạn"?
- [ ] Có từ phán xét nào? (sai / lãng phí / nên / phải ...)
- [ ] Có emoji, nhưng không quá 3 cái?
- [ ] Mỗi block ý có khoảng trắng?
- [ ] Đọc lên nghe có thoải mái, không ngượng?
- [ ] Nếu là alert: có cho lựa chọn không, hay chỉ phê bình?
