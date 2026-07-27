"""ObjectId parsing helpers."""

from bson import ObjectId
from bson.errors import InvalidId

from app.utils.exceptions import ValidationAppError


def parse_object_id(value: str, field_name: str = "id") -> ObjectId:
    """Parse a string into a MongoDB ObjectId.

    Args:
        value: Candidate ObjectId string.
        field_name: Field name used in error messages.

    Returns:
        Parsed ObjectId.

    Raises:
        ValidationAppError: If the value is not a valid ObjectId.
    """
    try:
        return ObjectId(value)
    except (InvalidId, TypeError) as exc:
        raise ValidationAppError(f"Invalid {field_name}") from exc
