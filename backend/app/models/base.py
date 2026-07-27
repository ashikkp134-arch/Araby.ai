"""Domain document helpers for MongoDB collections."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def utc_now() -> datetime:
    """Return the current UTC timestamp.

    Returns:
        Timezone-aware UTC datetime.
    """
    return datetime.now(timezone.utc)


def serialize_doc(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Convert a MongoDB document into an API-friendly dict.

    Args:
        doc: Raw MongoDB document or None.

    Returns:
        Document with `_id` mapped to `id`, or None.
    """
    if doc is None:
        return None
    result = dict(doc)
    if "_id" in result:
        result["id"] = str(result.pop("_id"))
    for key in ("user_id", "project_id", "folder_id", "parent_id", "session_id"):
        if key in result and result[key] is not None:
            result[key] = str(result[key])
    return result
