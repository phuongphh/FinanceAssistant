from agent_loop.cli import po_publish_notice


def test_po_notice_has_next_step_and_no_premature_test_request():
    text = po_publish_notice(
        1, 2, "Better news", True, "https://github.com/example/repo/pull/2"
    )
    assert "Bạn chưa cần" in text
    assert "Chưa có bản Dev" in text
    assert "Markdown" not in text
    assert len(text.split()) < 120
    assert "chưa đạt" in po_publish_notice(1, 2, "Better news", False)
