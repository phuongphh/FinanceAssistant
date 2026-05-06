# Issue #224

[Story] Telegram `/about`: Product About page with privacy-first messaging

## Context

Người dùng cần thêm một command mới cho Telegram bot để mở trang About (về sản phẩm) của FinanceAssistant trước khi mở rộng các tính năng SaaS/public beta.

Trang About không chỉ hiển thị thông tin app, mà còn phải tạo cảm giác tin cậy: sản phẩm quản lý tài chính cá nhân nên cần nhấn mạnh quyền riêng tư, minh bạch dữ liệu, và thông tin công ty đứng sau sản phẩm.

## Recommendation — nội dung trang About

Nên giữ nội dung ngắn, rõ, thân thiện với Telegram:

```text
💼 FinanceAssistant
Personal CFO cho tài chính cá nhân của bạn.

Version: <APP_VERSION>
© <YEAR> Nuitruc AI. All rights reserved.
Company: Nuitruc AI — https://nuitruc.ai

🔒 Privacy-first
FinanceAssistant chỉ dùng dữ liệu tài chính của bạn để ghi nhận, phân tích và hỗ trợ ra quyết định tốt hơn.
Không bán dữ liệu cá nhân. Không chia sẻ dữ liệu tài chính cho bên thứ ba nếu không có sự đồng ý của bạn.

Privacy Policy: <PRIVACY_POLICY_URL>
```

## Product copy guidance

- Dùng tone ngắn gọn, đáng tin, không quá marketing.
- Nhấn mạnh “Privacy-first” bằng emoji/heading để người dùng dễ thấy ngay.
- Company link nên là inline URL: `https://nuitruc.ai`.
- Version nên lấy từ config/package metadata, không hardcode nếu repo đã có biến version.
- Copyright year nên lấy theo runtime year hoặc config.
- Privacy Policy URL nên để config/env để sau này đổi link mà không cần sửa code.

## Scope

Implement một Telegram bot command mới:

- `/about` — trả về nội dung About trực tiếp trong Telegram.
- Nếu bot đang có menu command list, thêm `/about` vào danh sách command/menu tương ứng.
- Nội dung phải gồm:
  - Product name: `FinanceAssistant`
  - Version
  - Copyright
  - Company name: `Nuitruc AI`
  - Company website: `https://nuitruc.ai`
  - Privacy policy section nổi bật
  - Privacy Policy link/config placeholder

## Acceptance Criteria

- Khi gửi `/about`, bot trả về About message bằng tiếng Việt hoặc song ngữ ngắn gọn.
- Message hiển thị đúng version hiện tại của app.
- Message có copyright đầy đủ.
- Message có link công ty `https://nuitruc.ai`.
- Message có phần `Privacy-first` hoặc `Privacy Policy` được nhấn mạnh rõ ràng.
- Privacy Policy URL không bị hardcode sâu trong business logic; ưu tiên config/env/content file.
- Có test hoặc smoke check phù hợp cho command handler/formatter.
- Không log dữ liệu tài chính cá nhân khi xử lý `/about`.

## Implementation Notes

- Tìm nơi xử lý Telegram commands hiện tại trước khi code.
- Ưu tiên tách formatter/content khỏi handler để dễ chỉnh copy.
- Nếu repo đã có content YAML cho menu/copy, cân nhắc đặt About copy ở đó.
- Nếu chưa có privacy policy URL chính thức, dùng placeholder config như `PRIVACY_POLICY_URL` và default về company site hoặc `https://nuitruc.ai/privacy` sau khi xác nhận.

## Open Questions

1. Privacy Policy URL chính thức là gì?
   - Gợi ý mặc định: `https://nuitruc.ai/privacy`
2. Version source nên lấy từ đâu?
   - `pyproject.toml`, package metadata, env var, hoặc constant hiện có.
3. Copy nên thuần tiếng Việt hay song ngữ Việt/Anh?
   - Gợi ý: tiếng Việt ngắn gọn cho owner hiện tại; có thể chuyển song ngữ khi public beta.

## Out of Scope

- Không implement trang web privacy policy.
- Không thay đổi onboarding hoặc legal consent flow.
- Không thêm tracking/analytics riêng cho `/about` trừ khi đã có convention sẵn.
