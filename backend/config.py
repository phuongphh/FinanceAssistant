from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Backend
    environment: str = "development"
    port: int = 8000
    internal_api_key: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://finance:password@localhost:5432/finance_db"

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
    owner_telegram_id: str = ""

    # OpenClaw Skills
    finance_api_url: str = "http://localhost:8000/api/v1"
    finance_api_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
