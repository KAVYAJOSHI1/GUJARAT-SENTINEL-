"""Shared response envelopes, incl. the standardized error format (contract #6)."""
from typing import Any, Optional

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None


class ErrorResponse(BaseModel):
    """docs/API_CONTRACTS.md#6-standardized-http-api-error-response-format"""

    success: bool = False
    error: ErrorDetail


class SuccessResponse(BaseModel):
    success: bool = True
    data: Optional[Any] = None
