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


def test_expense_localised_constants_declared_before_init_usage():
    """Regression for the PR #758 Temporal Dead Zone bug.

    ``applyLocalizedKeywords()`` is called during the IIFE bootstrap and
    reads ``const UI_KEYWORDS``. In the original PR the const was
    declared lower in the same scope, so the call hit TDZ and aborted
    init — the user saw "Đang tải chi tiêu…" forever. Lock the source
    order so a future move can't silently re-introduce the bug.
    """
    js_lines = JS.read_text().splitlines()

    def first_index(predicate):
        for idx, line in enumerate(js_lines):
            if predicate(line):
                return idx
        return -1

    ui_keywords_decl = first_index(lambda line: line.lstrip().startswith("const UI_KEYWORDS"))
    date_format_decl = first_index(lambda line: line.lstrip().startswith("const DATE_FORMAT_BY_LANGUAGE"))
    apply_call = first_index(lambda line: "applyLocalizedKeywords();" in line)

    assert ui_keywords_decl >= 0, "UI_KEYWORDS const declaration missing"
    assert date_format_decl >= 0, "DATE_FORMAT_BY_LANGUAGE const declaration missing"
    assert apply_call >= 0, "applyLocalizedKeywords() init call missing"
    assert ui_keywords_decl < apply_call, (
        f"UI_KEYWORDS declared on line {ui_keywords_decl + 1} but read on "
        f"line {apply_call + 1} — TDZ violation, init will throw."
    )
    assert date_format_decl < apply_call, (
        f"DATE_FORMAT_BY_LANGUAGE declared on line {date_format_decl + 1} "
        f"but reachable from init on line {apply_call + 1} — TDZ risk."
    )


def test_expense_init_wrapped_in_try_catch_with_error_state_fallback():
    """The bootstrap must surface a visible error if anything throws.

    Without this guard, a sync throw during init (TDZ, missing DOM
    node, Telegram shim drift) leaves the user staring at the initial
    "Đang tải chi tiêu…" spinner forever. The catch handler must
    populate ``errorMessage``, flip to the error state, and bind a
    fresh reload listener since the original retry listener may not
    have attached.
    """
    js = JS.read_text()

    assert "function handleInitFailure(err)" in js, "init failure handler missing"
    assert "expense_dashboard init failed" in js, "console.error tag missing"
    assert "showState('error')" in js, "error state not shown on init failure"
    assert "window.location.reload()" in js, "reload fallback listener missing"
    assert "tải lại giúp mình nhé" in js, (
        "user-facing Vietnamese fallback message missing or off-tone "
        "(must match Bé Tiền warm-companion voice)"
    )
