"""Authentication: email/password + Google + GitHub OAuth."""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


# ---------- Schemas ----------

def _normalize_email(v: str) -> str:
    v = (v or "").strip().lower()
    if "@" not in v or len(v) < 5:
        raise ValueError("Invalid email address")
    # Allow .local and other non-public TLDs used for local admin accounts
    return v


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return _normalize_email(v)


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return _normalize_email(v)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str | None
    bio: str | None
    current_role: str | None
    location: str | None
    is_superuser: bool = False
    oauth_provider: str | None = None

    class Config:
        from_attributes = True


# ---------- Helpers ----------

def _tokens_for(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id, extra={"is_superuser": user.is_superuser}),
        refresh_token=create_refresh_token(user.id),
    )


async def _get_or_create_oauth_user(
    db: AsyncSession,
    *,
    email: str,
    full_name: str | None,
    provider: str,
    oauth_id: str,
) -> User:
    # Prefer match by oauth provider + id
    result = await db.execute(
        select(User).where(User.oauth_provider == provider, User.oauth_id == oauth_id)
    )
    user = result.scalar_one_or_none()
    if user:
        return user

    # Or by email
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user:
        user.oauth_provider = provider
        user.oauth_id = oauth_id
        if full_name and not user.full_name:
            user.full_name = full_name
        await db.flush()
        return user

    user = User(
        email=email,
        full_name=full_name,
        oauth_provider=provider,
        oauth_id=oauth_id,
        hashed_password=None,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


# ---------- Email / Password ----------

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return _tokens_for(user)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None or not user.hashed_password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    return _tokens_for(user)


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


# ---------- Google OAuth ----------

@router.get("/google/login")
async def google_login():
    if not settings.google_client_id:
        raise HTTPException(400, "Google OAuth is not configured (GOOGLE_CLIENT_ID missing)")
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": f"{settings.backend_public_url}/api/v1/auth/google/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return RedirectResponse(url)


@router.get("/google/callback")
async def google_callback(code: str = Query(...), db: AsyncSession = Depends(get_db)):
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(400, "Google OAuth is not configured")

    token_url = "https://oauth2.googleapis.com/token"
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            token_url,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": f"{settings.backend_public_url}/api/v1/auth/google/callback",
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            raise HTTPException(400, f"Google token exchange failed: {token_resp.text}")
        tokens = token_resp.json()
        access = tokens.get("access_token")
        userinfo = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access}"},
        )
        if userinfo.status_code != 200:
            raise HTTPException(400, "Failed to fetch Google user info")
        info = userinfo.json()

    email = info.get("email")
    if not email:
        raise HTTPException(400, "Google account has no email")
    user = await _get_or_create_oauth_user(
        db,
        email=email,
        full_name=info.get("name"),
        provider="google",
        oauth_id=str(info.get("id")),
    )
    jwt = _tokens_for(user)
    # Redirect to frontend with tokens in hash (simple for SPA)
    redirect = (
        f"{settings.frontend_url}/auth/callback"
        f"#access_token={jwt.access_token}&refresh_token={jwt.refresh_token}"
    )
    return RedirectResponse(redirect)


# ---------- GitHub OAuth ----------

@router.get("/github/login")
async def github_login():
    if not settings.github_client_id:
        raise HTTPException(400, "GitHub OAuth is not configured (GITHUB_CLIENT_ID missing)")
    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": f"{settings.backend_public_url}/api/v1/auth/github/callback",
        "scope": "user:email read:user",
    }
    url = "https://github.com/login/oauth/authorize?" + urlencode(params)
    return RedirectResponse(url)


@router.get("/github/callback")
async def github_callback(code: str = Query(...), db: AsyncSession = Depends(get_db)):
    if not settings.github_client_id or not settings.github_client_secret:
        raise HTTPException(400, "GitHub OAuth is not configured")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": f"{settings.backend_public_url}/api/v1/auth/github/callback",
            },
        )
        if token_resp.status_code != 200:
            raise HTTPException(400, f"GitHub token exchange failed: {token_resp.text}")
        tokens = token_resp.json()
        access = tokens.get("access_token")
        if not access:
            raise HTTPException(400, f"No access_token from GitHub: {tokens}")

        user_resp = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access}", "Accept": "application/json"},
        )
        info = user_resp.json()

        # Email may be private — fetch emails
        email = info.get("email")
        if not email:
            emails_resp = await client.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {access}", "Accept": "application/json"},
            )
            emails = emails_resp.json()
            primary = next((e for e in emails if e.get("primary") and e.get("verified")), None)
            email = primary["email"] if primary else (emails[0]["email"] if emails else None)

    if not email:
        raise HTTPException(400, "Could not get email from GitHub account")

    user = await _get_or_create_oauth_user(
        db,
        email=email,
        full_name=info.get("name") or info.get("login"),
        provider="github",
        oauth_id=str(info.get("id")),
    )
    jwt = _tokens_for(user)
    redirect = (
        f"{settings.frontend_url}/auth/callback"
        f"#access_token={jwt.access_token}&refresh_token={jwt.refresh_token}"
    )
    return RedirectResponse(redirect)


# ---------- Token refresh ----------

class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    from app.core.security import decode_token

    payload = decode_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return _tokens_for(user)
