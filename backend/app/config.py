"""
Central application configuration.
All values are overridable via environment variables / .env file.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- App ---
    APP_NAME: str = "SENTINEL Backend"
    ENV: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    # --- Database ---
    DATABASE_URL: str = (
        "postgresql+psycopg2://sentinel:sentinel@localhost:5432/sentinel"
    )
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30

    # --- Security / JWT ---
    JWT_SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8

    # --- MinIO ---
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "sentinel-evidence"
    MINIO_SECURE: bool = False

    # --- Local fallback storage ---
    LOCAL_EVIDENCE_FALLBACK_DIR: str = "./data/evidence_fallback"

    # --- Watchlist / Alert engine ---
    ALERT_COOLDOWN_SECONDS: int = 300

    # --- CORS ---
    CORS_ALLOW_ORIGINS: list[str] = ["*"]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
