"""Authentication request and response schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    """User registration payload.

    Attributes:
        email: Unique user email address.
        password: Plaintext password (min 8 chars).
        full_name: Display name.
    """

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    """User login payload.

    Attributes:
        email: Account email.
        password: Account password.
    """

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    """Public user representation.

    Attributes:
        id: User identifier.
        email: User email.
        full_name: Display name.
        created_at: Account creation timestamp.
    """

    id: str
    email: EmailStr
    full_name: str
    created_at: datetime


class AuthTokensResponse(BaseModel):
    """Authentication response containing user and token metadata.

    Attributes:
        user: Authenticated user profile.
        access_token: Short-lived access token.
        token_type: Token type label.
        expires_in: Access token lifetime in seconds.
    """

    user: UserResponse
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    """Optional body for refresh when cookie is unavailable.

    Attributes:
        refresh_token: Refresh token string.
    """

    refresh_token: Optional[str] = None
