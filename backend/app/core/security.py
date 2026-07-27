"""Password hashing and security utilities."""

import hashlib
import secrets

import bcrypt


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt.

    Args:
        password: Plaintext password.

    Returns:
        Bcrypt hashed password string.
    """
    digest = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return digest.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    Args:
        plain_password: Candidate plaintext password.
        hashed_password: Stored bcrypt hash.

    Returns:
        True when the password matches.
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def generate_token_id() -> str:
    """Generate a cryptographically secure token identifier.

    Returns:
        URL-safe random token id.
    """
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Create a SHA-256 hash of a token for safe storage.

    Args:
        token: Raw token string.

    Returns:
        Hex-encoded SHA-256 digest.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
