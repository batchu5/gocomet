from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # backend/.env, wherever the server is started from
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parent.parent / ".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/rfq_auction"
    cors_origins: str = "http://localhost:5173"
    # How often the background job checks for auctions that have reached their close time.
    close_job_interval_seconds: float = 2.0


settings = Settings()
