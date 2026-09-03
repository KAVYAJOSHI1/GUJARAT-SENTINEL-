"""
Domain exceptions and FastAPI exception handlers producing the
standardized error envelope required by
docs/API_CONTRACTS.md#6-standardized-http-api-error-response-format.
"""
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException


class SentinelException(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400, details=None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class DuplicateWatchlistEntryError(SentinelException):
    def __init__(self, plate: str):
        super().__init__(
            code="DUPLICATE_WATCHLIST_ENTRY",
            message=f"Plate '{plate}' already exists in the watchlist.",
            status_code=status.HTTP_409_CONFLICT,
        )


class NotFoundError(SentinelException):
    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            code="NOT_FOUND",
            message=f"{resource} '{resource_id}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )


def _envelope(code: str, message: str, details=None) -> dict:
    return {"success": False, "error": {"code": code, "message": message, "details": details}}


def register_exception_handlers(app):
    @app.exception_handler(SentinelException)
    async def sentinel_exception_handler(request: Request, exc: SentinelException):
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        detail = exc.detail
        if isinstance(detail, dict):
            code = detail.get("code", "HTTP_ERROR")
            message = detail.get("message", str(detail))
        else:
            code, message = "HTTP_ERROR", str(detail)
        return JSONResponse(status_code=exc.status_code, content=_envelope(code, message))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope("VALIDATION_ERROR", "Request validation failed.", exc.errors()),
        )

    @app.exception_handler(OperationalError)
    async def db_operational_error_handler(request: Request, exc: OperationalError):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("DATABASE_UNAVAILABLE", "Database connection failed."),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("INTERNAL_SERVER_ERROR", "An unexpected error occurred."),
        )
