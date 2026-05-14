from __future__ import annotations

import time

import pytest
from fastapi import HTTPException

from backend.config import get_settings
from backend.schemas.admin import AdminUserOut, ChangePasswordRequest
from backend.services import admin_auth
from backend.utils.admin_security import create_admin_token, decode_admin_token, hash_password, verify_password


@pytest.fixture(autouse=True)
def admin_settings(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_JWT_SECRET", "test-secret-with-enough-entropy")
    monkeypatch.setenv("ADMIN_JWT_EXPIRY_MINUTES", "60")
    yield
    get_settings.cache_clear()


def test_admin_user_out_never_exposes_password_hash():
    admin = AdminUserOut(
        id=1,
        email="phuongphh@nuitruc.ai",
        full_name="Phuong",
        role="super_admin",
        tenant_id=None,
        is_active=True,
        force_password_change=True,
        last_login_at=None,
        created_at="2026-05-14T00:00:00Z",
    )

    assert "password_hash" not in admin.model_dump()


def test_password_hash_roundtrip_without_plaintext_storage():
    password_hash = hash_password("StrongerPassword123")

    assert password_hash != "StrongerPassword123"
    assert verify_password("StrongerPassword123", password_hash)
    assert not verify_password("wrong-password", password_hash)


def test_jwt_contains_required_claims_and_rejects_tampering():
    token, jti, expires_in = create_admin_token(
        42,
        "phuongphh@nuitruc.ai",
        "super_admin",
        restricted=True,
    )

    payload = decode_admin_token(token)
    assert payload["admin_id"] == 42
    assert payload["email"] == "phuongphh@nuitruc.ai"
    assert payload["role"] == "super_admin"
    assert payload["restricted"] is True
    assert payload["jti"] == jti
    assert expires_in == 3600

    with pytest.raises(HTTPException) as exc_info:
        decode_admin_token(token[:-1] + ("a" if token[-1] != "a" else "b"))
    assert exc_info.value.status_code == 401


def test_change_password_schema_enforces_strength():
    ChangePasswordRequest(current_password="admin", new_password="StrongPassword123")

    with pytest.raises(ValueError):
        ChangePasswordRequest(current_password="admin", new_password="short1")
    with pytest.raises(ValueError):
        ChangePasswordRequest(current_password="admin", new_password="passwordonly")


def test_rate_limit_falls_back_to_memory_when_redis_unavailable(monkeypatch):
    class BrokenRedis:
        def get(self, key):
            raise OSError("redis unavailable")

        def pipeline(self):
            raise OSError("redis unavailable")

        def exists(self, key):
            raise OSError("redis unavailable")

    monkeypatch.setattr(admin_auth, "_redis", lambda: BrokenRedis())
    admin_auth._memory_attempts.clear()
    ip_address = "203.0.113.10"

    for _ in range(admin_auth.RATE_LIMIT_MAX):
        assert admin_auth.check_login_rate_limit(ip_address)
        admin_auth.record_login_attempt(ip_address)

    assert not admin_auth.check_login_rate_limit(ip_address)


def test_blacklist_falls_back_to_memory_when_redis_unavailable(monkeypatch):
    class BrokenRedis:
        def setex(self, key, ttl, value):
            raise OSError("redis unavailable")

        def exists(self, key):
            raise OSError("redis unavailable")

    monkeypatch.setattr(admin_auth, "_redis", lambda: BrokenRedis())
    admin_auth._memory_blacklist.clear()

    admin_auth.blacklist_token("jti-1", 60)
    assert admin_auth.is_token_blacklisted("jti-1")

    admin_auth._memory_blacklist["jti-1"] = time.time() - 1
    assert not admin_auth.is_token_blacklisted("jti-1")
