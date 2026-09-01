"""Request-scoped dependencies: who is calling, and may they do this.

Two credentials are accepted and they are NOT interchangeable:

* a Bearer JWT — a signed-in human. Carries a role, and role gates everything.
* an API key (`X-API-Key`) — a machine. Carries scopes, never a role, and is
  refused on anything that only makes sense for a person (inviting a teammate,
  changing the plan). A key that could do everything a human owner can is a
  key that turns one leaked secret into a total compromise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import Depends, Header, HTTPException, Request, status

from . import db
from .domain import can, iso
from .security import TokenError, decode_token, hash_api_key


@dataclass(frozen=True)
class Principal:
    """Whoever is making this request."""

    id: str
    kind: str  # "user" | "key"
    role: str = "viewer"
    email: str = ""
    scopes: tuple[str, ...] = ()

    @property
    def is_user(self) -> bool:
        return self.kind == "user"

    def label(self) -> str:
        return self.id


def _unauthorised(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def current_principal(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> Principal:
    # ---- API key ----
    if x_api_key:
        row = db.one("SELECT * FROM api_keys WHERE token_hash = ?", (hash_api_key(x_api_key),))
        if row is None:
            raise _unauthorised("Invalid API key")
        db.update("api_keys", row["id"], {"last_used_at": iso()})
        return Principal(
            id=row["id"],
            kind="key",
            email=f"{row['prefix']}…",
            scopes=tuple(db.loads(row["scopes"])),
        )

    # ---- bearer token ----
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorised()
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token, expect="access")
    except TokenError as exc:
        raise _unauthorised(str(exc)) from exc

    user = db.one("SELECT * FROM users WHERE id = ?", (payload["sub"],))
    if user is None or user["status"] == "disabled":
        raise _unauthorised("User no longer active")

    request.state.user_id = user["id"]
    return Principal(id=user["id"], kind="user", role=user["role"], email=user["email"])


async def current_user(principal: Principal = Depends(current_principal)) -> Principal:
    """Endpoints that only make sense for a signed-in person."""
    if not principal.is_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint requires a signed-in user, not an API key",
        )
    return principal


# Permissions are `area.action`; scopes are `area:read` / `area:write` /
# `area:rw` / `*`. These are the actions that only need read access — anything
# not listed is treated as a write, which is the safe default: a new permission
# added later cannot accidentally be satisfied by a read-only key.
_READ_ACTIONS = frozenset({"view", "read", "list"})


def scope_allows(scopes: tuple[str, ...], permission: str) -> bool:
    if "*" in scopes or permission in scopes:
        return True
    area, _, action = permission.partition(".")
    writes = {f"{area}:write", f"{area}:rw", f"{area}:*"}
    if writes & set(scopes):
        return True
    if action in _READ_ACTIONS:
        return bool({f"{area}:read"} & set(scopes))
    return False


def requires(permission: str) -> Callable[..., Any]:
    """Role gate. Use as `Depends(requires("campaigns.write"))`.

    A permission that is not in the matrix fails HERE, at import time, rather
    than at request time. `can()` returns False for an unknown name, so a typo
    used to produce an endpoint that refused every caller including the owner —
    a 403 that looks like a deliberate rule and is really a spelling mistake.
    Two of those shipped before this check existed.
    """
    from .domain import PERMISSIONS

    if permission not in PERMISSIONS:
        raise KeyError(
            f"{permission!r} is not a permission. Known: {', '.join(sorted(PERMISSIONS))}"
        )

    async def guard(principal: Principal = Depends(current_principal)) -> Principal:
        if principal.kind == "key":
            # a key carries scopes, never a role
            if scope_allows(principal.scopes, permission):
                return principal
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key is missing a scope for {permission}",
            )

        if not can(principal.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{principal.role}' cannot {permission}",
            )
        return principal

    return guard


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


def module_enabled(module: str) -> Callable[..., Any]:
    """Refuse a section this deployment was not sold.

    Hiding a module in the navigation is a presentation choice; this is the
    enforcement. Without it, a customer who was not given billing could still
    read /api/billing by typing it, which would make the whole white-label
    story cosmetic.
    """

    async def guard(principal: Principal = Depends(current_principal)) -> Principal:
        from .deployment import enabled

        if not enabled(module):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"The {module} section is not part of this deployment",
            )
        return principal

    return guard
