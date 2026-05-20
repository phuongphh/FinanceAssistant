from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "backend/miniapp/static/js/expense_dashboard.js"
CSS = ROOT / "backend/miniapp/static/css/expense.css"
HTML = ROOT / "backend/miniapp/templates/expense_dashboard.html"


def test_expense_modal_actions_have_consistent_three_button_layout():
    css = CSS.read_text()

    assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in css
    assert "min-height: 48px;" in css
    assert "white-space: nowrap;" in css


def test_expense_reverse_keyword_is_vietnamese_by_default():
    html = HTML.read_text()
    js = JS.read_text()

    assert '<button id="expense-delete-btn" type="button" class="danger-btn" hidden>Huỷ</button>' in html
    assert "reverse: 'Huỷ'" in js
    assert "if (els.modalDelete) els.modalDelete.textContent = keywords.reverse;" in js
    assert "Reverse</button>" not in html
