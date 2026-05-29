"""LLM prompt + parser for "The Reading" (Phase 4.4, Epic 1, WOW #1).

The Reading is the minute-1 WOW: right after the user picks an
onboarding goal — and again once they reveal a real number — Bé Tiền
"đoán" (guesses) a warm, specific-feeling sketch of their financial
self. The point is *probability over precision*: it opens humbly
("để em đoán thử…") and never asserts, mirroring the Twin weather
metaphor philosophy.

This module owns only the LLM half:

- ``READING_PROMPT``: the prompt *structure* (rules, schema). The
  fixed user-facing wrapper text (opening line, disclaimer, CTA) lives
  in ``content/onboarding/welcome_v2.yaml`` under ``reading`` — code
  holds structure, YAML holds copy.
- ``build_reading_prompt()``: fills the template for v0 (zero data:
  salutation + name + goal) or v1 (adds the real asset number).
- ``parse_reading_response()``: pure JSON parser → the guess body, or
  ``None`` when the LLM returns garbage (caller falls back to YAML copy).

Persona is a HARD constraint (``persona-critical``): zero judgment,
zero "nên/phải/dạy đời", zero "CFO", 100% correct salutation. These are
encoded in the prompt rules and gated by ``prompt-tester`` before merge.

Cost & caching
--------------
``call_llm`` keys on ``(task_type, user_id, prompt_hash)``; the Reading
is per-user (``shared_cache=False``) and runs on Groq for sub-second
latency so the minute-1 beat doesn't stall. Output is tiny (one short
paragraph) — a few hundred tokens.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


# Upper bound on the guess body we accept from the LLM. The Reading is
# meant to be 2-3 sentences; anything longer is the model rambling and
# we'd rather truncate than spam the user mid-onboarding.
MAX_READING_CHARS = 600


READING_PROMPT = """Bạn là Bé Tiền — người đồng hành quản lý tài sản, nhắn tin với một người Việt vừa bắt đầu dùng app. Em xưng "em", gọi người dùng là "{salutation}".

NHIỆM VỤ: Dựa trên vài thông tin ít ỏi dưới đây, hãy "đoán thử" một nét chân dung tài chính của {salutation} — cụ thể đủ để họ thấy "ơ sao đúng vậy", nhưng khiêm tốn vì em mới chỉ đoán.

QUY TẮC BẮT BUỘC:
1. Xưng hô CHÍNH XÁC: gọi người dùng là "{salutation}", tự xưng "em". Không dùng xưng hô nào khác.
2. TUYỆT ĐỐI KHÔNG phán xét, KHÔNG dạy đời, KHÔNG dùng "nên", "phải", "cần phải". Không chê tiêu hoang hay tiết kiệm ít.
3. Công nhận một điểm mạnh thầm lặng gắn với mục tiêu của họ (vd người muốn hiểu tài sản thường cẩn thận, người lên kế hoạch thường có tầm nhìn xa, người muốn theo dõi chi tiêu thường có kỷ luật và ý thức rõ về tiền).
4. Giọng ấm, tự nhiên như nhắn tin cho người thân. 2-3 câu. KHÔNG markdown, KHÔNG gạch đầu dòng, KHÔNG emoji thừa (tối đa 1).
5. KHÔNG bịa con số cụ thể. {number_rule}
6. KHÔNG dùng từ "CFO", "Personal CFO", hay thuật ngữ tài chính lạnh lùng.
7. KHÔNG mở đầu bằng lời chào ("chào", "xin chào") — phần mở đầu đã có sẵn; em chỉ viết phần đoán.

THÔNG TIN VỀ NGƯỜI DÙNG:
- Tên: {display_name}
- Điều họ mong Bé Tiền giúp: {goal_label}
{number_context}
OUTPUT — TRẢ VỀ JSON DUY NHẤT (không thêm text giải thích):
{{"reading": "phần em đoán, 2-3 câu"}}"""


# Slotted into the prompt for the two phases. v0 has no number; v1 does.
_NUMBER_RULE_V0 = (
    "Lúc này em chưa biết con số nào của họ — chỉ đoán qua mục tiêu và cảm nhận, "
    "đừng nhắc tới bất kỳ số tiền cụ thể nào."
)
_NUMBER_RULE_V1 = (
    "Em đã biết tổng tài sản hiện tại của họ (ghi bên dưới). Có thể nhắc tới quy mô "
    "đó một cách trân trọng, nhưng KHÔNG bịa thêm số khác."
)


def build_reading_prompt(
    *,
    salutation: str,
    display_name: str,
    goal_label: str,
    amount_text: str | None = None,
) -> str:
    """Fill ``READING_PROMPT`` for v0 (no number) or v1 (with number).

    ``amount_text`` is a pre-formatted human string (e.g. "1.5 tỷ") when
    present — the service formats it via ``currency_utils`` so this stays
    a pure string-composer with no money/Decimal logic.
    """
    if amount_text:
        number_rule = _NUMBER_RULE_V1
        number_context = f"- Tổng tài sản hiện tại: {amount_text}\n"
    else:
        number_rule = _NUMBER_RULE_V0
        number_context = ""

    return READING_PROMPT.format(
        salutation=salutation,
        display_name=display_name or "bạn",
        goal_label=goal_label,
        number_rule=number_rule,
        number_context=number_context,
    )


def parse_reading_response(raw: str | dict | None) -> str | None:
    """Extract the guess body from the LLM payload. Pure (no LLM call).

    Tolerates ```json fences and a bare string. Returns ``None`` on any
    parse failure or empty body so the caller can fall back to the fixed
    YAML copy — the minute-1 moment must never crash.
    """
    if raw is None:
        return None

    if isinstance(raw, dict):
        data: dict = raw
    else:
        text = str(raw).strip()
        if not text:
            return None
        if text.startswith("```"):
            lines = [ln for ln in text.splitlines() if not ln.startswith("```")]
            text = "\n".join(lines).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # Some models skip the JSON envelope and just write the
            # sentence. Accept that as the body rather than dropping it.
            if text.startswith("{"):
                logger.warning("reading: non-JSON payload: %r", text[:200])
                return None
            return _clean_body(text)
        if not isinstance(parsed, dict):
            return None
        data = parsed

    body = data.get("reading")
    if not isinstance(body, str):
        return None
    return _clean_body(body)


def _clean_body(body: str) -> str | None:
    body = (body or "").strip().strip('"').strip()
    if not body:
        return None
    if len(body) > MAX_READING_CHARS:
        body = body[:MAX_READING_CHARS].rstrip()
    return body
