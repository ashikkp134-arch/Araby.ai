"""Application-specific exception hierarchy."""

from typing import Any, Optional


class AppException(Exception):
    """Base application exception.

    Attributes:
        message: Human-readable error message.
        status_code: HTTP status code.
        error_code: Machine-readable error code.
        details: Optional extra error details.
    """

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        error_code: str = "app_error",
        details: Optional[Any] = None,
    ) -> None:
        """Initialize the exception.

        Args:
            message: Human-readable error message.
            status_code: HTTP status code.
            error_code: Machine-readable error code.
            details: Optional extra error details.
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details


class NotFoundError(AppException):
    """Raised when a requested resource does not exist."""

    def __init__(self, message: str = "Resource not found") -> None:
        """Initialize not-found error.

        Args:
            message: Error message.
        """
        super().__init__(message=message, status_code=404, error_code="not_found")


class UnauthorizedError(AppException):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Unauthorized") -> None:
        """Initialize unauthorized error.

        Args:
            message: Error message.
        """
        super().__init__(message=message, status_code=401, error_code="unauthorized")


class ForbiddenError(AppException):
    """Raised when the user lacks permission."""

    def __init__(self, message: str = "Forbidden") -> None:
        """Initialize forbidden error.

        Args:
            message: Error message.
        """
        super().__init__(message=message, status_code=403, error_code="forbidden")


class ConflictError(AppException):
    """Raised when a resource conflict occurs."""

    def __init__(self, message: str = "Conflict") -> None:
        """Initialize conflict error.

        Args:
            message: Error message.
        """
        super().__init__(message=message, status_code=409, error_code="conflict")


class RateLimitError(AppException):
    """Raised when a rate limit is exceeded."""

    def __init__(self, message: str = "Too many requests") -> None:
        """Initialize rate-limit error.

        Args:
            message: Error message.
        """
        super().__init__(message=message, status_code=429, error_code="rate_limited")


class ValidationAppError(AppException):
    """Raised for domain validation failures."""

    def __init__(self, message: str = "Validation failed", details: Optional[Any] = None) -> None:
        """Initialize validation error.

        Args:
            message: Error message.
            details: Optional validation details.
        """
        super().__init__(
            message=message,
            status_code=422,
            error_code="validation_error",
            details=details,
        )
