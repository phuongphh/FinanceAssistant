from backend.services.llm_service import TASK_MAX_TOKENS


def test_report_text_has_higher_token_budget():
    assert TASK_MAX_TOKENS.get("report_text") == 900
