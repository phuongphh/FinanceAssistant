# Release 10 — Broadcast Message (1.4.5.0)

> **Mục đích:** Tin nhắn gửi cho **tất cả user** thông báo về bản cập nhật 1.4.5.0.
> **Không phải deploy notes nội bộ.** Giọng văn Bé Tiền — ấm áp, thuần Việt, không jargon.

> **⚠️ Lưu ý nội bộ (KHÔNG gửi cho user) — gate theo feature flag:**
> Bản cập nhật này tập trung vào **khả năng hỏi một câu quyết định thật** (Phase 4.5) mà onboarding mới (Phase 4.6) đưa lên tuyến đầu. Chỉ broadcast **sau khi** đã bật flag tương ứng ở production, nếu không user bấm thử sẽ không thấy gì:
> - Khối "Hỏi một câu, có hướng đi ngay" → cần `PLAN_FEASIBILITY_QA_ENABLED`
> - Khối "Thanh độ nét" → cần `CLARITY_METER_ENABLED`
> - Khối "Thử nếu… thì sao" → cần `SHOCK_SIMULATION_ENABLED`
> - Xuất Excel `/export` → `EXPORT_EXCEL_ENABLED` đã `true` sẵn
>
> Nếu ở lần release này **không** bật khối nào ở trên thì **bỏ khối đó ra** khỏi bản gửi.
> **KHÔNG** nhắc tới Phase 4.7 (Guardian Layer — drift warning E1 + guardrail/kill-switch E3 đang build dark, flag off; scam-check E2 legal-blocked) và **KHÔNG** nhắc chi tiết nội bộ onboarding reset (chỉ chạm user mới) — đúng nguyên tắc không quảng cáo tính năng chưa bật.

---

## Bản đầy đủ (gửi 1 lần qua Telegram broadcast)

🎉 **Bé Tiền vừa lớn thêm một chút — có gì mới cho bạn**

Lần này tụi mình làm được điều ấp ủ đã lâu: giờ bạn có thể **hỏi Bé Tiền một câu quyết định thật**, và nhận câu trả lời thẳng thắn dựa trên chính con số của bạn 👇

🎯 **Hỏi một câu, có hướng đi ngay**
Cứ nhắn tự nhiên như đang tâm sự:
• *"3 năm nữa mình đủ cọc mua nhà chưa?"*
• *"với nhịp này, bao lâu nữa mình có quỹ khẩn cấp 6 tháng?"*
Bé Tiền nhìn tài sản + thu nhập của bạn rồi cho biết đủ hay chưa, còn cách bao xa, và mốc gần nhất trong tầm tay.

🔎 **Thanh "độ nét" — thành thật về mức chắc chắn**
Mỗi câu trả lời đi kèm một thanh **độ nét**: bức tranh tiền của bạn đang rõ tới đâu. Còn mờ thì Bé Tiền nói thật — *"đây là hướng, chưa phải con số đóng đinh"* — rồi gợi ý thêm một hai thông tin để lần sau nét hơn. Không phán xét, chỉ đồng hành.

🌊 **Thử "nếu… thì sao" mà không đụng số liệu thật**
Tò mò *"nếu mình rút 100tr ra thì danh mục xoay xở thế nào?"* — Bé Tiền chạy thử trên một bản sao, cho bạn xem trước, số liệu gốc của bạn vẫn nguyên vẹn.

📤 **Xuất toàn bộ số liệu ra Excel**
Gõ */export* là có ngay file Excel gọn gàng để bạn tự xem, lưu trữ hay đối chiếu.

🌱 **Màn chào hỏi ấm hơn cho những người bạn mới**
Bé Tiền cũng vừa làm lại phần chào hỏi cho người mới bắt đầu — hỏi đúng điều bạn muốn lo cho xong trước nhất về chuyện tiền, rồi đi cùng bạn từ đó. Nếu có bạn bè mới, mời họ thử nha.

❤️ Cảm ơn bạn đã đồng hành. Có gì chưa ổn cứ nhắn Bé Tiền nha — feedback của bạn là cách tụi mình lớn lên.

---

## Bản notification (ngắn — push notification / teaser)

🎉 **Bé Tiền có tính năng mới**
• Hỏi một câu quyết định thật: *"3 năm nữa đủ cọc nhà chưa?"* → có hướng đi ngay
• Mỗi câu trả lời kèm thanh **"độ nét"** — thành thật về mức chắc chắn
• Thử *"nếu rút 100tr thì sao"* mà không đụng số liệu thật
• Xuất toàn bộ số liệu ra Excel với */export*
Cảm ơn bạn đã đồng hành ❤️
