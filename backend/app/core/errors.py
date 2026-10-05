"""Application errors. Users never see raw Python/DB errors (spec 62)."""
from typing import Any


class AppError(Exception):
    status_code = 400
    code = "APP_ERROR"

    def __init__(self, message: str, *, code: str | None = None, details: Any = None,
                 rule_id: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details
        self.rule_id = rule_id


class AuthenticationError(AppError):
    status_code = 401
    code = "AUTHENTICATION_FAILED"


class PermissionDenied(AppError):
    status_code = 403
    code = "PERMISSION_DENIED"


class NotFound(AppError):
    status_code = 404
    code = "NOT_FOUND"


class Conflict(AppError):
    status_code = 409
    code = "CONFLICT"


class ValidationFailed(AppError):
    status_code = 422
    code = "VALIDATION_FAILED"


class ReasonRequired(ValidationFailed):
    code = "REASON_REQUIRED"


class BusinessRuleError(AppError):
    """A GMP business rule blocked the transaction (carries rule id)."""

    status_code = 409
    code = "BUSINESS_RULE_VIOLATION"


class SegregationOfDutiesError(BusinessRuleError):
    code = "SEGREGATION_OF_DUTIES"


class IllegalTransition(BusinessRuleError):
    code = "ILLEGAL_STATUS_TRANSITION"


class ImmutableRecordError(BusinessRuleError):
    code = "IMMUTABLE_RECORD"
