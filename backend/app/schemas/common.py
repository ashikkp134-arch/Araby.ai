"""Shared API response schemas."""

from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """Standard API envelope used by all endpoints.

    Attributes:
        success: Whether the request succeeded.
        message: Human-readable status message.
        data: Response payload.
        error: Error details when success is False.
    """

    success: bool = True
    message: str = ""
    data: Optional[T] = None
    error: Optional[Any] = None


class PaginationMeta(BaseModel):
    """Pagination metadata for list endpoints.

    Attributes:
        page: Current page number (1-indexed).
        page_size: Number of items per page.
        total: Total number of matching items.
        total_pages: Total number of pages.
    """

    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class PaginatedData(BaseModel, Generic[T]):
    """Paginated list payload.

    Attributes:
        items: Page items.
        pagination: Pagination metadata.
    """

    items: List[T]
    pagination: PaginationMeta
