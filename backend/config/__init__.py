"""Application configuration — settings + shared constants.

Importing `backend.config` yields the Settings loader (preserving the pre-split
`from backend.config import get_settings, Settings` entry points). Domain
constants such as categories / emoji maps live in submodules:

    from backend.config.categories import get_category, get_all_categories
    from backend.config.emoji_map import EMOJI_MAP
"""
from functools import lru_cache

from pydantic_settings import BaseSettings


APP_VERSION = "1.4.4.00"


class Settings(BaseSettings):
    # Backend
    environment: str = "development"
    port: int = 8001
    internal_api_key: str = ""

    # Admin Observability Console (Phase 4.2.5)
    admin_jwt_secret: str = ""
    admin_jwt_expiry_minutes: int = 60
    admin_redis_url: str = "redis://localhost:6379/1"
    admin_allowed_origin: str = "https://admin.betien.vn"
    admin_api_rate_limit_per_minute: int = 100

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
    # Speech-to-text provider (self-hosted, Vietnamese-tuned). Accepts a
    # multipart audio upload and returns ``{"transcript": ...}``. Telegram
    # voice notes (OGG/Opus) are accepted natively — no transcoding needed.
    # 30s timeout covers the worst observed cold-start (~1s warm, but the
    # service occasionally pauses on first hit after idle).
    stt_api_url: str = "https://stt.nuitruc.ai/api/stt/upload"
    stt_api_key: str = ""  # Optional bearer token; empty = no auth header
    stt_api_timeout_seconds: float = 30.0
    # OpenAI key — historically used for Whisper STT before we moved to
    # ``stt.nuitruc.ai``. Kept here only because some legacy tests reference
    # it; can be dropped once those are cleaned up.
    openai_api_key: str = ""

    # Groq (Tier 1 NLU classifier). DeepSeek V4-Flash is fast in
    # throughput but 4-12s to first token by design, which is too slow
    # for interactive intent classification. Groq's Llama 3.3 70B serves
    # the same prompt in ~300-700ms at $0.59/$0.79 per 1M tokens. Empty
    # in dev/CI degrades to rule-based classification only.
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.3-70b-versatile"

    # Default per-call timeout for LLM HTTP requests (seconds). Tier 1
    # callers override to ~3s; everything else (OCR parse, reports,
    # storytelling, advisory, goal roadmaps) flows through DeepSeek
    # V4-Flash, which is 4-12s to first token by design and can run
    # 20-40s for long-context outputs. Default keeps 5x headroom over
    # worst-case first-token so the slow tail doesn't false-alarm, while
    # still capping runaway hangs.
    llm_timeout_seconds: float = 60.0

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
    # VN stock dispatcher order. "vndirect" makes api-finfo.vndirect.com.vn the
    # primary and SSI the backup; "ssi" keeps the historical SSI-first order.
    # Switched to VNDIRECT-first by default after the SSI iboard dchart
    # endpoint stopped returning data reliably.
    stock_provider_primary: str = "vndirect"

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

    # Expense Enhancement — opt-in 22:00 ICT daily transaction summary.
    daily_transaction_summary_enabled: bool = False

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
