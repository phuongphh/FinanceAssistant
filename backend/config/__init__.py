"""Application configuration — settings + shared constants.

Importing `backend.config` yields the Settings loader (preserving the pre-split
`from backend.config import get_settings, Settings` entry points). Domain
constants such as categories / emoji maps live in submodules:

    from backend.config.categories import get_category, get_all_categories
    from backend.config.emoji_map import EMOJI_MAP
"""
from functools import lru_cache

from pydantic_settings import BaseSettings


APP_VERSION = "1.3.8.01"


class Settings(BaseSettings):
    # Backend
    environment: str = "development"
    port: int = 8001
    internal_api_key: str = ""

    # Database
    database_url: str = ""  # Set via DATABASE_URL env var

    # Database connection pool — see docs/archive/scaling-refactor-A.md §A2.
    # Defaults target 1K-user Phase 1 VPS; override via env for Mac Mini dev.
    db_pool_size: int = 20
    db_max_overflow: int = 30
    db_pool_timeout: int = 10           # seconds to wait for a connection
    db_pool_recycle: int = 1800         # recycle after 30 min (avoid stale conns)
    db_pool_pre_ping: bool = True       # ping before checkout — detect dead conns

    # LLM APIs
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    anthropic_api_key: str = ""
    # External OCR provider (text extraction from receipt images). The
    # response is then parsed into structured fields by DeepSeek via
    # ``llm_service.call_llm`` — this keeps vision and reasoning concerns
    # separate and avoids paying Claude vision prices for every receipt.
    ocr_api_url: str = "https://ocr.nuitruc.ai/api/v1/ocr/extract"
    ocr_api_key: str = ""  # Optional bearer token; empty = no auth header
    ocr_api_timeout_seconds: float = 20.0
    # OpenAI key — currently used only for Whisper voice transcription.
    # Empty in dev/CI is fine; the voice path falls back to a friendly
    # "tính năng voice chưa bật" message.
    openai_api_key: str = ""

    # Gmail OAuth2
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_redirect_uri: str = "http://localhost:8000/auth/gmail/callback"

    # Notion
    notion_api_key: str = ""
    notion_expenses_db_id: str = ""
    notion_goals_db_id: str = ""
    notion_reports_db_id: str = ""
    notion_market_db_id: str = ""
    notion_investment_log_db_id: str = ""

    # Telegram
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""  # Validates webhook requests from Telegram
    owner_telegram_id: str = ""
    # Optional Telegram custom emoji id for the animated sunrise in morning briefings.
    telegram_morning_custom_emoji_id: str = ""

    # Zalo Official Account (Phase 4B Epic 4)
    # Provisioned manually by ops; empty in dev/CI degrades gracefully — the
    # adapter returns False on send and linking flows surface a friendly
    # "not configured" message instead of raising.
    zalo_oa_access_token: str = ""
    zalo_oa_secret_key: str = ""  # Used to verify webhook X-ZEvent-Signature
    zalo_app_id: str = ""
    # Phase 4.1 channel-discipline gate. The Zalo OA adapter is fully wired
    # (Phase 4B) but DISABLED for the 50-user Telegram-only soft launch so
    # we measure one channel cleanly. Operator flips this to True at the
    # start of Phase 5.1 (Zalo rollout).
    zalo_channel_enabled: bool = False

    # Market data
    redis_url: str = "redis://localhost:6379/0"
    market_data_timeout_seconds: float = 3.0
    market_data_alerts_enabled: bool = False

    # OpenClaw Skills
    finance_api_url: str = "http://localhost:8001/api/v1"
    finance_api_key: str = ""

    # Telegram Mini App — public HTTPS base for the wealth dashboard.
    # Telegram requires a valid HTTPS URL for ``web_app`` inline buttons,
    # so production must override this; dev/CI leaves it empty and the
    # briefing handler falls back to a placeholder message.
    miniapp_base_url: str = ""

    # Label for the bot's chat menu button (next to the message input). Kept
    # short because Telegram truncates long labels on narrow viewports — the
    # legacy "Báo cáo tài sản" overflowed on iOS. Code-driven so each deploy
    # can re-sync the menu (label + cache-bust URL) without a manual BotFather
    # edit. Override via env var if product-renamed.
    miniapp_menu_label: str = "💰 Tài sản"

    # ``extra="ignore"`` lets the .env file hold sibling env vars used by
    # docker-compose (e.g. POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB)
    # without pydantic-settings 2.x rejecting them as extras.
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()


__all__ = ["APP_VERSION", "Settings", "get_settings"]
