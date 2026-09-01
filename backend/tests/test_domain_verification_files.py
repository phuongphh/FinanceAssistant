"""Domain-verification files must be served verbatim from the public root.

Zalo verifies ownership of ``finance.nuitruc.ai`` by fetching the token
file it hands out in the Developer Console. The SPA mounted at ``/`` in
``backend.main`` answers unknown paths with ``index.html`` and HTTP 200
whenever the caller accepts ``text/html`` — so "the URL opens" proves
nothing. These tests pin the two things that actually matter: the file is
present in the repo, and the app returns *its* bytes rather than the SPA
fallback.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.admin_spa import SPAStaticFiles
from backend.main import _public_file_route, app

PUBLIC_ROOT = Path(__file__).resolve().parents[1] / "static" / "public"
ZALO_VERIFIER = "zalo_verifierUVAzBV_0CW8Sm8TLzUeIJoh7YbZ6iL03CJCt.html"


def test_zalo_verification_file_is_committed():
    assert (PUBLIC_ROOT / ZALO_VERIFIER).is_file()


def test_zalo_verification_file_carries_the_console_token():
    content = (PUBLIC_ROOT / ZALO_VERIFIER).read_text()

    assert 'property="zalo-platform-site-verification"' in content
    assert 'content="UVAzBV_0CW8Sm8TLzUeIJoh7YbZ6iL03CJCt"' in content


def test_app_serves_the_verification_file():
    client = TestClient(app)

    response = client.get(f"/{ZALO_VERIFIER}", headers={"Accept": "text/html"})

    assert response.status_code == 200
    assert "zalo-platform-site-verification" in response.text
    assert response.text == (PUBLIC_ROOT / ZALO_VERIFIER).read_text()


def test_public_root_file_wins_over_the_spa_fallback(tmp_path):
    """The token must survive a root SPA mount, which is the prod shape.

    ``backend/static/admin`` only exists after a build, so the mounts in
    ``backend.main`` are absent in a fresh checkout. Rebuild the same
    registration order here — public file first, SPA at ``/`` second — so
    the regression is caught even when the SPA is not built.
    """
    spa_dir = tmp_path / "admin"
    spa_dir.mkdir()
    (spa_dir / "index.html").write_text("<html><body>admin SPA</body></html>")

    verifier = PUBLIC_ROOT / ZALO_VERIFIER
    spa_app = FastAPI()
    spa_app.add_api_route(
        f"/{ZALO_VERIFIER}",
        _public_file_route(verifier),
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )
    spa_app.mount("/", SPAStaticFiles(directory=str(spa_dir), html=True))
    client = TestClient(spa_app)

    # Sanity check: the fallback really does answer unknown paths with 200.
    fallback = client.get("/no-such-file.html", headers={"Accept": "text/html"})
    assert fallback.status_code == 200
    assert "admin SPA" in fallback.text

    response = client.get(f"/{ZALO_VERIFIER}", headers={"Accept": "text/html"})

    assert response.status_code == 200
    assert response.text == verifier.read_text()
