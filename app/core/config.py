from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Sales Agent Platform"
    app_env: str = "development"
    app_debug: bool = True
    api_v1_prefix: str = "/api/v1"

    secret_key: str = "CHANGE_ME_WITH_A_LONG_RANDOM_SECRET"
    access_token_expire_minutes: int = 60
    algorithm: str = "HS256"

    postgres_user: str = "aiagent"
    postgres_password: str = "aiagent_dev_password"
    postgres_db: str = "aiagent"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    redis_url: str = "redis://localhost:6379/0"

    llm_provider: str = "mock"
    mock_model: str = "mock-v0.2"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-terra"
    openai_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "low"
    openai_timeout_seconds: float = 45.0
    openai_max_retries: int = 2

    embedding_provider: str = "openai"
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_batch_size: int = 64
    knowledge_max_upload_mb: int = 10
    knowledge_chunk_chars: int = 1200
    knowledge_chunk_overlap_chars: int = 200
    rag_top_k: int = 5
    rag_min_similarity: float = 0.15


    whatsapp_verify_token: str = "local-v08-verify-token"
    whatsapp_app_secret: str = "local-v08-app-secret-change-me"
    whatsapp_graph_api_version: str = "v26.0"
    whatsapp_webhook_max_body_bytes: int = 1048576
    whatsapp_http_timeout_seconds: float = 20.0

    # v0.9 Realtime Voice foundation
    openai_realtime_model: str = "gpt-realtime-2.1"
    openai_realtime_voice: str = "marin"
    openai_realtime_timeout_seconds: float = 30.0
    voice_audio_max_bytes: int = 5_000_000
    voice_session_max_minutes: int = 60

    # v0.10 Twilio Media Streams bridge laboratory
    voice_bridge_lab_enabled: bool = True
    voice_bridge_lab_token: str = "local-v10-bridge-token-change-me"
    voice_barge_in_enabled: bool = True
    voice_bridge_playback_speed: float = 4.0

    bootstrap_tenant_name: str = "Demo Tenant"
    bootstrap_tenant_slug: str = "demo"
    bootstrap_admin_email: str = "admin@example.com"
    bootstrap_admin_password: str = "ChangeMe123!"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def langgraph_database_url(self) -> str:
        # LangGraph PostgresSaver uses psycopg, not SQLAlchemy/asyncpg.
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
