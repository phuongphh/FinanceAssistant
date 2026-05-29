"""Phase 4.4 Epic 1 — The Reading (WOW #1).

Covers the pure prompt builder + parser, the failure-safe service
composition (open + guess + disclaimer / fallback), the goal-label
mapping, and the ``READING_ENABLED`` feature flag on/off behaviour.
"""

from __future__ import annotations

import uuid

import pytest


# ----- build_reading_prompt (pure) --------------------------------------


@pytest.mark.parametrize("salutation", ["anh", "chị", "bạn"])
@pytest.mark.parametrize(
    "goal_label",
    [
        "muốn hiểu rõ tổng tài sản của mình",
        "muốn lên kế hoạch cho một mục tiêu lớn trong đời",
        "muốn theo dõi chi tiêu thông minh hơn",
    ],
)
def test_build_prompt_v0_threads_salutation_and_goal(salutation, goal_label):
    from backend.bot.personality.reading_prompt import build_reading_prompt

    prompt = build_reading_prompt(
        salutation=salutation, display_name="Minh", goal_label=goal_label
    )
    # Correct salutation woven into the rules + persona.
    assert f'gọi người dùng là "{salutation}"' in prompt
    assert goal_label in prompt
    assert "Minh" in prompt
    # v0 must instruct the model NOT to invent any number.
    assert "chưa biết con số" in prompt
    assert "Tổng tài sản hiện tại" not in prompt
    # Persona guardrails present.
    assert "KHÔNG phán xét" in prompt
    assert "CFO" in prompt  # the rule banning the word is in-prompt


def test_build_prompt_v1_includes_amount_context():
    from backend.bot.personality.reading_prompt import build_reading_prompt

    prompt = build_reading_prompt(
        salutation="anh",
        display_name="Minh",
        goal_label="muốn hiểu rõ tổng tài sản của mình",
        amount_text="1.5 tỷ",
    )
    assert "Tổng tài sản hiện tại: 1.5 tỷ" in prompt
    assert "đã biết tổng tài sản" in prompt


def test_build_prompt_blank_name_defaults_to_ban():
    from backend.bot.personality.reading_prompt import build_reading_prompt

    prompt = build_reading_prompt(
        salutation="bạn", display_name="", goal_label="x"
    )
    assert "Tên: bạn" in prompt


# ----- parse_reading_response (pure) ------------------------------------


def test_parse_clean_json():
    from backend.bot.personality.reading_prompt import parse_reading_response

    out = parse_reading_response('{"reading": "Em đoán anh là người cẩn thận."}')
    assert out == "Em đoán anh là người cẩn thận."


def test_parse_json_with_code_fence():
    from backend.bot.personality.reading_prompt import parse_reading_response

    raw = '```json\n{"reading": "Một nét đoán."}\n```'
    assert parse_reading_response(raw) == "Một nét đoán."


def test_parse_dict_payload():
    from backend.bot.personality.reading_prompt import parse_reading_response

    assert parse_reading_response({"reading": "abc"}) == "abc"


def test_parse_bare_sentence_accepted():
    from backend.bot.personality.reading_prompt import parse_reading_response

    # Model skipped the JSON envelope — accept the sentence as the body.
    assert parse_reading_response("Em đoán anh thích lập kế hoạch.") == (
        "Em đoán anh thích lập kế hoạch."
    )


@pytest.mark.parametrize("raw", [None, "", "   ", '{"reading": ""}', '{"x": 1}'])
def test_parse_garbage_returns_none(raw):
    from backend.bot.personality.reading_prompt import parse_reading_response

    assert parse_reading_response(raw) is None


def test_parse_truncates_overlong_body():
    from backend.bot.personality.reading_prompt import (
        MAX_READING_CHARS,
        parse_reading_response,
    )

    long = "a" * (MAX_READING_CHARS + 200)
    out = parse_reading_response({"reading": long})
    assert out is not None
    assert len(out) <= MAX_READING_CHARS


# ----- goal_label_for ---------------------------------------------------


@pytest.mark.parametrize(
    "code,expected_fragment",
    [
        ("understand_wealth", "hiểu rõ tổng tài sản"),
        ("plan_goal", "kế hoạch cho một mục tiêu"),
        ("track_spending", "theo dõi chi tiêu"),
    ],
)
def test_goal_label_for_known_codes(code, expected_fragment):
    from backend.services import reading_service

    assert expected_fragment in reading_service.goal_label_for(code)


