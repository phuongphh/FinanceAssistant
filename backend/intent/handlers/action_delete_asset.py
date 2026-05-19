"""Handler for ``ACTION_DELETE_ASSET`` — open the asset delete picker.

Triggered by free-text like "xoá tài sản", "xoá tài sản ACB",
"xoá ví zalopay", "xoá cổ phiếu FPT". The handler tries (in order):

1. If ``asset_name`` is extracted AND matches exactly one active asset,
   open the per-asset confirm-delete card directly so the user
   completes the task with one tap.
2. If ``asset_type`` is extracted, jump straight to the type-scoped
   delete list (``show_asset_delete_list``).
3. Otherwise show the type-picker (``show_asset_delete_type_picker``)
   so the user narrows the list before tapping ``🗑``.

Returns "" so the dispatcher skips the duplicate plain-text send.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot.handlers import asset_entry as asset_entry_handlers
from backend.intent.extractors._normalize import strip_diacritics
from backend.intent.handlers.base import IntentHandler
from backend.intent.intents import IntentResult
from backend.models.user import User
from backend.wealth.services import asset_service

logger = logging.getLogger(__name__)


def _name_matches(asset_name: str, query: str) -> bool:
    """Case- and diacritic-insensitive containment check.

    The classifier hands us the diacritic-stripped, lowercased
    capture (e.g. "vang sjc"), but asset names in the DB keep their
    diacritics ("Vàng SJC"). Strip both sides before comparing so the
    matcher behaves the way users expect.
    """
    if not asset_name or not query:
        return False
    return strip_diacritics(query.lower()) in strip_diacritics(asset_name.lower())




def _asset_matches_query(asset, query: str) -> bool:
    """Match by display name OR ticker/symbol in ``asset.extra``."""
    if _name_matches(getattr(asset, "name", ""), query):
        return True
    extra = getattr(asset, "extra", {}) or {}
    for key in ("ticker", "symbol", "code"):
        v = extra.get(key)
        if not v:
            continue
        if _name_matches(str(v), query):
            return True
    return False


def _asset_matches_exactly(asset, query: str) -> bool:
    """Stricter than ``_asset_matches_query`` — requires equality on name
    or ticker/symbol after diacritic+case normalization. Used to break
    ties when a query like "TCEF" substring-hits multiple assets but the
    user clearly meant the one named "TCEF".
    """
    q = strip_diacritics((query or "").lower()).strip()
    if not q:
        return False
    name = strip_diacritics(str(getattr(asset, "name", "") or "").lower()).strip()
    if name == q:
        return True
    extra = getattr(asset, "extra", {}) or {}
    for key in ("ticker", "symbol", "code"):
        v = extra.get(key)
        if v and strip_diacritics(str(v).lower()).strip() == q:
            return True
    return False
class ActionDeleteAssetHandler(IntentHandler):
    async def handle(
        self, intent: IntentResult, user: User, db: AsyncSession
    ) -> str:
        params = intent.parameters or {}
        asset_type = params.get("asset_type")
        asset_name = (params.get("asset_name") or "").strip()
        asset_subtype = params.get("asset_subtype")
        chat_id = user.telegram_id

        if asset_name:
            assets = await asset_service.get_user_assets(db, user.id)
            matches = [
                a
                for a in assets
                if a.is_active and _asset_matches_query(a, asset_name)
                and (asset_type is None or str(a.asset_type) == asset_type)
                and (asset_subtype is None or str(getattr(a, "subtype", "")) == asset_subtype)
            ]
            if len(matches) > 1:
                exact = [a for a in matches if _asset_matches_exactly(a, asset_name)]
                if len(exact) == 1:
                    matches = exact
            if len(matches) == 1:
                await asset_entry_handlers._confirm_asset_delete(
                    db, chat_id, user, str(matches[0].id)
                )
                return ""
            if len(matches) > 1:
                inferred_asset_type = asset_type
                if inferred_asset_type is None:
                    match_types = {str(a.asset_type) for a in matches}
                    if len(match_types) == 1:
                        inferred_asset_type = match_types.pop()
                if inferred_asset_type:
                    await asset_entry_handlers.show_asset_delete_list(
                        db, chat_id, user, inferred_asset_type, subtype=asset_subtype
                    )
                    return ""

        if asset_type:
            await asset_entry_handlers.show_asset_delete_list(
                db, chat_id, user, asset_type, subtype=asset_subtype
            )
            return ""

        await asset_entry_handlers.show_asset_delete_type_picker(db, chat_id, user)
        return ""
