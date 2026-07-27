"""JWT access and refresh token helpers."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import JWTError, jwt

from app.core.config import get_settings


def create_access_token(subject: str, extra_claims: Optional[Dict[str, Any]] = None) -> str:
    """Create a signed JWT access token.

    Args:
        subject: User identifier stored in the `sub` claim.
        extra_claims: Optional additional claims.

    Returns:
        Encoded JWT access token string.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": subject,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_refresh_token(subject: str, jti: str) -> str:
    """Create a signed JWT refresh token.

    Args:
        subject: User identifier stored in the `sub` claim.
        jti: Unique token identifier used for rotation tracking.

    Returns:
        Encoded JWT refresh token string.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": "refresh",
        "jti": jti,
        "iat": now,
        "exp": now + timedelta(minutes=settings.refresh_token_expire),
    }
    return jwt.encode(payload, settings.jwt_refresh_secret, algorithm="HS256")


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and validate an access token.

    Args:
        token: Encoded JWT access token.

    Returns:
        Decoded token payload.

    Raises:
        JWTError: If the token is invalid or expired.
    """
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    if payload.get("type") != "access":
        raise JWTError("Invalid token type")
    return payload


def decode_refresh_token(token: str) -> Dict[str, Any]:
    """Decode and validate a refresh token.

    Args:
        token: Encoded JWT refresh token.

    Returns:
        Decoded token payload.

    Raises:
        JWTError: If the token is invalid or expired.
    """
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_refresh_secret, algorithms=["HS256"])
    if payload.get("type") != "refresh":
        raise JWTError("Invalid token type")
    return payload
