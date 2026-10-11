"""GitHub OAuth authentication routes: login initiation, callback handling, session inspection, and logout."""


from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.logging import logger
from app.core.security import (
    create_session_token,
    generate_oauth_state,
    sign_oauth_state,
    verify_oauth_state,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import AuthStatusResponse, UserRead
from app.services.github_oauth import GitHubOAuthError, github_oauth_service

router = APIRouter()


@router.get("/github/login", summary="Initiate GitHub OAuth Flow")
async def github_login() -> RedirectResponse:
    """Generate CSRF state, store signed state in cookie, and redirect user to GitHub OAuth authorization page."""
    raw_state = generate_oauth_state()
    signed_state = sign_oauth_state(raw_state)
    authorization_url = github_oauth_service.build_authorization_url(raw_state)

    response = RedirectResponse(
        url=authorization_url,
        status_code=status.HTTP_302_FOUND,
    )

    # 10 minutes expiry for OAuth state cookie
    response.set_cookie(
        key=settings.OAUTH_STATE_COOKIE_NAME,
        value=signed_state,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        path="/",
    )
    return response


@router.get("/github/callback", summary="GitHub OAuth Callback Handler")
async def github_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
    oauth_state_cookie: str | None = Cookie(None, alias=settings.OAUTH_STATE_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Validate CSRF state, exchange code for GitHub token, fetch user profile, upsert user, and issue session JWT cookie."""
    # Handle user cancellation or GitHub errors
    if error:
        logger.warning(f"GitHub OAuth returned error: {error} - {error_description}")
        target_error_url = f"{settings.FRONTEND_URL}/?error={error}"
        return RedirectResponse(url=target_error_url, status_code=status.HTTP_302_FOUND)

    # Validate state and code presence
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing OAuth authorization code or state parameter.",
        )

    if not oauth_state_cookie or not verify_oauth_state(state, oauth_state_cookie):
        logger.warning("OAuth state verification failed. Possible CSRF attack or expired state cookie.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state parameter.",
        )

    try:
        # 1. Exchange code for access token
        access_token = await github_oauth_service.exchange_code_for_token(code)

        # 2. Fetch GitHub profile and primary email
        profile = await github_oauth_service.fetch_github_user_profile(access_token)

        # 3. Upsert user in database with Fernet-encrypted token
        user = await github_oauth_service.upsert_user(db, profile, access_token)

        # 4. Issue session JWT
        token_payload = {
            "sub": str(user.id),
            "github_id": user.github_id,
            "login": user.login,
        }
        session_jwt = create_session_token(token_payload)

        # 5. Redirect to frontend dashboard with session cookie
        dashboard_url = f"{settings.FRONTEND_URL}/dashboard"
        response = RedirectResponse(url=dashboard_url, status_code=status.HTTP_302_FOUND)

        # Set httpOnly session cookie
        max_age_seconds = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        response.set_cookie(
            key=settings.SESSION_COOKIE_NAME,
            value=session_jwt,
            max_age=max_age_seconds,
            httponly=True,
            samesite="lax",
            secure=settings.is_production,
            path="/",
        )

        # Clear state cookie
        response.delete_cookie(
            key=settings.OAUTH_STATE_COOKIE_NAME,
            path="/",
        )
        return response

    except GitHubOAuthError as exc:
        logger.error(f"GitHub OAuth exchange failure: {exc.message}")
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except Exception as exc:
        logger.error(f"Unexpected error during OAuth callback: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while completing authentication.",
        ) from exc


@router.get("/me", response_model=UserRead, summary="Get Current Authenticated User")
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserRead:
    """Return profile information for the currently authenticated user."""
    return UserRead.model_validate(current_user)


@router.post("/logout", response_model=AuthStatusResponse, summary="Log Out and Clear Session")
async def logout(response: Response) -> AuthStatusResponse:
    """Clear session cookie and invalidate active browser session."""
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
    )
    return AuthStatusResponse(
        authenticated=False,
        message="Session successfully terminated.",
    )


@router.get("/demo-login", summary="One-Click Demo Mode Login (Redirect)")
async def demo_login_redirect() -> RedirectResponse:
    """Issue session cookie for pre-seeded demo user and redirect to frontend."""
    if not settings.DEMO_MODE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demo mode is disabled.",
        )
    from app.db.demo_store import DEMO_USER_ID, get_demo_session

    store = get_demo_session()
    user = store.users_by_id.get(DEMO_USER_ID)
    if not user:
        from app.db.demo_store import seed_demo_data

        seed_demo_data(store)
        user = store.users_by_id[DEMO_USER_ID]

    token_payload = {
        "sub": str(user.id),
        "github_id": user.github_id,
        "login": user.login,
    }
    session_jwt = create_session_token(token_payload)
    max_age_seconds = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    redirect_resp = RedirectResponse(url=f"{settings.FRONTEND_URL}/", status_code=status.HTTP_302_FOUND)
    redirect_resp.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_jwt,
        max_age=max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        path="/",
    )
    return redirect_resp


@router.post("/demo-login", response_model=UserRead, summary="One-Click Demo Mode Login (JSON)")
async def demo_login_json(response: Response) -> UserRead:
    """Issue session cookie for pre-seeded demo user and return user profile."""
    if not settings.DEMO_MODE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demo mode is disabled.",
        )
    from app.db.demo_store import DEMO_USER_ID, get_demo_session

    store = get_demo_session()
    user = store.users_by_id.get(DEMO_USER_ID)
    if not user:
        from app.db.demo_store import seed_demo_data

        seed_demo_data(store)
        user = store.users_by_id[DEMO_USER_ID]

    token_payload = {
        "sub": str(user.id),
        "github_id": user.github_id,
        "login": user.login,
    }
    session_jwt = create_session_token(token_payload)
    max_age_seconds = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_jwt,
        max_age=max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        path="/",
    )
    return UserRead.model_validate(user)
