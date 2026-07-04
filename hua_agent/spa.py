"""SPA static file fallback handler."""

import os
from urllib.parse import unquote

from fastapi import HTTPException
from fastapi.responses import FileResponse

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def create_spa_fallback():
    """Create the SPA fallback route handler."""
    static_dir = os.path.join(_PROJECT_ROOT, "static", "dist")

    def spa_fallback(path: str):
        decoded = unquote(path)
        if "%" in decoded:
            raise HTTPException(status_code=404, detail="Not Found")

        full = os.path.join(static_dir, decoded)
        real_full = os.path.realpath(full)
        real_static = os.path.realpath(static_dir)

        if not real_full.startswith(real_static + os.sep) and real_full != real_static:
            raise HTTPException(status_code=404, detail="Not Found")

        import stat as _stat

        try:
            _stat.S_IFMT(os.stat(full).st_mode)
            return FileResponse(full)
        except (FileNotFoundError, NotADirectoryError):
            pass
        return FileResponse(os.path.join(static_dir, "index.html"))

    return spa_fallback
