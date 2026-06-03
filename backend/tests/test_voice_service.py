"""Tests for ``backend.services.voice_service``.

The service POSTs a multipart audio upload to ``stt.nuitruc.ai`` and
extracts ``{"transcript": ...}`` from the JSON response. We cover the
happy path plus every error branch the storytelling/voice_query
handlers depend on to switch to their "thử lại nhé" fallback.

We mock at the ``httpx.AsyncClient.post`` boundary via ``MockTransport``
so the test exercises the real request shape (multipart body, headers)
end-to-end without hitting the network.
"""
from __future__ import annotations

import json

import httpx
import pytest

from backend.services import voice_service
from backend.services.voice_service import (
    VoiceTranscriptionError,
    _mime_for,
    transcribe_vietnamese,
)


@pytest.fixture(autouse=True)
def _reset_client():
    """Force the lazy singleton to rebuild each test so fixtures can
    swap in a MockTransport without leaking client state across tests."""
    voice_service._client = None
    yield
    voice_service._client = None


def _install_transport(monkeypatch, handler):
    """Replace the lazy ``httpx.AsyncClient`` with one routed to ``handler``."""

    def _client_factory():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(voice_service, "_get_client", _client_factory)


@pytest.mark.asyncio
async def test_success_returns_stripped_transcript(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["content_type"] = request.headers.get("content-type", "")
        captured["body_len"] = len(request.content)
        return httpx.Response(
            200,
            json={
                "status": "success",
                "transcript": "  Xin chào hôm qua tôi ăn nhà hàng  ",
                "processing_time_seconds": 0.57,
            },
        )

    _install_transport(monkeypatch, handler)

    out = await transcribe_vietnamese(b"\x00\x01\x02fake-ogg", filename="voice.ogg")
    assert out == "Xin chào hôm qua tôi ăn nhà hàng"
    assert captured["url"].endswith("/api/stt/upload")
    assert captured["content_type"].startswith("multipart/form-data")
    # The audio payload is wrapped in multipart envelope, so body > raw bytes.
    assert captured["body_len"] > len(b"\x00\x01\x02fake-ogg")


@pytest.mark.asyncio
async def test_empty_audio_short_circuits(monkeypatch):
    called = False

    def handler(_request):
        nonlocal called
        called = True
        return httpx.Response(200, json={"transcript": "nope"})

    _install_transport(monkeypatch, handler)

    with pytest.raises(VoiceTranscriptionError, match="empty audio"):
        await transcribe_vietnamese(b"")
    assert called is False, "should never hit the network on empty audio"


@pytest.mark.asyncio
async def test_http_4xx_raises(monkeypatch):
    def handler(_request):
        return httpx.Response(422, json={"detail": "validation"})

    _install_transport(monkeypatch, handler)

    with pytest.raises(VoiceTranscriptionError, match="HTTP 422"):
        await transcribe_vietnamese(b"abc")


@pytest.mark.asyncio
async def test_timeout_raises(monkeypatch):
    def handler(_request):
        raise httpx.TimeoutException("read timeout")

    _install_transport(monkeypatch, handler)

    with pytest.raises(VoiceTranscriptionError, match="timeout"):
        await transcribe_vietnamese(b"abc")


@pytest.mark.asyncio
async def test_transport_error_raises(monkeypatch):
    def handler(_request):
        raise httpx.ConnectError("dns fail")

    _install_transport(monkeypatch, handler)

    with pytest.raises(VoiceTranscriptionError, match="STT provider error"):
        await transcribe_vietnamese(b"abc")


@pytest.mark.asyncio
async def test_non_json_body_raises(monkeypatch):
    def handler(_request):
        return httpx.Response(200, content=b"not json at all")

    _install_transport(monkeypatch, handler)

    with pytest.raises(VoiceTranscriptionError, match="non-JSON"):
        await transcribe_vietnamese(b"abc")


@pytest.mark.asyncio
async def test_empty_transcript_field_raises(monkeypatch):
    def handler(_request):
        return httpx.Response(200, json={"status": "success", "transcript": "   "})

    _install_transport(monkeypatch, handler)

    with pytest.raises(VoiceTranscriptionError, match="empty transcript"):
        await transcribe_vietnamese(b"abc")


@pytest.mark.asyncio
async def test_missing_transcript_field_raises(monkeypatch):
    def handler(_request):
        return httpx.Response(200, json={"status": "success"})

    _install_transport(monkeypatch, handler)

    with pytest.raises(VoiceTranscriptionError, match="empty transcript"):
        await transcribe_vietnamese(b"abc")


@pytest.mark.asyncio
async def test_accepts_text_field_alias(monkeypatch):
    """Some upstream variants use ``text`` instead of ``transcript`` —
    treat both as valid so a server-side rename doesn't break voice."""

    def handler(_request):
        return httpx.Response(200, json={"text": "Tối qua tôi đi ăn"})

    _install_transport(monkeypatch, handler)

    assert await transcribe_vietnamese(b"abc") == "Tối qua tôi đi ăn"


@pytest.mark.asyncio
async def test_bearer_header_when_key_configured(monkeypatch):
    monkeypatch.setattr(voice_service.settings, "stt_api_key", "secret-token")

    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"transcript": "ok"})

    _install_transport(monkeypatch, handler)

    await transcribe_vietnamese(b"abc")
    assert seen["auth"] == "Bearer secret-token"


@pytest.mark.asyncio
async def test_no_auth_header_when_key_empty(monkeypatch):
    monkeypatch.setattr(voice_service.settings, "stt_api_key", "")

    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"transcript": "ok"})

    _install_transport(monkeypatch, handler)

    await transcribe_vietnamese(b"abc")
    assert seen["auth"] == ""


def test_mime_for_known_extensions():
    assert _mime_for("voice.ogg") == "audio/ogg"
    assert _mime_for("voice.opus") == "audio/ogg"
    assert _mime_for("clip.wav") == "audio/wav"
    assert _mime_for("clip.mp3") == "audio/mpeg"
    assert _mime_for("clip.m4a") == "audio/mp4"
    assert _mime_for("clip.webm") == "audio/webm"
    assert _mime_for("blob") == "application/octet-stream"
