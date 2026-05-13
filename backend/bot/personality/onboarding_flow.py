"""Onboarding flow — 5-step state machine (target ~3 minutes).

Each step is independent: the step machine only tracks *where* the
user is so routes and transaction handlers can dispatch appropriately.
The message copy lives in `backend/bot/handlers/onboarding.py`; this
module is the contract that both handler and service import from.
"""
from enum import IntEnum


class OnboardingStep(IntEnum):
    NOT_STARTED = 0
    WELCOME = 1            # welcome message sent
    ASKING_NAME = 2        # waiting for name text
    ASKING_GOAL = 3        # waiting for goal button tap
    FIRST_TRANSACTION = 4  # waiting for first expense
    AHA_MOMENT = 5         # 3-input-modes intro shown, awaiting first-asset CTA
    FIRST_ASSET = 6        # waiting for first asset add (Phase 3A)
    COMPLETED = 7


# Goal code → Vietnamese label. Kept short so labels fit inline-button
# constraints (Telegram truncates long button text on narrow screens).
PRIMARY_GOALS: dict[str, str] = {
    "save_more": "💰 Tiết kiệm nhiều hơn",
    "understand": "📊 Hiểu mình tiêu vào đâu",
    "reach_goal": "🎯 Đạt mục tiêu cụ thể",
    "less_stress": "🧘 Bớt stress về tiền",
}


# Personalised reply after the user picks a goal — keeps the same
# warm/non-prescriptive tone defined in `docs/tone_guide.md`.
GOAL_RESPONSES: dict[str, str] = {
    "save_more": (
        "Mình sẽ giúp bạn nhìn rõ chi tiêu và tìm chỗ tiết kiệm được 💰"
    ),
    "understand": (
        "Tuyệt! Mình sẽ giúp bạn thấy rõ tiền đi đâu, không còn mơ hồ nữa 📊"
    ),
    "reach_goal": (
        "Mục tiêu rõ ràng là bước đầu quan trọng nhất! "
        "Mình sẽ đồng hành cùng bạn 🎯"
    ),
    "less_stress": (
        "Mình hiểu cảm giác đó. Chúng ta sẽ đi từng bước nhỏ, không áp lực 🧘"
    ),
}
