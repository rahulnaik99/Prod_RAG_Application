from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # App
    APP_ENV: str = "development"
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    # CORS — in production set this to your frontend Container App FQDN
    # e.g. ALLOWED_ORIGINS=["https://frontend.happywave-abc123.eastus.azurecontainerapps.io"]
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000"]

    # Database — Azure Database for PostgreSQL Flexible Server
    DATABASE_URL: str  # postgresql+asyncpg://user:pass@host/db?ssl=require

    # Redis — Azure Cache for Redis
    REDIS_URL: str     # rediss://:password@host:6380/0  (TLS on port 6380)

    # Azure Blob Storage (replaces S3)
    AZURE_STORAGE_CONNECTION_STRING: str
    AZURE_STORAGE_CONTAINER: str = "rag-documents"

    # Weaviate Cloud (unchanged)
    WEAVIATE_URL: str
    WEAVIATE_API_KEY: str
    WEAVIATE_CLASS_NAME: str = "Document"

    # OpenAI (unchanged)
    OPENAI_API_KEY: str
    OPENAI_EMBED_MODEL: str = "text-embedding-3-small"
    OPENAI_CHAT_MODEL: str = "gpt-4o"

    # Leaky bucket
    OPENAI_QUEUE_MAX_SIZE: int = 50
    OPENAI_DRAIN_RATE_SECONDS: float = 1.0


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
