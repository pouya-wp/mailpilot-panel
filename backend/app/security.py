"""Passwords, tokens and API keys — all on the standard library.

No passlib, no python-jose. Both would be extra dependencies for algorithms
that ship with CPython, and passlib in particular is unmaintained and breaks
against modern bcrypt on 3.13. What is here is small enough to audit in one
sitting:

* passwords use `hashlib.scrypt`, which is memory-hard and in the stdlib. Each
  hash carries its own salt and parameters, so the cost can be raised later
  without invalidating existing hashes.
* tokens are HS256 JWTs, signed and verified with `hmac.compare_digest`. The
  signature is checked BEFORE the payload is parsed, and `exp` is enforced.
* API keys are stored only as a hash. The plaintext is returned exactly once,
  at creation, and cannot be recovered afterwards.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from typing import Any

from .config import settings

# scrypt parameters. n=2**14 keeps a single hash around 50-80 ms on a laptop —
# slow enough to make offline guessing expensive, fast enough for a login.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_LEN = 32


# ---------------------------------------------------------------- passwords


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_SCRYPT_LEN
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time, and never raises on a malformed hash."""
    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(bytes.fromhex(digest_hex)),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk.hex(), digest_hex)


# ---------------------------------------------------------------- jwt


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _sign(message: bytes) -> bytes:
    return hmac.new(settings.secret_key.encode("utf-8"), message, hashlib.sha256).digest()


class TokenError(Exception):
    """Raised for anything wrong with a token — never says which thing."""


def create_token(subject: str, *, kind: str = "access", ttl_seconds: int | None = None, **claims: Any) -> str:
    now = int(time.time())
    if ttl_seconds is None:
        ttl_seconds = settings.access_ttl_min * 60
    payload: dict[str, Any] = {
        "sub": subject,
        "typ": kind,
        "iat": now,
        "exp": now + ttl_seconds,
        "jti": uuid.uuid4().hex,
        **claims,
    }
    header = _b64e(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64e(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode())
    signing_input = f"{header}.{body}".encode("ascii")
    return f"{header}.{body}.{_b64e(_sign(signing_input))}"


def decode_token(token: str, *, expect: str | None = None) -> dict[str, Any]:
    try:
        header_b64, body_b64, sig_b64 = token.split(".")
    except ValueError as exc:
        raise TokenError("malformed token") from exc

    # Verify FIRST. Parsing an unverified payload is how `alg: none` and
    # friends get in.
    expected = _sign(f"{header_b64}.{body_b64}".encode("ascii"))
    try:
        given = _b64d(sig_b64)
    except Exception as exc:  # noqa: BLE001 - any decode failure is the same answer
        raise TokenError("bad signature") from exc
    if not hmac.compare_digest(expected, given):
        raise TokenError("bad signature")

    try:
        payload = json.loads(_b64d(body_b64))
    except Exception as exc:  # noqa: BLE001
        raise TokenError("malformed payload") from exc

    if not isinstance(payload, dict):
        raise TokenError("malformed payload")
    if int(payload.get("exp", 0)) < int(time.time()):
        raise TokenError("expired")
    if expect and payload.get("typ") != expect:
        raise TokenError("wrong token type")
    return payload


# ---------------------------------------------------------------- api keys


def new_api_key(live: bool = True) -> tuple[str, str, str]:
    """Returns (plaintext, prefix, hash). The plaintext is never stored."""
    body = secrets.token_urlsafe(30)
    plaintext = f"mp_{'live' if live else 'test'}_{body}"
    prefix = plaintext[:16]
    return plaintext, prefix, hash_api_key(plaintext)


def hash_api_key(plaintext: str) -> str:
    """A fast hash is correct here: an API key is 240 bits of entropy, so it
    is not guessable, and this runs on every API request."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def sign_blob(payload: str) -> str:
    """A short HMAC over an arbitrary string.

    Used for things that leave the server and come back expected to be
    unchanged — a pending agent action shown to an operator, then posted back
    when they approve it. Not a token: it carries no identity and no expiry,
    it only answers "is this the same bytes I sent?".
    """
    return _b64e(_sign(payload.encode("utf-8")))[:32]


def blob_matches(payload: str, signature: str) -> bool:
    return hmac.compare_digest(sign_blob(payload), signature or "")
