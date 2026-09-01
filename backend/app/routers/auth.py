"""Sign in, refresh, sign out, and "who am I".

Refresh tokens are stored HASHED and are single-use: refreshing rotates the
token and revokes the one presented. That way a stolen refresh token is only
good until the legitimate client next refreshes — at which point one of the two
presents an already-revoked token and the whole family can be cut off.
"""

from __future__ import annotations

import hashlib
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .. import db, throttle
from ..config import settings
from ..deps import Principal, client_ip, current_user
from ..domain import PERMISSIONS, ROLES, can, iso, log
from ..schemas import LoginIn, PasswordIn, RefreshIn
from ..security import (
    TokenError,
    create_token,
    decode_token,
    hash_password,
    new_id,
    verify_password,
)
from ..serial import user as ser_user

router = APIRouter(prefix="/auth", tags=["auth"])


def _hash_refresh(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _issue(user_row) -> dict:
    access = create_token(user_row["id"], kind="access", role=user_row["role"], email=user_row["email"])
    refresh = create_token(
        user_row["id"], kind="refresh", ttl_seconds=settings.refresh_ttl_days * 86400
    )
    db.insert(
        "refresh_tokens",
        {
            "id": new_id("rt"),
            "user_id": user_row["id"],
            "token_hash": _hash_refresh(refresh),
            "expires_at": iso(),
            "revoked": 0,
            "created_at": iso(),
        },
    )
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": settings.access_ttl_min * 60,
        "user": ser_user(user_row),
    }


@router.post("/login")
def login(payload: LoginIn, request: Request) -> dict:
    ip = client_ip(request)

    # Checked BEFORE the password is verified: a locked-out attacker should not
    # get to spend our CPU on an scrypt hash with every guess.
    try:
        throttle.check(payload.email, ip)
    except throttle.TooManyAttempts as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc

    row = db.one("SELECT * FROM users WHERE lower(email) = lower(?)", (payload.email,))

    # Always run a verification, even when the account does not exist, so the
    # response time does not leak which addresses are registered.
    stored = row["password_hash"] if row and row["password_hash"] else hash_password("__no_such_user__")
    ok = verify_password(payload.password, stored)

    if not row or not ok or row["status"] != "active":
        throttle.failed(payload.email, ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    throttle.succeeded(payload.email, ip)
    db.update("users", row["id"], {"last_active_at": iso()})
    log(
        kind="human",
        actor=row["id"],
        action_en="signed in",
        action_fa="وارد شد",
        target="auth",
        tone="info",
        ip=ip,
    )
    return _issue(row)


@router.post("/refresh")
def refresh(payload: RefreshIn) -> dict:
    try:
        claims = decode_token(payload.refresh_token, expect="refresh")
    except TokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    token_hash = _hash_refresh(payload.refresh_token)
    stored = db.one("SELECT * FROM refresh_tokens WHERE token_hash = ?", (token_hash,))
    if stored is None or stored["revoked"]:
        # A revoked token being replayed means the family is compromised —
        # cut all of that user's sessions, not just this one.
        if stored is not None:
            db.execute("UPDATE refresh_tokens SET revoked = 1 WHERE user_id = ?", (stored["user_id"],))
        raise HTTPException(status_code=401, detail="Refresh token is no longer valid")

    row = db.one("SELECT * FROM users WHERE id = ?", (claims["sub"],))
    if row is None or row["status"] != "active":
        raise HTTPException(status_code=401, detail="User no longer active")

    db.update("refresh_tokens", stored["id"], {"revoked": 1})  # single use
    return _issue(row)


@router.post("/logout", status_code=204)
def logout(principal: Principal = Depends(current_user)) -> None:
    db.execute("UPDATE refresh_tokens SET revoked = 1 WHERE user_id = ?", (principal.id,))


@router.get("/me")
def me(principal: Principal = Depends(current_user)) -> dict:
    row = db.one("SELECT * FROM users WHERE id = ?", (principal.id,))
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    out = ser_user(row)
    out["permissions"] = sorted(p for p in PERMISSIONS if can(row["role"], p))
    return out


@router.post("/password", status_code=204)
def change_password(payload: PasswordIn, principal: Principal = Depends(current_user)) -> None:
    row = db.one("SELECT * FROM users WHERE id = ?", (principal.id,))
    if row is None or not verify_password(payload.current_password, row["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    db.update("users", principal.id, {"password_hash": hash_password(payload.new_password)})
    # changing a password ends every other session
    db.execute("UPDATE refresh_tokens SET revoked = 1 WHERE user_id = ?", (principal.id,))
    log(kind="human", actor=principal.id, action_en="changed their password",
        action_fa="رمز عبور خود را عوض کرد", target="auth", tone="info")


@router.get("/permissions", tags=["meta"])
def permissions() -> dict:
    """The role matrix the Team page prints, served from the same source the
    API enforces — so the UI can never advertise a permission that does not
    actually exist."""
    return {"roles": list(ROLES), "permissions": {k: list(v) for k, v in PERMISSIONS.items()}}
