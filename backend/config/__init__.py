"""Application configuration — settings + shared constants.

Importing `backend.config` yields the Settings loader (preserving the pre-split
`from backend.config import get_settings, Settings` entry points). Domain
constants such as categories / emoji maps live in submodules:

    from backend.config.categories import get_category, get_all_categories
    from backend.config.emoji_map import EMOJI_MAP
"""
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Backend
    environment: str = "development"
    port: int = 8001
    internal_api_key: str = ""

    # Database
    database_url: str = ""  # Set via DATABASE_URL env var

    # Database connection pool — see docs/strategy/scaling-refactor-A.md §A2.
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

    # OpenClaw Skills
    finance_api_url: str = "http://localhost:8001/api/v1"
    finance_api_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


__all__ = ["Settings", "get_settings"]
