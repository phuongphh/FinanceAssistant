"""Phase 5.1 #2.4 — a Twin chart reaching Zalo as a URL.

The break this closes: Telegram hands notifiers raw ``bytes``, Zalo's
``/message/cs`` takes an ``image_url``, and before #2.4 the Zalo adapter
had nowhere to put the bytes. #1.2 built the publish half; this file
tests the join.

Two properties get more attention than the happy path, because both fail
silently in production if they regress:

* **Publish, commit, then send.** ``media_url_service`` only flushes.
  If the row is still uncommitted when Zalo fetches the URL — which it
  does within seconds — the resolver sees nothing and the user gets a
  broken image with no error anywhere. The commit is asserted to have
  happened *before* the OA call, not merely to have happened.
* **Every failure degrades to text.** Flag off, no public base URL, an
  unlinked sender, a storage error: each one has to come out as a
  caption-only text message. A briefing that dies because its chart
  couldn't upload is a worse outcome than a chartless briefing.
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from types import SimpleNamespace

import pytest
from tests.test_phase_5_1.conftest import FakeMediaSession

from backend.adapters import media_storage as media_storage_module
from backend.adapters.zalo_notifier import ZaloNotifier, _content_type_for
from backend.services import zalo_linking_service

SENDER = "zalo-sender-should-never-be-logged"
BASE_URL = "https://betien.test"
PNG = b"\x89PNG\r\n\x1a\n" + b"chart" * 40
NOTIFIER_LOGGER = "backend.adapters.zalo_notifier"


class FakeOAClient:
    """Records what reached the OA, and *when* the image call happened.

    ``commits_at_send`` is the whole point of the class: it snapshots the
    session's commit count at the moment ``send_image_message`` is
    entered, which is the only way to assert ordering rather than mere
    occurrence.
    """

    is_configured = True
    is_send_enabled = True

    def __init__(self, db: FakeMediaSession | None = None) -> None:
        self._db = db
        self.sent: list[tuple[str, str]] = []
        self.images: list[tuple[str, str, str]] = []
        self.commits_at_send: list[int] = []
        self.ok = True

    async def send_message(self, recipient_id: str, text: str) -> bool:
        self.sent.append((recipient_id, text))
        return self.ok

    async def send_message_with_buttons(
        self, recipient_id: str, text: str, buttons: list
    ) -> bool:
        self.sent.append((recipient_id, text))
        return self.ok

    async def send_image_message(
        self, recipient_id: str, image_url: str, caption: str = ""
    ) -> bool:
        if self._db is not None:
            self.commits_at_send.append(self._db.commits)
        self.images.append((recipient_id, image_url, caption))
        return self.ok


def settings_for(tmp_path, *, enabled=True, base_url=BASE_URL, ttl=900):
    return SimpleNamespace(
        media_url_enabled=enabled,
        media_public_base_url=base_url,
        media_storage_path=str(tmp_path / "media"),
        media_url_ttl_seconds=ttl,
    )


def session_factory_for(db):
    @contextlib.asynccontextmanager
    async def _open():
        yield db

    return _open


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    """A notifier whose settings, session, and OA client are all fakes.

    ``get_settings`` is patched on :mod:`backend.config` rather than on
    the adapter: the adapter imports it *inside* the method (the Telegram
    hot path must not pay for the media stack at import time), so the
    source module is the only binding there is to patch.
    """
    db = FakeMediaSession()
    client = FakeOAClient(db)
    settings = settings_for(tmp_path)

    import backend.config

    monkeypatch.setattr(backend.config, "get_settings", lambda: settings)

    def make(*, user_id=None):
        return ZaloNotifier(
            client,
            SENDER,
            user_id=user_id,
            session_factory=session_factory_for(db),
        )

    return SimpleNamespace(
        make=make, db=db, client=client, settings=settings, tmp_path=tmp_path
    )


# ---------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bytes_become_a_url_zalo_can_fetch(wired):
    owner = uuid.uuid4()

    result = await wired.make(user_id=owner).send_photo(
        0, PNG, caption="Twin của bạn", filename="be-tien-twin.png"
    )

    assert result == {"ok": True, "channel": "zalo"}
    assert len(wired.client.images) == 1
    recipient, image_url, caption = wired.client.images[0]
    assert recipient == SENDER
    assert image_url.startswith(f"{BASE_URL}/api/v1/media/")
    assert caption == "Twin của bạn"
    # No second message: an image plus its caption is one CS send, which
    # is what the 48h window ledger upstream is counting.
    assert wired.client.sent == []


@pytest.mark.asyncio
async def test_the_published_row_belongs_to_the_caller_supplied_user(wired):
    owner = uuid.uuid4()

    await wired.make(user_id=owner).send_photo(0, PNG, caption="Twin")

    assert len(wired.db.rows) == 1
    assert wired.db.rows[0].user_id == owner
    assert wired.db.rows[0].byte_size == len(PNG)


@pytest.mark.asyncio
async def test_the_bytes_are_on_disk_under_the_row_s_storage_key(wired):
    await wired.make(user_id=uuid.uuid4()).send_photo(0, PNG, caption="Twin")

    key = wired.db.rows[0].storage_key
    stored = media_storage_module.FilesystemMediaStorage(
        wired.settings.media_storage_path
    )
    assert await stored.read(key) == PNG


@pytest.mark.asyncio
async def test_the_commit_happens_before_the_url_is_handed_to_zalo(wired):
    """The ordering hazard from ``media_url_service``'s docstring.

    Zalo fetches within seconds. A URL sent while its row is still
    uncommitted resolves to a 404 that nothing logs — the send succeeded,
    the image just never appears.
    """
    await wired.make(user_id=uuid.uuid4()).send_photo(0, PNG, caption="Twin")

    assert wired.client.commits_at_send == [1]


@pytest.mark.asyncio
async def test_an_explicit_image_url_skips_publishing_entirely(wired):
    """Callers that already host the asset shouldn't mint a second copy."""
    result = await wired.make(user_id=uuid.uuid4()).send_photo(
        0, PNG, caption="Twin", image_url="https://cdn.test/twin.png"
    )

    assert result is not None
    assert wired.client.images[0][1] == "https://cdn.test/twin.png"
    assert wired.db.rows == []
    assert wired.db.commits == 0


