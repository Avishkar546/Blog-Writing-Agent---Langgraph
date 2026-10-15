from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = Field(
        default="postgresql+psycopg://blog_app:blog_app@localhost:5432/blog_generator"
    )
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    tavily_api_key: str = ""
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    tpm_budget: int = Field(default=7600, gt=0)
    max_image_bytes: int = Field(default=10 * 1024 * 1024, gt=0)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
