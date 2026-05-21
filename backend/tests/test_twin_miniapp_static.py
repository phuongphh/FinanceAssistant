from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "backend/miniapp/static/js/twin_dashboard.js"
CSS = ROOT / "backend/miniapp/static/css/twin.css"
HTML = ROOT / "backend/miniapp/templates/twin_dashboard.html"
PREACT = ROOT / "miniapp/src/views/TwinDashboard.tsx"


def test_twin_hidden_sections_cannot_override_hidden_attribute():
    css = CSS.read_text()

    assert ".twin-page [hidden]" in css
    assert "display: none !important" in css


def test_twin_dashboard_asset_labels_are_vietnamese():
    js = JS.read_text()
    preact = PREACT.read_text()

    for source in (js, preact):
        assert "cash: 'Tiền mặt'" in source
        assert "crypto: 'Tiền mã hóa'" in source
        assert "real_estate: 'Bất động sản'" in source
        assert "stock: 'Cổ phiếu VN'" in source

    assert "crypto: 'Crypto'" not in js
    assert "{key}:" not in preact


def test_twin_dashboard_uses_safe_rendering_and_resilient_chart():
    js = JS.read_text()

    assert "typeof Chart === 'undefined'" in js
    assert "escapeHtml(labelAsset" in js
    assert "escapeHtml(value)" in js
    assert "Chưa có breakdown tài sản" not in js


def test_twin_cta_is_fully_vietnamese():
    js = JS.read_text()
    html = HTML.read_text()

    assert "Thay đổi để đạt Tối ưu" in js
    assert "Thay đổi để đạt Tối ưu" in html
    assert "Thay đổi để đạt Optimal" not in js
    assert "Thay đổi để đạt Optimal" not in html


def test_twin_preloads_opposite_scenario_for_faster_toggle():
    js = JS.read_text()

    assert "function preloadOtherScenario(activeScenario)" in js
    assert "const targetScenario = activeScenario === 'current' ? 'optimal' : 'current';" in js
    assert "if (cache[targetScenario]) return;" in js
    assert "fetch(`/api/twin?scenario=${encodeURIComponent(targetScenario)}`" in js
    assert "if (body && body.data) cache[targetScenario] = body.data;" in js
    assert "preloadOtherScenario(scenario);" in js
