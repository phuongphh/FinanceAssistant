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


def test_expense_modal_buttons_render_in_expected_order_and_labels():
    """Guard UI rendering after redesign of Huỷ / Quay về / Lưu buttons."""
    html = HTML.read_text()

    delete_btn = '<button id="expense-delete-btn" type="button" class="danger-btn" hidden>Huỷ</button>'
    cancel_btn = '<button id="expense-cancel-btn" type="button" class="secondary-btn">Quay về</button>'
    save_btn = '<button id="expense-save-btn" type="button" class="primary-btn">Lưu</button>'

    assert delete_btn in html
    assert cancel_btn in html
    assert save_btn in html
    assert html.index(delete_btn) < html.index(cancel_btn) < html.index(save_btn)


def test_expense_dashboard_refreshes_on_resume_events_with_debounced_background_sync():
    js = JS.read_text()

    assert "document.addEventListener('visibilitychange', onResumeRefresh);" in js
    assert "window.addEventListener('focus', onResumeRefresh);" in js
    assert "window.addEventListener('pageshow', onPageShowRefresh);" in js
    assert "if (refreshInFlight || (now - lastRefreshAt) < 3000) return;" in js


def test_expense_overview_fetch_disables_cache_and_adds_timestamp_nonce():
    js = JS.read_text()

    assert "params.set('_t', String(Date.now()));" in js
    assert "fetchAPI('/expense-dashboard/overview' + qs, { cache: 'no-store' })" in js


def test_expense_overview_has_watchdog_timeout_to_prevent_infinite_spinner():
    js = JS.read_text()

    assert "Promise.race([" in js
    assert "failAfter(15000)" in js
    assert "new Error('API timeout')" in js
