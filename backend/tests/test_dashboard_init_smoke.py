"""Bootstrap smoke tests for the miniapp dashboard JS bundles.

The Telegram Mini App dashboards are vanilla IIFE scripts that wire up
event listeners and trigger the first network fetch synchronously at
module load. A sync throw inside that bootstrap (TDZ on `const`, missing
DOM node, Telegram shim drift) silently aborts the IIFE and leaves the
user staring at the initial "Đang tải…" spinner forever — the exact
failure mode that motivated this test after PR #758 introduced a
``Cannot access 'UI_KEYWORDS' before initialization`` regression in
``expense_dashboard.js``.

The static string-matching tests in ``test_expense_miniapp_static.py``
can't catch that class of bug because they never execute the JS. This
suite spawns Node with the harness at ``js_dashboard_smoke.cjs``, which
runs each bundle inside a ``vm`` sandbox with a minimal DOM / Telegram /
fetch stub and asserts (a) the bootstrap returns without throwing and
(b) it issued at least one network request (proof it reached its
initial render call).

Tests skip cleanly if Node isn't on PATH so the suite stays runnable on
minimal environments. The local + dev shell + intent-tests CI image all
ship Node ≥18.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "backend/tests/js_dashboard_smoke.cjs"
STATIC_JS_DIR = ROOT / "backend/miniapp/static/js"

NODE = shutil.which("node")

# Dashboards that bootstrap via an IIFE. Each must issue at least one
# fetch during init — the assertion that catches "silent halt" bugs.
IIFE_DASHBOARDS = [
    "expense_dashboard.js",
    "wealth_dashboard.js",
    "twin_dashboard.js",
    "dashboard.js",
]


def _run_harness(target: Path) -> dict:
    """Invoke the Node smoke harness against `target` and parse its JSON."""
    proc = subprocess.run(
        [NODE, str(HARNESS), str(target)],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=str(ROOT),
    )
    # Harness writes a single JSON line to stdout on both success and
    # failure paths; stderr carries `console.*` output from the bundle.
    stdout = (proc.stdout or "").strip()
    if not stdout:
        raise AssertionError(
            f"harness produced no stdout (exit={proc.returncode}); stderr=\n{proc.stderr}"
        )
    last_line = stdout.splitlines()[-1]
    try:
        payload = json.loads(last_line)
    except json.JSONDecodeError as exc:  # pragma: no cover - guard
        raise AssertionError(
            f"harness stdout not JSON: {last_line!r} (exit={proc.returncode})"
        ) from exc
    payload["_returncode"] = proc.returncode
    payload["_stderr"] = proc.stderr
    return payload


@pytest.mark.skipif(NODE is None, reason="Node.js not on PATH; smoke test skipped.")
@pytest.mark.parametrize("dashboard", IIFE_DASHBOARDS)
def test_dashboard_iife_initialises_without_throwing(dashboard: str) -> None:
    """The bundle must run to completion under the smoke harness.

    A synchronous throw during the IIFE means the user never gets past
    the loading spinner. Regression for the PR #758 TDZ bug on
    ``UI_KEYWORDS`` in ``expense_dashboard.js``.
    """
    target = STATIC_JS_DIR / dashboard
    assert target.exists(), f"dashboard bundle missing: {target}"
    result = _run_harness(target)
    assert result["ok"], (
        f"{dashboard} bootstrap threw during init:\n"
        f"  error: {result.get('error')}\n"
        f"  stack: {result.get('stack')}\n"
        f"  stderr: {result.get('_stderr')}"
    )


@pytest.mark.skipif(NODE is None, reason="Node.js not on PATH; smoke test skipped.")
@pytest.mark.parametrize("dashboard", IIFE_DASHBOARDS)
def test_dashboard_init_reaches_first_fetch(dashboard: str) -> None:
    """Init must issue at least one network request.

    A silent abort (eg. an exception swallowed by the new try/catch
    bootstrap guard) would leave fetchCalls at 0 — we'd still see the
    error state instead of the spinner, but the dashboard would never
    load. Forcing a non-zero fetch count keeps the guard from masking
    real init regressions.
    """
    target = STATIC_JS_DIR / dashboard
    result = _run_harness(target)
    assert result["fetchCalls"] >= 1, (
        f"{dashboard} init completed but issued no fetch — "
        f"likely a silent halt (urls={result.get('urls')!r}).\n"
        f"  stderr: {result.get('_stderr')}"
    )


@pytest.mark.skipif(NODE is None, reason="Node.js not on PATH; smoke test skipped.")
def test_smoke_harness_catches_simulated_tdz_violation(tmp_path: Path) -> None:
    """Self-test: the harness must surface a Temporal Dead Zone error.

    This guards the smoke harness itself — if a future refactor
    accidentally hides exceptions, the IIFE tests would silently start
    passing even on broken bundles.
    """
    bad = tmp_path / "bad_dashboard.js"
    bad.write_text(
        "(function () {\n"
        "    'use strict';\n"
        "    function read() { return CONSTANT; }\n"
        "    read();\n"
        "    const CONSTANT = 'should be unreachable';\n"
        "})();\n"
    )
    result = _run_harness(bad)
    assert not result["ok"], "harness must report TDZ throw as failure"
    assert "CONSTANT" in (result.get("error") or ""), (
        f"expected TDZ error mentioning CONSTANT; got: {result.get('error')}"
    )
    assert result["fetchCalls"] == 0
