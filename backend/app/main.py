"""GMP-MERP application entry point."""
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import errors
from app.api.v1 import api_router
from app.audit import hooks
from app.audit.context import AuditContext, set_context
from app.core import db
from app.core.config import get_settings
from app.core.logging import setup_logging


def create_app(*, configure_db: bool = True) -> FastAPI:
    cfg = get_settings()
    setup_logging(cfg.log_dir)
    if configure_db:
        db.configure(cfg.database_url)
    import app.models  # noqa: F401 - register metadata
    hooks.install()
    app = FastAPI(title=cfg.app_name, version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json",
                  redoc_url=None)
    app.state.trust_proxy = cfg.is_production  # behind our reverse proxy in production

    @app.middleware("http")
    async def context_and_headers(request: Request, call_next):
        cid = request.headers.get("x-correlation-id") or uuid.uuid4().hex[:16]
        request.state.correlation_id = cid
        set_context(AuditContext(correlation_id=cid))  # replaced after authentication
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = cid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = response.headers.get("Cache-Control", "no-store")
        response.headers["Content-Security-Policy"] = ("default-src 'self'; img-src 'self' data:; "
                                                       "style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
        if cfg.cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    errors.register(app)
    app.include_router(api_router)
    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built SPA (frontend/dist) when present; in production the reverse proxy may do this instead."""
    import os

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    dist = os.environ.get("MERP_FRONTEND_DIST") or os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
    dist = os.path.abspath(dist)
    if not os.path.isfile(os.path.join(dist, "index.html")):
        return
    app.mount("/assets", StaticFiles(directory=os.path.join(dist, "assets")), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse(status_code=404, content={"message": "Not found", "code": "NOT_FOUND"})
        return FileResponse(os.path.join(dist, "index.html"), headers={"Cache-Control": "no-store"})
