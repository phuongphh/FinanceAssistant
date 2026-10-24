# Issue #919

NLU: \"được bố cho 500k\" không được nhận diện là money-in trong menu Chi tiêu

## Vấn đề

Khi user gõ **"được bố cho 500k"** trong menu CHI TIÊU, Bé Tiền **không** nhận diện đây là một giao dịch **tiền vào (money-in)** mà ghi nhầm thành chi tiêu.

Menu Chi tiêu lại hứa hẹn các ví dụ như:
- "được thưởng 200k"
- "được bố cho 500k"
- "được lì xì 50k trên momo"

→ tất cả phải là **money-in**.

## Nguyên nhân

"được bố cho 500k" sau khi strip dấu → `duoc bo cho 500k`. Substring `duoc cho` bị từ "bo" chen vào nên không khớp, handler cũ ghi nhầm thành expense. Không có fast-path / Tier-1 pattern nào bắt được case này.

## Hint sản phẩm

Khi câu có từ **"được"** đứng trước một động từ cho/tặng (cho, tặng, biếu, thưởng, lì xì, mừng tuổi, hỗ trợ...) thì **thông thường là một giao dịch tiền vào**.

Lưu ý: "được" cũng là **resultative particle** ("mua được áo" = mua thành công → CHI TIÊU), nên phải veto khi có động từ hành động đứng trước.

## Yêu cầu

- Enhance NLU Tier 1 (rule-based) và Tier 2 (LLM) để bắt money-in cho các case "được ... cho/thưởng/lì xì X".
- Đảm bảo consistency, tốc độ phản hồi, UI/UX, security.
- Viết đầy đủ unit test.

https://claude.ai/code/session_017oCtfHUSEeb7V51bjBJpn4
