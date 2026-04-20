"""Tests for Telegram Mini App initData verification (Issue #29)."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from backend.miniapp.auth import verify_init_data

BOT_TOKEN = "1234567:TEST-BOT-TOKEN"


def _sign(fields: dict[str, str], token: str = BOT_TOKEN) -> str:
    """Helper — produce a valid Telegram initData query string."""
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(fields.items(), key=lambda kv: kv[0])
    )
    secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    signed = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    return urlencode({**fields, "hash": signed})


def _base_fields(user_id: int = 12345) -> dict[str, str]:
    return {
        "auth_date": str(int(time.time())),
        "query_id": "ABC",
        "user": json.dumps(
            {
                "id": user_id,
                "first_name": "Phương",
                "username": "phuong",
                "language_code": "vi",
            }
        ),
    }


class TestVerifyInitData:
    def test_valid_signature(self):
        init_data = _sign(_base_fields())
        result = verify_init_data(init_data, bot_token=BOT_TOKEN)
        assert result is not None
        assert result["user_id"] == 12345
        assert result["first_name"] == "Phương"
        assert result["username"] == "phuong"

    def test_invalid_hash(self):
        init_data = _sign(_base_fields())
        # Tamper with hash
        tampered = init_data.rsplit("hash=", 1)[0] + "hash=" + "0" * 64
        assert verify_init_data(tampered, bot_token=BOT_TOKEN) is None

    def test_wrong_bot_token(self):
        init_data = _sign(_base_fields())
        assert verify_init_data(init_data, bot_token="different-token") is None

    def test_missing_hash(self):
        # Query string without a hash field
        fields = _base_fields()
        qs = urlencode(fields)
        assert verify_init_data(qs, bot_token=BOT_TOKEN) is None

    def test_empty_input(self):
        assert verify_init_data("", bot_token=BOT_TOKEN) is None

    def test_missing_bot_token(self):
        init_data = _sign(_base_fields())
        assert verify_init_data(init_data, bot_token="") is None

    def test_expired_auth_date(self):
        fields = _base_fields()
        fields["auth_date"] = str(int(time.time()) - 10 * 24 * 3600)  # 10 days ago
        init_data = _sign(fields)
        assert verify_init_data(init_data, bot_token=BOT_TOKEN) is None

    def test_custom_max_age_allows_old_tokens(self):
        fields = _base_fields()
        fields["auth_date"] = str(int(time.time()) - 10 * 24 * 3600)
        init_data = _sign(fields)
        result = verify_init_data(
            init_data, bot_token=BOT_TOKEN, max_age_seconds=100 * 24 * 3600
        )
        assert result is not None
        assert result["user_id"] == 12345

    def test_tampered_user_field(self):
        fields = _base_fields()
        init_data = _sign(fields)
        # Swap user payload to another user after signing — hash should fail
        parts = init_data.split("&")
        new_parts = []
        for p in parts:
            if p.startswith("user="):
                new_parts.append(
                    "user="
                    + urlencode({"user": json.dumps({"id": 99999})})[5:]
                )
            else:
                new_parts.append(p)
        tampered = "&".join(new_parts)
        assert verify_init_data(tampered, bot_token=BOT_TOKEN) is None

    def test_no_user_field(self):
        """Valid hash but no user payload → returns dict but user_id is None."""
        fields = {"auth_date": str(int(time.time())), "query_id": "X"}
        init_data = _sign(fields)
        result = verify_init_data(init_data, bot_token=BOT_TOKEN)
        assert result is not None
        assert result["user_id"] is None

    def test_invalid_auth_date(self):
        fields = _base_fields()
        fields["auth_date"] = "not-a-number"
        init_data = _sign(fields)
        assert verify_init_data(init_data, bot_token=BOT_TOKEN) is None
