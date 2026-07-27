"""Authentication API routes."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import get_current_user
from app.api.service_deps import get_auth_service
from app.core.config import get_settings
from app.schemas.auth import (
    AuthTokensResponse,
    LoginRequest,
    RefreshRequest,
    SignupRequest,
    UserResponse,
)
from app.schemas.common import APIResponse
from app.services.auth_service import AuthService
from app.utils.exceptions import UnauthorizedError

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Attach the refresh token as an HTTP-only cookie.

    Args:
        response: Outgoing response.
        refresh_token: Refresh token value.
    """
    settings = get_settings()
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.refresh_token_expire * 60,
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Clear the refresh token cookie.

    Args:
        response: Outgoing response.
    """
    response.delete_cookie(key=REFRESH_COOKIE, path="/api/v1/auth")


@router.post("/signup", response_model=APIResponse[AuthTokensResponse])
async def signup(
    payload: SignupRequest,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
) -> APIResponse[AuthTokensResponse]:
    """Register a new user.

    Args:
        payload: Signup payload.
        response: Response used for cookie attachment.
        auth_service: Auth service dependency.

    Returns:
        Standard API response with auth tokens.
    """
    result, refresh = await auth_service.signup(
        payload.email,
        payload.password,
        payload.full_name,
    )
    _set_refresh_cookie(response, refresh)
    return APIResponse(success=True, message="Signup successful", data=result)


@router.post("/login", response_model=APIResponse[AuthTokensResponse])
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
) -> APIResponse[AuthTokensResponse]:
    """Authenticate an existing user.

    Args:
        payload: Login payload.
        request: Incoming request for IP extraction.
        response: Response used for cookie attachment.
        auth_service: Auth service dependency.

    Returns:
        Standard API response with auth tokens.
    """
    client_ip = request.client.host if request.client else "unknown"
    result, refresh = await auth_service.login(payload.email, payload.password, client_ip)
    _set_refresh_cookie(response, refresh)
    return APIResponse(success=True, message="Login successful", data=result)


@router.post("/refresh", response_model=APIResponse[AuthTokensResponse])
async def refresh(
    request: Request,
    response: Response,
    payload: Optional[RefreshRequest] = None,
    auth_service: AuthService = Depends(get_auth_service),
) -> APIResponse[AuthTokensResponse]:
    """Rotate refresh tokens and issue a new access token.

    Args:
        request: Incoming request with cookie.
        response: Response used for cookie rotation.
        payload: Optional body containing refresh token.
        auth_service: Auth service dependency.

    Returns:
        Standard API response with rotated tokens.
    """
    token = request.cookies.get(REFRESH_COOKIE)
    if not token and payload:
        token = payload.refresh_token
    if not token:
        raise UnauthorizedError("Missing refresh token")
    result, new_refresh = await auth_service.refresh(token)
    _set_refresh_cookie(response, new_refresh)
    return APIResponse(success=True, message="Token refreshed", data=result)


@router.post("/logout", response_model=APIResponse[Dict[str, Any]])
async def logout(
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
) -> APIResponse[Dict[str, Any]]:
    """Log out the current session.

    Args:
        request: Incoming request.
        response: Response used to clear cookies.
        auth_service: Auth service dependency.

    Returns:
        Standard API response confirming logout.
    """
    auth_header = request.headers.get("Authorization", "")
    access = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else None
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    await auth_service.logout(access, refresh_token)
    _clear_refresh_cookie(response)
    return APIResponse(success=True, message="Logged out", data={})


@router.get("/me", response_model=APIResponse[UserResponse])
async def me(
    current_user: Dict[str, Any] = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> APIResponse[UserResponse]:
    """Return the authenticated user profile.

    Args:
        current_user: Authenticated user dependency.
        auth_service: Auth service dependency.

    Returns:
        Standard API response with user profile.
    """
    profile = await auth_service.me(current_user)
    return APIResponse(success=True, message="OK", data=profile)
