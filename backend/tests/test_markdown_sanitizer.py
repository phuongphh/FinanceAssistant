"""Tests for markdown_sanitizer — root-cause fix for #231."""
import pytest

from backend.utils.markdown_sanitizer import sanitize_markdown


class TestSanitizeMarkdownBasic:
    def test_empty_string(self):
        assert sanitize_markdown("") == ""

    def test_plain_text_unchanged(self):
        text = "Đây là chữ thường, không có markdown."
        assert sanitize_markdown(text) == text

    def test_balanced_bold_unchanged(self):
        text = "Hôm nay *quan trọng* lắm nhé."
        assert sanitize_markdown(text) == text

    def test_balanced_italic_unchanged(self):
        text = "Đây là _gợi ý_ thôi."
        assert sanitize_markdown(text) == text

    def test_balanced_code_span_unchanged(self):
        text = "Lệnh `git status` để xem."
        assert sanitize_markdown(text) == text

    def test_complete_link_unchanged(self):
        text = "Xem thêm [tại đây](https://example.com) để biết."
        assert sanitize_markdown(text) == text

    def test_idempotent_on_already_balanced(self):
        text = "*bold* and _italic_ and `code` and [link](https://x.com)"
        once = sanitize_markdown(text)
        twice = sanitize_markdown(once)
        assert once == text
        assert twice == once


class TestUnbalancedBold:
    def test_truncated_mid_bold(self):
        # LLM ran out of tokens mid-emphasis.
        result = sanitize_markdown("Hãy đầu tư vào *VinHomes")
        assert result == "Hãy đầu tư vào \\*VinHomes"

    def test_stray_asterisk_at_end(self):
        result = sanitize_markdown("Cẩn thận nhé*")
        assert result == "Cẩn thận nhé\\*"

    def test_three_asterisks_balances_first_pair(self):
        # *foo* * — three `*` total. Greedy match: first two pair up,
        # third is stray.
        result = sanitize_markdown("*foo* *")
        assert result == "*foo* \\*"


class TestUnbalancedItalic:
    def test_unclosed_underscore(self):
        result = sanitize_markdown("Đây là _quan trọng cho việc tiết kiệm.")
        assert result == "Đây là \\_quan trọng cho việc tiết kiệm."

    def test_underscore_in_ticker_balanced(self):
        # BTC_USD ... ETH_USD — the two underscores pair up. Renders as
        # italic content between them, but parses without error.
        text = "BTC_USD và ETH_USD"
        out = sanitize_markdown(text)
        # No escapes: pairs are balanced.
        assert "\\_" not in out


class TestUnbalancedBacktick:
    def test_unclosed_code_span(self):
        result = sanitize_markdown("Chạy lệnh `npm install để cài.")
        assert result == "Chạy lệnh \\`npm install để cài."

    def test_unclosed_triple_backtick(self):
        result = sanitize_markdown("Code:\n```\npython main.py")
        assert result.startswith("Code:\n\\`\\`\\`")

    def test_balanced_triple_backtick_unchanged(self):
        text = "```\npython main.py\n```"
        assert sanitize_markdown(text) == text

    def test_asterisk_inside_code_span_preserved(self):
        # Code spans should preserve content verbatim — the ``*`` inside
        # should NOT be touched.
        text = "Use `*` for bold."
        assert sanitize_markdown(text) == text


class TestBrokenLinks:
    def test_unclosed_bracket(self):
        result = sanitize_markdown("Xem [thêm tại đây")
        assert result == "Xem \\[thêm tại đây"

    def test_bracket_without_paren(self):
        # [text] without (url) — Telegram needs the full shape.
        result = sanitize_markdown("Xem [thêm] về vấn đề này.")
        assert result == "Xem \\[thêm] về vấn đề này."

    def test_unclosed_url_paren(self):
        result = sanitize_markdown("Xem [thêm](https://example.com chi tiết.")
        assert result == "Xem \\[thêm](https://example.com chi tiết."


class TestListBullets:
    def test_asterisk_bullet_at_line_start_escaped(self):
        # The killer LLM output mode: standard-Markdown bullet list.
        text = "Gợi ý cho bạn:\n* Mục 1\n* Mục 2\n* Mục 3"
        result = sanitize_markdown(text)
        assert "\\* Mục 1" in result
        assert "\\* Mục 2" in result
        assert "\\* Mục 3" in result

    def test_indented_bullet_escaped(self):
        text = "List:\n  * Sub-item"
        result = sanitize_markdown(text)
        assert "  \\* Sub-item" in result

    def test_bullet_does_not_affect_inline_bold(self):
        text = "Note: *quan trọng* lắm.\n* Mục 1"
        result = sanitize_markdown(text)
        # Inline bold preserved, bullet escaped.
        assert "*quan trọng*" in result
        assert "\\* Mục 1" in result

    def test_dash_bullets_unchanged(self):
        # ``-`` is not a Markdown opener for Telegram, leave alone.
        text = "List:\n- Item 1\n- Item 2"
        assert sanitize_markdown(text) == text


class TestRealWorldAdvisoryOutput:
    """Cases drawn from real LLM advisory failures we've seen in logs."""

    def test_truncated_advisory(self):
        # The original failure from #230 logs: response cut off at
        # ~1200 chars mid-bold.
        text = (
            "Mình thấy bạn đang quan tâm đến BĐS. Một vài hướng:\n\n"
            "*Option 1*: Mua chung cư cho thuê. Lợi nhuận ổn định 5-7%/năm.\n"
            "*Option 2*: Mua đất nền vùng ven. Tăng giá nhanh hơn nhưng *rủi ro"
        )
        out = sanitize_markdown(text)
        # The unclosed `*rủi ro` opener at end gets escaped.
        assert out.endswith("\\*rủi ro")
        # The complete pairs are still intact.
        assert "*Option 1*" in out
        assert "*Option 2*" in out

    def test_mixed_problems(self):
        text = (
            "Tóm lại:\n"
            "* Tiết kiệm trước, đầu tư sau\n"
            "* Mua [VN30](https://etf.vn nếu thận trọng\n"
            "* _Đa dạng hoá quan trọng"
        )
        out = sanitize_markdown(text)
        # All three bullet markers escaped.
        assert out.count("\\*") >= 3
        # Broken link bracket escaped.
        assert "\\[VN30]" in out
        # Unclosed italic escaped.
        assert "\\_Đa dạng hoá" in out

    def test_does_not_disturb_clean_advisory(self):
        # When the LLM produces clean Markdown, we don't mangle it.
        text = (
            "Gợi ý của mình:\n\n"
            "Bạn có thể thử *Option A*: gửi tiết kiệm 12 tháng "
            "(_ổn định, lãi ~5%_).\n\n"
            "Hoặc xem thêm [bài viết này](https://example.com).\n\n"
            "_Đây là gợi ý cá nhân, không phải lời khuyên đầu tư._"
        )
        # Greedy matching pairs every entity correctly here.
        assert sanitize_markdown(text) == text