# ---------------------------------------------------------------------
# Degrading to text — four routes to the same place
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flag_off_sends_the_caption_as_text(wired):
    wired.settings.media_url_enabled = False

    result = await wired.make(user_id=uuid.uuid4()).send_photo(
        0, PNG, caption="Twin của bạn"
    )

    assert result == {"ok": True, "channel": "zalo"}
    assert wired.client.images == []
    assert wired.client.sent == [(SENDER, "Twin của bạn")]
    assert wired.db.rows == []


@pytest.mark.asyncio
async def test_no_public_base_url_sends_the_caption_as_text(wired):
    """An unreachable deployment saying "text only", not a misconfig."""
    wired.settings.media_public_base_url = ""

    await wired.make(user_id=uuid.uuid4()).send_photo(0, PNG, caption="Twin")

    assert wired.client.images == []
    assert wired.client.sent == [(SENDER, "Twin")]


@pytest.mark.asyncio
async def test_an_unlinked_sender_falls_back_and_says_so(wired, monkeypatch, caplog):
    """``media_objects.user_id`` is NOT NULL and we will not invent one."""

    async def no_link(db, zalo_user_id):
        return None

    monkeypatch.setattr(zalo_linking_service, "get_linked_user", no_link)

    with caplog.at_level(logging.WARNING, logger=NOTIFIER_LOGGER):
        await wired.make().send_photo(0, PNG, caption="Twin")

    assert "zalo.media.unlinked" in caplog.text
    assert SENDER not in caplog.text
    assert wired.client.images == []
    assert wired.client.sent == [(SENDER, "Twin")]
    assert wired.db.rows == []


@pytest.mark.asyncio
async def test_a_linked_sender_publishes_under_the_looked_up_user(wired, monkeypatch):
    """The inbound handler builds the notifier before it knows the user."""
    owner = uuid.uuid4()

    async def linked(db, zalo_user_id):
        assert zalo_user_id == SENDER
        return SimpleNamespace(id=owner)

    monkeypatch.setattr(zalo_linking_service, "get_linked_user", linked)

    await wired.make().send_photo(0, PNG, caption="Twin")

    assert wired.db.rows[0].user_id == owner
    assert wired.client.images


