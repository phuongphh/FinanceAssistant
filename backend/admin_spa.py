"""SPA-friendly StaticFiles for the admin portal.

Starlette's ``StaticFiles(html=True)`` only serves ``index.html`` when the
requested path resolves to a directory. Client-side routes like ``/login``
or ``/admin/users`` have no matching file on disk, so they return 404
(see issue #791). ``SPAStaticFiles`` catches that 404 and falls back to
``index.html`` so the SPA router can take over.
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
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise
