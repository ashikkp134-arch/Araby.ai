"""Tests for workspace file-type edit policy."""

import pytest

from app.utils.exceptions import ValidationAppError
from app.utils.workspace_file_policy import (
    JAVASCRIPT_EDIT_MESSAGE,
    PYTHON_EDIT_MESSAGE,
    assert_path_editable,
    edit_restriction_message,
    is_path_editable,
)


def test_python_allows_py_only() -> None:
    assert is_path_editable("python", "app/main.py") is True
    assert is_path_editable("python", "README.md") is False
    assert is_path_editable("python", "src/app.js") is False


def test_javascript_allows_js_family() -> None:
    assert is_path_editable("javascript", "src/app.js") is True
    assert is_path_editable("javascript", "src/App.tsx") is True
    assert is_path_editable("javascript", "src/util.ts") is True
    assert is_path_editable("javascript", "src/Widget.jsx") is True
    assert is_path_editable("javascript", "README.md") is False
    assert is_path_editable("javascript", "main.py") is False


def test_website_unrestricted() -> None:
    assert is_path_editable("website", "index.html") is True
    assert is_path_editable("website", "styles.css") is True
    assert is_path_editable("website", "src/App.tsx") is True
    assert is_path_editable("website", "notes.md") is True


def test_messages() -> None:
    assert edit_restriction_message("python") == PYTHON_EDIT_MESSAGE
    assert edit_restriction_message("javascript") == JAVASCRIPT_EDIT_MESSAGE


def test_assert_raises() -> None:
    with pytest.raises(ValidationAppError) as exc:
        assert_path_editable("python", "README.md")
    assert exc.value.message == PYTHON_EDIT_MESSAGE
