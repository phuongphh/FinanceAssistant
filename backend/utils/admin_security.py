from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status

from backend.config import get_settings

ALGORITHM = "HS256"
DEFAULT_ADMIN_JWT_EXPIRY_MINUTES = 60
_PBKDF2_PREFIX = "pbkdf2_sha256"
_PBKDF2_ITERATIONS = 390_000


def hash_password(password: str) -> str:
    """Hash admin passwords with bcrypt cost 12 when the dependency is installed.

    CI/dev sandboxes may not have the native bcrypt wheel available; in that
    case we fall back to a self-describing PBKDF2 hash so tests and local seed
    scripts remain runnable. Production requirements include bcrypt and will
    produce standard bcrypt hashes.
    """
    try:
        import bcrypt

        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
    except ImportError:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
        return "$".join(
            [
                _PBKDF2_PREFIX,
                str(_PBKDF2_ITERATIONS),
                _b64url_encode(salt),
                _b64url_encode(digest),
            ]
        )


def verify_password(password: str, password_hash: str) -> bool:
    if password_hash.startswith(f"{_PBKDF2_PREFIX}$"):
        _, iterations, salt_b64, digest_b64 = password_hash.split("$", 3)
        expected = _b64url_decode(digest_b64)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            _b64url_decode(salt_b64),
            int(iterations),
        )
        return hmac.compare_digest(expected, actual)

    try:
        import bcrypt
    except ImportError as exc:
        raise RuntimeError("bcrypt is required to verify bcrypt admin password hashes") from exc
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _jwt_secret() -> str:
    settings = get_settings()
    secret = settings.admin_jwt_secret or settings.internal_api_key
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ADMIN_JWT_SECRET is not configured",
        )
    return secret


def create_admin_token(admin_id: int, email: str, role: str, restricted: bool = False) -> tuple[str, str, int]:
    settings = get_settings()
    expires_in = settings.admin_jwt_expiry_minutes * 60
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=expires_in)
    jti = secrets.token_urlsafe(24)
    payload = {
        "admin_id": admin_id,
        "email": email,
        "role": role,
        "restricted": restricted,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    header = {"typ": "JWT", "alg": ALGORITHM}
    signing_input = ".".join(
        [
            _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        ]
    )
    signature = hmac.new(_jwt_secret().encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url_encode(signature)}", jti, expires_in


def decode_admin_token(token: str) -> dict[str, Any]:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".", 2)
        signing_input = f"{header_b64}.{payload_b64}"
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
        if header.get("alg") != ALGORITHM:
            raise ValueError("Unexpected JWT algorithm")
        expected = hmac.new(_jwt_secret().encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
        actual = _b64url_decode(signature_b64)
        if _b64url_encode(actual) != signature_b64:
            raise ValueError("Non-canonical JWT signature")
        if not hmac.compare_digest(expected, actual):
            raise ValueError("Invalid JWT signature")
        if int(payload.get("exp", 0)) <= int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("JWT expired")
        if not payload.get("jti") or not payload.get("admin_id"):
            raise ValueError("Missing required JWT claims")
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
