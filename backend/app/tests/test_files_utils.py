"""Unit tests for path sanitization helpers."""

import pytest

from app.utils.exceptions import ValidationAppError
from app.utils.files import join_path, normalize_path, sanitize_name


def test_sanitize_name_rejects_traversal() -> None:
    """Reject unsafe names containing separators."""
    with pytest.raises(ValidationAppError):
        sanitize_name("../secret")


def test_normalize_and_join_path() -> None:
    """Normalize and join nested paths safely."""
    assert normalize_path("/src/utils/") == "src/utils"
    assert join_path("src", "main.py") == "src/main.py"
