from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    keitaro_api_url: str = "https://tracker.example.com"
    keitaro_admin_url: str | None = None
    keitaro_api_key: str = ""
    keitaro_domain_id: int | None = None
    # Keitaro campaign group_id. On this tracker FORTESTS is 10332.
    keitaro_group_id: int | None = None
    # Keitaro traffic_source_id. On tlgk.host, FORTESTS is 836.
    keitaro_source_id: int | None = None
    database_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
