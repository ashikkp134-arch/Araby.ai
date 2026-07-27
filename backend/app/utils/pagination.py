"""Pagination helpers."""

from math import ceil
from typing import Tuple

from app.schemas.common import PaginationMeta


def clamp_pagination(page: int, page_size: int) -> Tuple[int, int]:
    """Normalize page and page size values.

    Args:
        page: Requested page number.
        page_size: Requested page size.

    Returns:
        Tuple of (page, page_size).
    """
    safe_page = max(page, 1)
    safe_size = min(max(page_size, 1), 100)
    return safe_page, safe_size


def build_pagination(page: int, page_size: int, total: int) -> PaginationMeta:
    """Build pagination metadata.

    Args:
        page: Current page.
        page_size: Page size.
        total: Total item count.

    Returns:
        PaginationMeta instance.
    """
    total_pages = ceil(total / page_size) if page_size else 0
    return PaginationMeta(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )
