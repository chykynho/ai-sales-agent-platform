from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Sales Agent Platform"
    app_env: str = "development"
    app_debug: bool = True
    api_v1_prefix: str = "/api/v1"
    app_version: str = "0.14.1"

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

    # v0.11 Production Telephony Hardening
    voice_production_enabled: bool = False
    twilio_require_signature: bool = True
    twilio_public_base_url: str | None = None
    twilio_wss_base_url: str | None = None
    openai_transcribe_model: str = "gpt-transcribe"
    voice_vad_rms_threshold: int = 450
    voice_vad_silence_ms: int = 700
    voice_vad_min_speech_ms: int = 240
    voice_vad_max_utterance_ms: int = 15000
    voice_production_first_turn_only: bool = True

    # v0.12 Observability / SRE
    observability_enabled: bool = True
    observability_log_json: bool = True
    observability_metrics_enabled: bool = True
    observability_tracing_enabled: bool = True
    observability_service_name: str = "ai-sales-agent-platform"
    observability_otlp_endpoint: str | None = None
    observability_otlp_timeout_seconds: float = 5.0
    observability_trace_console: bool = False
    observability_tenant_labels: bool = True

    # v0.13 Resiliência / Performance / Load Testing
    resilience_enabled: bool = True
    resilience_fail_open: bool = True
    resilience_rate_limit_enabled: bool = True
    resilience_rate_limit_requests: int = 600
    resilience_rate_limit_window_seconds: int = 60
    resilience_rate_limit_exempt_paths: str = "/metrics,/api/v1/health/live,/api/v1/health/ready,/docs,/openapi.json"
    resilience_bulkhead_enabled: bool = True
    resilience_bulkhead_llm_concurrency: int = 16
    resilience_bulkhead_acquire_timeout_seconds: float = 0.25
    resilience_circuit_breaker_enabled: bool = True
    resilience_circuit_failure_threshold: int = 5
    resilience_circuit_failure_window_seconds: int = 60
    resilience_circuit_cooldown_seconds: int = 30
    resilience_circuit_probe_lock_seconds: int = 10
    # O SDK OpenAI já possui retries internos. Mantemos 1 tentativa externa por padrão
    # para não multiplicar chamadas; aumente somente para providers sem retry próprio.
    resilience_retry_max_attempts: int = 1
    resilience_retry_base_delay_seconds: float = 0.25
    resilience_retry_max_delay_seconds: float = 2.0
    resilience_retry_jitter_seconds: float = 0.10
    load_test_concurrency: int = 20
    load_test_requests: int = 200
    load_test_p95_threshold_ms: float = 750.0
    load_test_error_rate_threshold_pct: float = 1.0

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
