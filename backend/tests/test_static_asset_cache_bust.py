"""Lock the contract between miniapp templates and the cache-bust hash.

`backend/miniapp/routes.py::_compute_static_version()` hashes every file
in `_STATIC_REF_FILES` to produce the `?v=<hash>` query string that
Telegram's WebView uses as a cache key. Any static JS/CSS asset the
templates `<script>`/`<link>` to must be in that tuple — otherwise an
edit to it ships with an unchanged hash and users keep the stale
cached bundle after deploy.

The dashboard_common.js helper bundle was introduced in PR #768 and is
loaded by three templates (expense, wealth, dashboard). Forgetting to
register it was the P1 catch from chatgpt-codex-connector — this test
prevents a recurrence for any future shared bundle.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = ROOT / "backend/miniapp/templates"
STATIC_DIR = ROOT / "backend/miniapp/static"

# Mirrors the rewriter pattern in routes.py — any `/miniapp/static/...`
# reference inside the HTML gets a `?v=<hash>` appended at serve time.
STATIC_URL_PATTERN = re.compile(r'/miniapp/static/([a-zA-Z0-9_/.-]+\.(?:js|css))')


def _referenced_static_files() -> set[str]:
    """Scan every template under templates/ for /miniapp/static/* refs."""
    refs: set[str] = set()
    for html in TEMPLATES_DIR.glob("*.html"):
        for match in STATIC_URL_PATTERN.finditer(html.read_text()):
            refs.add(match.group(1))
    return refs


def _registered_static_files() -> tuple[str, ...]:
    """Pull the live tuple out of routes.py without importing the module
    (fastapi may not be installed in the slim test env)."""
    routes_src = (ROOT / "backend/miniapp/routes.py").read_text()
    match = re.search(
        r"_STATIC_REF_FILES\s*=\s*\(([^)]+)\)",
        routes_src,
        re.DOTALL,
    )
    assert match, "could not locate _STATIC_REF_FILES in routes.py"
    entries = re.findall(r'"([^"]+)"', match.group(1))
    return tuple(entries)


def test_every_referenced_static_asset_is_in_cache_bust_hash() -> None:
    """Templates must not load a /miniapp/static/* asset that the cache-
    bust hash ignores. Adding a new shared bundle (the PR #768 case)
    without registering it ships stale logic to every user who already
    has the previous build cached.
    """
    referenced = _referenced_static_files()
    registered = set(_registered_static_files())
    missing = referenced - registered
    assert not missing, (
        f"Static assets referenced in templates but missing from "
        f"_STATIC_REF_FILES — edits won't bust the WebView cache:\n"
        + "\n".join(f"  - {path}" for path in sorted(missing))
        + "\n\nAdd them to _STATIC_REF_FILES in backend/miniapp/routes.py."
    )


def test_dashboard_common_js_registered_for_cache_bust() -> None:
    """Explicit guard for the shared dashboard helper bundle introduced
    in PR #768. Three dashboards depend on it; a stale-cache regression
    here would mask shared-helper bug fixes across the whole product.
    """
    assert "js/dashboard_common.js" in _registered_static_files(), (
        "js/dashboard_common.js missing from _STATIC_REF_FILES. "
        "Without it, edits to the shared helpers ship with an "
        "unchanged ?v=<hash> and Telegram WebView keeps stale bundle."
    )


def test_every_registered_asset_actually_exists_on_disk() -> None:
    """Catch the inverse problem: a stale entry in _STATIC_REF_FILES
    that no longer exists on disk would crash _compute_static_version()
    at process start (FileNotFoundError under the .read_bytes() call).
    """
    missing = [path for path in _registered_static_files() if not (STATIC_DIR / path).exists()]
    assert not missing, (
        "_STATIC_REF_FILES references non-existent files (will crash "
        "on app startup):\n" + "\n".join(f"  - {path}" for path in missing)
    )
