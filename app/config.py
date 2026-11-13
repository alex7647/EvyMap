from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки через переменные окружения VENUE_* или файл .env."""

    model_config = SettingsConfigDict(env_prefix="VENUE_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./venue.db"  # для Postgres: postgresql+psycopg://user:pass@host/db
    secret_key: str = "dev-secret-change-me-use-VENUE_SECRET_KEY-in-prod"
    token_ttl_hours: int = 24
    media_dir: Path = Path("./media")
    max_upload_mb: int = 25
    base_max_px: int = 4096


settings = Settings()