@pytest.mark.parametrize("code", [None, "", "unknown_code"])
def test_goal_label_for_unknown_falls_back(code):
    from backend.services import reading_service

    label = reading_service.goal_label_for(code)
    assert label  # non-empty default
    assert "quản lý tài chính" in label


# ----- generate_reading (service composition) ---------------------------


@pytest.mark.asyncio
async def test_generate_reading_v0_composes_open_guess_disclaimer(monkeypatch):
    from backend.services import reading_service

    captured = {}

    async def fake_call_llm(prompt, **kwargs):
        captured.update(kwargs)
        return '{"reading": "Anh có vẻ là người cẩn thận với tiền bạc."}'

    monkeypatch.setattr(reading_service, "call_llm", fake_call_llm)

    text = await reading_service.generate_reading(
        db=None,
        user_id=uuid.uuid4(),
        salutation="anh",
        display_name="Minh",
        goal_label="muốn hiểu rõ tổng tài sản của mình",
    )

    # Guess sits between the fixed open + disclaimer.
    assert "Anh có vẻ là người cẩn thận với tiền bạc." in text
    assert "Để em đoán thử" in text  # open line from YAML
    assert "con số thật" in text  # v0 disclaimer invites the real number

    # Cache + provider contract: per-user, Groq, correct task.
    assert captured["task_type"] == "reading"
    assert captured["shared_cache"] is False
    assert captured["provider"] == "groq"
    # db=None → caching disabled (no session to read/write).
    assert captured["use_cache"] is False


@pytest.mark.asyncio
async def test_generate_reading_v1_uses_amount_and_v1_disclaimer(monkeypatch):
    from backend.services import reading_service

    async def fake_call_llm(prompt, **kwargs):
        assert "1.5 tỷ" in prompt  # amount threaded into the prompt
        return '{"reading": "Quy mô đó cho thấy anh đã đi một chặng đường."}'

    monkeypatch.setattr(reading_service, "call_llm", fake_call_llm)

    text = await reading_service.generate_reading(
        db=None,
        user_id=uuid.uuid4(),
        salutation="anh",
        display_name="Minh",
        goal_label="muốn hiểu rõ tổng tài sản của mình",
        amount_text="1.5 tỷ",
    )
    assert "Quy mô đó cho thấy anh đã đi một chặng đường." in text
    # v1 bridges to the Twin teaser, not the "show me a number" CTA.
    assert "Twin" in text


@pytest.mark.asyncio
async def test_generate_reading_falls_back_on_llm_error(monkeypatch):
    from backend.services import reading_service
    from backend.services.llm_service import LLMError

    async def boom(prompt, **kwargs):
        raise LLMError("groq down")

    monkeypatch.setattr(reading_service, "call_llm", boom)

    text = await reading_service.generate_reading(
        db=None,
        user_id=uuid.uuid4(),
        salutation="chị",
        display_name="Lan",
        goal_label="muốn theo dõi chi tiêu thông minh hơn",
    )
    # Fallback copy still references the salutation and never crashes.
    assert "chị" in text.lower()
    assert text.strip()


@pytest.mark.asyncio
async def test_generate_reading_falls_back_on_garbage(monkeypatch):
    from backend.services import reading_service

    async def fake_call_llm(prompt, **kwargs):
        return '{"unexpected": "shape"}'

    monkeypatch.setattr(reading_service, "call_llm", fake_call_llm)

    text = await reading_service.generate_reading(
        db=None,
        user_id=uuid.uuid4(),
        salutation="anh",
        display_name="Minh",
        goal_label="x",
        amount_text="200tr",
    )
    # v1 fallback copy.
    assert text.strip()
    assert "Twin" in text


# ----- READING_ENABLED feature flag -------------------------------------


def test_reading_flag_default_on(monkeypatch):
    from backend.bot.handlers import onboarding_v2

    monkeypatch.delenv("READING_ENABLED", raising=False)
    assert onboarding_v2.is_reading_enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "FALSE", "Off"])
def test_reading_flag_off(monkeypatch, val):
    from backend.bot.handlers import onboarding_v2

    monkeypatch.setenv("READING_ENABLED", val)
    assert onboarding_v2.is_reading_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "yes", "on", "anything"])
def test_reading_flag_on(monkeypatch, val):
    from backend.bot.handlers import onboarding_v2

    monkeypatch.setenv("READING_ENABLED", val)
    assert onboarding_v2.is_reading_enabled() is True
