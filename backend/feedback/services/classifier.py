from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.feedback.models.feedback import Feedback
from backend.feedback.services.feedback_service import list_unclassified_feedbacks
from backend.services.llm_service import LLMError, call_llm

logger = logging.getLogger(__name__)

CLASSIFIER_VERSION = "feedback-v1-deepseek-2026-05"
VALID_CATEGORIES = {"bug", "suggestion", "praise", "question", "complaint", "other"}
VALID_SENTIMENTS = {"positive", "neutral", "negative"}
VALID_PRIORITIES = {"high", "medium", "low"}

PROMPT_TEMPLATE = """Bạn là hệ thống phân loại feedback cho app tài chính cá nhân Bé Tiền.

Nhiệm vụ: đọc feedback tiếng Việt/Anh bên dưới và trả về JSON hợp lệ, không markdown, không giải thích.

Schema bắt buộc:
{{
  "category": "bug|suggestion|praise|question|complaint|other",
  "sentiment": "positive|neutral|negative",
  "priority": "high|medium|low",
  "confidence": 0.0
}}

Luật nhanh:
- bug: lỗi kỹ thuật, bot không chạy, sai số liệu, crash, command không phản hồi.
- suggestion: đề xuất tính năng/cải tiến.
- praise: khen, hài lòng.
- question: hỏi cách dùng/chính sách.
- complaint: bực bội, chê trải nghiệm, mất niềm tin.
- other: không rõ.
- priority high nếu có mất dữ liệu/không dùng được/sai tiền nghiêm trọng; medium nếu ảnh hưởng UX; low nếu nice-to-have/khen.

Feedback: {content}
"""


def _fallback() -> dict[str, Any]:
    return {
        "category": "other",
        "sentiment": "neutral",
        "priority": "low",
        "confidence": 0.0,
        "classifier_version": CLASSIFIER_VERSION,
    }


def _extract_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


class FeedbackClassifier:
    """DeepSeek-backed classifier with deterministic safe fallback."""

    def __init__(self, *, version: str = CLASSIFIER_VERSION) -> None:
        self.version = version

    async def classify(
        self,
        content: str,
        *,
        db: AsyncSession | None = None,
    ) -> dict[str, Any]:
        prompt = PROMPT_TEMPLATE.format(content=(content or "").strip()[:5000])
        try:
            raw = await call_llm(
                prompt,
                task_type="feedback_classify",
                db=db,
                use_cache=True,
                shared_cache=True,
            )
            data = _extract_json(raw)
        except (LLMError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("Feedback classification fallback: %s", exc)
            return _fallback()

        category = str(data.get("category", "other")).strip().lower()
        sentiment = str(data.get("sentiment", "neutral")).strip().lower()
        priority = str(data.get("priority", "low")).strip().lower()
        try:
            confidence = float(data.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0

        return {
            "category": category if category in VALID_CATEGORIES else "other",
            "sentiment": sentiment if sentiment in VALID_SENTIMENTS else "neutral",
            "priority": priority if priority in VALID_PRIORITIES else "low",
            "confidence": max(0.0, min(1.0, confidence)),
            "classifier_version": self.version,
        }


async def classify_feedback_batch(
    db: AsyncSession,
    *,
    limit: int = 50,
    max_attempts: int = 3,
    classifier: FeedbackClassifier | None = None,
) -> int:
    classifier = classifier or FeedbackClassifier()
    feedbacks = await list_unclassified_feedbacks(db, limit=limit, max_attempts=max_attempts)
    processed = 0
    for feedback in feedbacks:
        try:
            feedback.classification_attempts = (feedback.classification_attempts or 0) + 1
            result = await classifier.classify(feedback.content, db=db)
            feedback.category = result["category"]
            feedback.sentiment = result["sentiment"]
            feedback.priority = result["priority"]
            feedback.classification_confidence = result["confidence"]
            feedback.classifier_version = result["classifier_version"]
            feedback.classification_error = None
            processed += 1
        except Exception as exc:  # noqa: BLE001 - worker must keep processing other rows.
            feedback.classification_attempts = (feedback.classification_attempts or 0) + 1
            feedback.classification_error = str(exc)[:2000]
            logger.exception("Failed to classify feedback id=%s", feedback.id)
    await db.flush()
    return processed
