"""SPA-friendly StaticFiles for the admin portal.

Starlette's ``StaticFiles(html=True)`` only serves ``index.html`` when the
requested path resolves to a directory. Client-side routes like ``/login``
or ``/admin/users`` have no matching file on disk, so they return 404
(see issue #791). ``SPAStaticFiles`` catches that 404 and falls back to
``index.html`` *only for browser navigation requests* so the SPA router
can take over — without turning unknown API endpoints or missing static
assets into bogus HTML 200s.
"""

from __future__ import annotations

from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Scope


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or not self._should_fall_back(path, scope):
                raise
            return await super().get_response("index.html", scope)

    @staticmethod
    def _should_fall_back(path: str, scope: Scope) -> bool:
        # Never swallow 404s for API endpoints — monitoring and clients
        # rely on real 404s for unknown endpoints. (Mount at "/" passes
        # the path with the mount prefix stripped, so /api/v1/x arrives
        # here as "api/v1/x".)
        if path.startswith("api/") or path.startswith("/api/"):
            return False
        # Only fall back for browser navigation requests, which advertise
        # text/html in Accept. Missing JS/CSS/images use other Accept
        # values; serving HTML for them would break browser parsing.
        for name, value in scope.get("headers") or ():
            if name == b"accept":
                return b"text/html" in value.lower()
        return False
