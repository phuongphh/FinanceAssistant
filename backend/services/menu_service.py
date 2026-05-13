"""Menu service — single source of truth for all menu data.

All menu text, buttons, and feature descriptions are defined here.
Both the Telegram router and OpenClaw skill consume this via API.
"""

FEATURES = [
    {
        "key": "gmail_scan",
        "emoji": "\U0001f4e7",
        "label": "Quét hóa đơn Gmail",
        "short_label": "Quét Gmail",
        "trigger_examples": ["quét gmail", "scan gmail"],
        "description": (
            "Quét Gmail tìm hóa đơn từ UOB Bank, Grab, Xanh SM, Traveloka "
            "và tự động ghi nhận chi tiêu."
        ),
    },
    {
        "key": "ocr",
        "emoji": "\U0001f4f8",
        "label": "Nhận diện hóa đơn",
        "short_label": "OCR Hóa đơn",
        "trigger_examples": ["gửi ảnh hóa đơn/receipt trực tiếp"],
        "description": (
            "Dùng AI Vision để trích xuất:\n"
            "• Tên merchant\n• Số tiền\n• Ngày\n• Danh mục\n\n"
            "Sau đó hỏi bạn confirm trước khi lưu."
        ),
    },
    {
        "key": "add_expense",
        "emoji": "\u270d\ufe0f",
        "label": "Thêm chi tiêu",
        "short_label": "Thêm chi tiêu",
        "trigger_examples": ["thêm chi tiêu 150k ăn trưa", "chi 50k grab", "ghi lại 200k shopping"],
        "description": 'Gửi theo format: "thêm chi tiêu [số tiền] [mô tả]"',
    },
    {
        "key": "report",
        "emoji": "\U0001f4ca",
        "label": "Báo cáo chi tiêu",
        "short_label": "Báo cáo",
        "trigger_examples": ["báo cáo tháng này", "báo cáo tháng 3", "tổng chi tiêu"],
        "description": (
            "Tổng hợp chi tiêu theo danh mục, so sánh với tháng trước, "
            "và đưa ra nhận xét."
        ),
    },
    {
        "key": "market",
        "emoji": "\U0001f4c8",
        "label": "Thông tin thị trường",
        "short_label": "Thị trường",
        "trigger_examples": ["thị trường hôm nay?", "VN-Index?"],
        "description": "Hiển thị VN-Index, VN30, HNX và các quỹ đầu tư (DCDS, VESAF...).",
    },
    {
        "key": "advice",
        "emoji": "\U0001f4a1",
        "label": "Gợi ý đầu tư",
        "short_label": "Gợi ý đầu tư",
        "trigger_examples": ["nên đầu tư gì?"],
        "description": "Phân tích tình hình tài chính cá nhân + thị trường để đưa ra gợi ý phù hợp.",
    },
    {
        "key": "goals",
        "emoji": "\U0001f3af",
        "label": "Mục tiêu tài chính",
        "short_label": "Mục tiêu",
        "trigger_examples": [
            "tôi muốn tiết kiệm 50tr để mua xe trong 6 tháng",
            "tiến độ mục tiêu?",
            "cập nhật mục tiêu",
        ],
        "description": "Theo dõi tiến độ mục tiêu tài chính và nhắc nhở bạn.",
    },
    {
        "key": "income",
        "emoji": "\U0001f4b0",
        "label": "Cập nhật thu nhập",
        "short_label": "Thu nhập",
        "trigger_examples": ["thu nhập tháng này là 20tr"],
        "description": "Dùng thu nhập để tính tỷ lệ tiết kiệm và đưa ra báo cáo chính xác hơn.",
    },
]

BOT_COMMANDS = [
    {"command": "menu", "description": "Hiển thị menu tính năng"},
    {"command": "start", "description": "Bắt đầu sử dụng bot"},
    {"command": "report", "description": "Báo cáo chi tiêu tháng này"},
    {"command": "goals", "description": "Xem mục tiêu tài chính"},
    {"command": "market", "description": "Thông tin thị trường"},
]


def get_menu_text() -> str:
    """Plain text menu (for OpenClaw / non-Telegram clients)."""
    lines = ["\U0001f3e6 Finance Assistant — Menu\n", "Chọn tính năng bạn muốn sử dụng:\n"]
    for f in FEATURES:
        examples = ", ".join(f'"{e}"' for e in f["trigger_examples"])
        lines.append(f'{f["emoji"]} {f["label"]} — {examples}')
    lines.append("\nNhập lệnh hoặc mô tả nhu cầu bằng tiếng Việt tự nhiên.")
    return "\n".join(lines)


def get_telegram_menu_text() -> str:
    """Markdown menu header for Telegram (used with inline keyboard)."""
    return "\U0001f3e6 *Finance Assistant — Menu*\n\nChọn tính năng bạn muốn sử dụng:"


def get_telegram_buttons() -> list[list[dict]]:
    """Inline keyboard button layout for Telegram."""
    pairs = []
    for i in range(0, len(FEATURES), 2):
        row = []
        for f in FEATURES[i : i + 2]:
            row.append({
                "text": f'{f["emoji"]} {f["short_label"]}',
                "callback_data": f'menu:{f["key"]}',
            })
        pairs.append(row)
    return pairs


def get_callback_response(callback_key: str) -> str | None:
    """Markdown response for a Telegram inline keyboard callback."""
    # callback_key format: "menu:<feature_key>"
    feature_key = callback_key.removeprefix("menu:")
    for f in FEATURES:
        if f["key"] == feature_key:
            examples = "\n".join(f'• "{e}"' for e in f["trigger_examples"])
            return (
                f'{f["emoji"]} *{f["label"]}*\n\n'
                f"Gửi:\n{examples}\n\n{f['description']}"
            )
    return None


def get_features_json() -> list[dict]:
    """Full feature list as JSON (for API consumers)."""
    return FEATURES
