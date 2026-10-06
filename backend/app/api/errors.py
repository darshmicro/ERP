import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.audit.context import get_context
from app.core import db
from app.core.errors import AppError
from app.core.logging import app_log, security_log
from app.core.time import utcnow
from app.models.audit import ErrorLog


def _body(message, code, ref=None, details=None, rule_id=None, cid=None):
    return {"message": message, "code": code, "reference": ref, "details": details, "rule_id": rule_id,
            "correlation_id": cid, "timestamp": utcnow().isoformat()}


def _log_error(request: Request, exc: Exception) -> str:
    ctx = get_context()
    s = db.new_session()
    try:
        row = ErrorLog(correlation_id=getattr(request.state, "correlation_id", None), route=request.url.path[:200],
                       user_id=ctx.user_id, error_type=type(exc).__name__)
        s.add(row)
        s.commit()
        ref = f"ERR-{row.occurred_at.year}-{row.id:06d}"
    finally:
        s.close()
    app_log.error("unhandled error %s", ref, exc_info=exc,
                  extra={"correlation_id": getattr(request.state, "correlation_id", None)})
    return ref


def register(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        cid = getattr(request.state, "correlation_id", None)
        if exc.rule_id:
            security_log.info(exc.message, extra={"event": "RULE_BLOCK", "rule_id": exc.rule_id,
                                                  "user": get_context().user_name, "correlation_id": cid})
        return JSONResponse(status_code=exc.status_code,
                            content=_body(exc.message, exc.code, None, exc.details, exc.rule_id, cid))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        fields = [{"field": ".".join(str(x) for x in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse(status_code=422, content=_body("Some fields are invalid.", "VALIDATION_FAILED",
                                                           details=fields,
                                                           cid=getattr(request.state, "correlation_id", None)))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code,
                            content=_body(str(exc.detail), "HTTP_ERROR",
                                          cid=getattr(request.state, "correlation_id", None)))

    @app.exception_handler(StaleDataError)
    async def _stale(request: Request, exc: Exception):
        return JSONResponse(status_code=409, content=_body(
            "This record was changed by another user. Reload and try again.", "CONCURRENT_MODIFICATION",
            cid=getattr(request.state, "correlation_id", None)))

    @app.exception_handler(OverflowError)
    @app.exception_handler(DataError)
    async def _bad_value(request: Request, exc: Exception):
        """An identifier/number outside the database range (e.g. /lots/99999999999999999999) is a client error, not a server fault."""
        return JSONResponse(status_code=422, content=_body("A value is outside the permitted range.", "VALIDATION_FAILED", cid=getattr(request.state, "correlation_id", None)))

    @app.exception_handler(IntegrityError)
    async def _integrity(request: Request, exc: IntegrityError):
        ref = _log_error(request, exc)
        return JSONResponse(status_code=409, content=_body(
            "The transaction conflicts with existing data and could not be completed.",
            "DATA_CONFLICT", ref, cid=getattr(request.state, "correlation_id", None)))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        ref = _log_error(request, exc)
        return JSONResponse(status_code=500, content=_body(
            f"Transaction could not be completed. Reference: {ref}", "INTERNAL_ERROR", ref,
            cid=getattr(request.state, "correlation_id", None)))
