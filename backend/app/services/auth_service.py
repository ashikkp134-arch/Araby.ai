"""Authentication service implementing signup, login, refresh, and logout."""

import logging
from datetime import timedelta
from typing import Any, Dict, Optional, Tuple

from app.core.config import get_settings
from app.core.jwt import create_access_token, create_refresh_token, decode_refresh_token
from app.core.redis import RedisCache
from app.core.security import generate_token_id, hash_password, hash_token, verify_password
from app.models.base import utc_now
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import AuthTokensResponse, UserResponse
from app.utils.exceptions import ConflictError, RateLimitError, UnauthorizedError
from app.utils.object_id import parse_object_id
from jose import JWTError

logger = logging.getLogger(__name__)


class AuthService:
    """Business logic for authentication and session management."""

    def __init__(
        self,
        user_repo: UserRepository,
        refresh_repo: RefreshTokenRepository,
        cache: RedisCache,
    ) -> None:
        """Initialize the auth service.

        Args:
            user_repo: User repository.
            refresh_repo: Refresh token repository.
            cache: Redis cache helper.
        """
        self._users = user_repo
        self._refresh = refresh_repo
        self._cache = cache
        self._settings = get_settings()

    async def signup(
        self,
        email: str,
        password: str,
        full_name: str,
    ) -> Tuple[AuthTokensResponse, str]:
        """Register a new user and issue tokens.

        Args:
            email: User email.
            password: Plaintext password.
            full_name: Display name.

        Returns:
            Tuple of auth response and refresh token string.

        Raises:
            ConflictError: If email already exists.
        """
        existing = await self._users.find_by_email(email)
        if existing:
            raise ConflictError("Email already registered")
        user = await self._users.create(email, hash_password(password), full_name)
        access, refresh = await self._issue_tokens(user["id"])
        logger.info("User signed up: %s", user["email"])
        return self._build_auth_response(user, access, refresh), refresh

    async def login(self, email: str, password: str, client_ip: str) -> Tuple[AuthTokensResponse, str]:
        """Authenticate a user and issue tokens.

        Args:
            email: User email.
            password: Plaintext password.
            client_ip: Client IP used for rate limiting.

        Returns:
            Tuple of auth response and refresh token string.

        Raises:
            RateLimitError: If login attempts exceed the limit.
            UnauthorizedError: If credentials are invalid.
        """
        await self._enforce_login_rate_limit(client_ip, email)
        user_doc = await self._users.find_by_email(email)
        if not user_doc or not verify_password(password, user_doc["password_hash"]):
            raise UnauthorizedError("Invalid email or password")
        user = {
            "id": str(user_doc["_id"]),
            "email": user_doc["email"],
            "full_name": user_doc["full_name"],
            "created_at": user_doc["created_at"],
        }
        access, refresh = await self._issue_tokens(user["id"])
        logger.info("User logged in: %s", user["email"])
        response = self._build_auth_response(user, access, refresh)
        return response, refresh

    async def refresh(self, refresh_token: str) -> Tuple[AuthTokensResponse, str]:
        """Rotate a refresh token and issue a new token pair.

        Args:
            refresh_token: Current refresh token.

        Returns:
            Tuple of auth response and new refresh token.

        Raises:
            UnauthorizedError: If refresh token is invalid.
        """
        try:
            payload = decode_refresh_token(refresh_token)
        except JWTError as exc:
            raise UnauthorizedError("Invalid refresh token") from exc
        token_hash = hash_token(refresh_token)
        stored = await self._refresh.find_valid(token_hash)
        if not stored:
            raise UnauthorizedError("Refresh token revoked or expired")
        if stored.get("jti") != payload.get("jti"):
            raise UnauthorizedError("Refresh token mismatch")
        await self._refresh.revoke(token_hash)
        user_id = payload["sub"]
        user_doc = await self._users.find_by_id(parse_object_id(user_id, "user_id"))
        if not user_doc:
            raise UnauthorizedError("User not found")
        user = {
            "id": str(user_doc["_id"]),
            "email": user_doc["email"],
            "full_name": user_doc["full_name"],
            "created_at": user_doc["created_at"],
        }
        access, new_refresh = await self._issue_tokens(user["id"])
        return self._build_auth_response(user, access, new_refresh), new_refresh

    async def logout(self, access_token: Optional[str], refresh_token: Optional[str]) -> None:
        """Revoke access and refresh tokens.

        Args:
            access_token: Optional access token to blacklist.
            refresh_token: Optional refresh token to revoke.
        """
        if access_token:
            ttl = self._settings.access_token_expire * 60
            await self._cache.set(f"jwt:blacklist:{access_token}", "1", ttl)
        if refresh_token:
            await self._refresh.revoke(hash_token(refresh_token))

    async def me(self, user: Dict[str, Any]) -> UserResponse:
        """Return the current authenticated user profile.

        Args:
            user: Authenticated user dict.

        Returns:
            UserResponse schema instance.
        """
        return UserResponse(**user)

    async def _issue_tokens(self, user_id: str) -> Tuple[str, str]:
        """Create and persist an access/refresh token pair.

        Args:
            user_id: Authenticated user id.

        Returns:
            Tuple of access token and refresh token.
        """
        jti = generate_token_id()
        access = create_access_token(user_id)
        refresh = create_refresh_token(user_id, jti)
        expires_at = utc_now() + timedelta(minutes=self._settings.refresh_token_expire)
        await self._refresh.create(
            user_id=parse_object_id(user_id, "user_id"),
            token_hash=hash_token(refresh),
            jti=jti,
            expires_at=expires_at,
        )
        await self._cache.set(
            f"refresh:{jti}",
            user_id,
            self._settings.refresh_token_expire * 60,
        )
        return access, refresh

    async def _enforce_login_rate_limit(self, client_ip: str, email: str) -> None:
        """Apply login rate limiting per IP and email.

        Args:
            client_ip: Client IP address.
            email: Attempted email.

        Raises:
            RateLimitError: When attempts exceed the configured limit.
        """
        key = f"rate:login:{client_ip}:{email.lower()}"
        count = await self._cache.incr(key)
        if count == 1:
            await self._cache.expire(key, 900)
        if count > self._settings.rate_limit_login:
            raise RateLimitError("Too many login attempts. Try again later.")

    def _build_auth_response(
        self,
        user: Dict[str, Any],
        access_token: str,
        refresh_token: str,
    ) -> AuthTokensResponse:
        """Build an AuthTokensResponse envelope.

        Args:
            user: Serialized user.
            access_token: Access token string.
            refresh_token: Refresh token string (not returned in body).

        Returns:
            AuthTokensResponse instance.
        """
        _ = refresh_token
        return AuthTokensResponse(
            user=UserResponse(**user),
            access_token=access_token,
            token_type="bearer",
            expires_in=self._settings.access_token_expire * 60,
        )