@pytest.mark.asyncio
async def test_a_storage_failure_degrades_instead_of_raising(
    wired, monkeypatch, caplog
):
    """The ``Notifier`` port promises not to raise, and a chart that
    failed to upload must not take the briefing down with it."""

    class ExplodingStorage:
        def __init__(self, root):
            self._root = root

        async def write(self, key, data):
            raise OSError("disk full")

    monkeypatch.setattr(
        media_storage_module, "FilesystemMediaStorage", ExplodingStorage
    )

    with caplog.at_level(logging.ERROR, logger=NOTIFIER_LOGGER):
        result = await wired.make(user_id=uuid.uuid4()).send_photo(
            0, PNG, caption="Twin"
        )

    assert "zalo.media.publish_failed" in caplog.text
    assert result == {"ok": True, "channel": "zalo"}
    assert wired.client.sent == [(SENDER, "Twin")]


@pytest.mark.asyncio
async def test_a_photo_with_no_caption_and_no_url_sends_nothing(wired):
    """Nothing to say and no image to say it with — silence, not an
    empty bubble. The window wrapper reads the same condition off
    ``can_publish_images`` so no slot is reserved either."""
    wired.settings.media_url_enabled = False

    result = await wired.make(user_id=uuid.uuid4()).send_photo(0, PNG)

    assert result is None
    assert wired.client.sent == []
    assert wired.client.images == []


# ---------------------------------------------------------------------
# Caption ceiling and content type
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_caption_gets_the_full_message_ceiling(wired):
    """The caption travels in ``message.text`` — the same field a plain CS
    send fills — so it gets the same 300 chars. The old 100 was our own
    invention and would have split every Twin (~230 chars) into two
    sends, spending two of the window's eight slots to say one thing."""
    caption = "Bé Tiền theo dõi vùng dự phóng của bạn. " * 20

    await wired.make(user_id=uuid.uuid4()).send_photo(0, PNG, caption=caption)

    sent_caption = wired.client.images[0][2]
    assert len(sent_caption) == 300
    assert sent_caption.endswith("…")


@pytest.mark.asyncio
async def test_a_caption_that_fits_is_sent_whole(wired):
    caption = "Bé Tiền theo dõi vùng dự phóng của bạn. " * 6
    assert 100 < len(caption) <= 300  # the interval the old cap would have cut

    await wired.make(user_id=uuid.uuid4()).send_photo(0, PNG, caption=caption)

    assert wired.client.images[0][2] == caption.strip()


@pytest.mark.asyncio
async def test_the_caption_is_stripped_of_markdown(wired):
    await wired.make(user_id=uuid.uuid4()).send_photo(
        0, PNG, caption="*Twin* của `bạn`"
    )

    assert wired.client.images[0][2] == "Twin của bạn"


@pytest.mark.asyncio
async def test_the_content_type_follows_the_renderer_s_filename(wired):
    await wired.make(user_id=uuid.uuid4()).send_photo(
        0, PNG, caption="Twin", filename="be-tien-twin.png"
    )

    assert wired.db.rows[0].content_type == "image/png"


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("be-tien-twin.png", "image/png"),
        ("share.JPG", "image/jpeg"),
        ("share.jpeg", "image/jpeg"),
        ("loading.gif", "image/gif"),
        # An unknown suffix is far more likely a caller passing a label
        # than a genuinely different format, and guessing wrong sets a
        # Content-Type Zalo will refuse. PNG is the honest default.
        ("chart.webp", "image/png"),
        ("no-suffix", "image/png"),
        ("", "image/png"),
        (None, "image/png"),
    ],
)
def test_content_type_table(filename, expected):
    assert _content_type_for(filename) == expected


# ---------------------------------------------------------------------
# can_publish_images — the question the window wrapper asks
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("enabled", "base_url", "expected"),
    [
        (True, BASE_URL, True),
        (False, BASE_URL, False),
        (True, "", False),
        (False, "", False),
    ],
)
def test_can_publish_images_needs_both_settings(
    tmp_path, monkeypatch, enabled, base_url, expected
):
    import backend.config

    monkeypatch.setattr(
        backend.config,
        "get_settings",
        lambda: settings_for(tmp_path, enabled=enabled, base_url=base_url),
    )

    notifier = ZaloNotifier(FakeOAClient(), SENDER)

    assert notifier.can_publish_images is expected
