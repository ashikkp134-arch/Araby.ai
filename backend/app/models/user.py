"""User document model helpers."""

from typing import Any, Dict

from app.models.base import utc_now


def build_user_document(email: str, password_hash: str, full_name: str) -> Dict[str, Any]:
    """Build a new user document for insertion.

    Args:
        email: Normalized email address.
        password_hash: Bcrypt password hash.
        full_name: Display name.

    Returns:
        MongoDB-ready user document.
    """
    now = utc_now()
    return {
        "email": email.lower().strip(),
        "password_hash": password_hash,
        "full_name": full_name.strip(),
        "created_at": now,
        "updated_at": now,
    }
