from __future__ import annotations

from decimal import Decimal
from typing import Any

from prometheus_client import Counter, Gauge, Histogram

from app.core.config import settings

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total de requisições HTTP processadas.",
    ("method", "route", "status_code"),
)
HTTP_ERRORS = Counter(
    "http_errors_total",
    "Total de respostas HTTP 5xx.",
    ("method", "route", "status_code"),
)
HTTP_DURATION = Histogram(
    "http_request_duration_seconds",
    "Duração das requisições HTTP em segundos.",
    ("method", "route"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)
HTTP_IN_FLIGHT = Gauge(
    "http_in_flight_requests",
    "Número atual de requisições HTTP em processamento.",
)
TENANT_REQUESTS = Counter(
    "tenant_requests_total",
    "Total de requisições HTTP autenticadas por tenant.",
    ("tenant_id", "route"),
)

LLM_REQUESTS = Counter(
    "llm_requests_total",
    "Total de chamadas LLM.",
    ("provider", "model", "operation", "status"),
)
LLM_DURATION = Histogram(
    "llm_request_duration_seconds",
    "Duração das chamadas LLM em segundos.",
    ("provider", "model", "operation"),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 45, 90),
)
LLM_TOKENS = Counter(
    "llm_tokens_total",
    "Tokens processados por tipo.",
    ("provider", "model", "token_type"),
)
LLM_COST = Counter(
    "llm_cost_usd_total",
    "Custo LLM estimado acumulado em USD.",
    ("provider", "model"),
)
TENANT_LLM_COST = Counter(
    "tenant_llm_cost_usd_total",
    "Custo LLM estimado acumulado em USD por tenant.",
    ("tenant_id",),
)
AGENT_RUNS = Counter(
    "agent_runs_total",
    "Execuções de agente por status e operação.",
    ("operation", "status"),
)
AGENT_RUN_DURATION = Histogram(
    "agent_run_duration_seconds",
    "Duração de execuções de agente em segundos.",
    ("operation",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 45, 90),
)

TOOL_CALLS = Counter(
    "tool_calls_total",
    "Chamadas de ferramentas por nome e status.",
    ("tool_name", "status"),
)
TOOL_ERRORS = Counter(
    "tool_call_errors_total",
    "Erros de ferramentas.",
    ("tool_name", "error_code"),
)
TOOL_DURATION = Histogram(
    "tool_call_duration_seconds",
    "Duração das ferramentas em segundos.",
    ("tool_name",),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)

RAG_SEARCHES = Counter(
    "rag_search_total",
    "Buscas RAG por status.",
    ("status",),
)
RAG_DURATION = Histogram(
    "rag_search_duration_seconds",
    "Duração da busca RAG em segundos.",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)
RAG_RESULTS = Histogram(
    "rag_results",
    "Quantidade de chunks retornados por busca RAG.",
    buckets=(0, 1, 2, 3, 5, 8, 10, 15, 20),
)

VOICE_SESSIONS = Counter(
    "voice_sessions_total",
    "Sessões de voz por provider e status.",
    ("provider", "status"),
)
VOICE_SESSION_DURATION = Histogram(
    "voice_session_duration_seconds",
    "Duração total de sessões de voz em segundos.",
    ("provider",),
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300),
)
VOICE_STT_DURATION = Histogram(
    "voice_stt_duration_seconds",
    "Duração de Speech-to-Text em segundos.",
    ("model",),
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 45),
)
VOICE_REALTIME_DURATION = Histogram(
    "voice_realtime_duration_seconds",
    "Duração das chamadas OpenAI Realtime em segundos.",
    ("model", "operation"),
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 45, 90),
)
ACTIVE_VOICE_SESSIONS = Gauge(
    "active_voice_sessions",
    "Número atual de streams/sessões de voz em processamento.",
    ("mode",),
)

TWILIO_CALLS = Counter(
    "twilio_calls_total",
    "Eventos de chamada Twilio por status.",
    ("status",),
)
TWILIO_CALL_ERRORS = Counter(
    "twilio_call_errors_total",
    "Erros relacionados ao fluxo Twilio.",
    ("error_type",),
)
TWILIO_STREAM_EVENTS = Counter(
    "twilio_stream_events_total",
    "Eventos de status de Media Stream Twilio.",
    ("status",),
)


def enabled() -> bool:
    return bool(settings.observability_enabled and settings.observability_metrics_enabled)


def safe_tenant_label(value: Any) -> str:
    if not settings.observability_tenant_labels:
        return "disabled"
    text = str(value or "").strip()
    return text if text else "unknown"


def observe_llm_success(*, run: Any, result: Any, latency_ms: int) -> None:
    if not enabled():
        return
    provider = str(result.provider)
    model = str(result.model)
    operation = str(run.operation)
    LLM_REQUESTS.labels(provider, model, operation, "completed").inc()
    LLM_DURATION.labels(provider, model, operation).observe(max(0.0, latency_ms / 1000))
    AGENT_RUNS.labels(operation, "completed").inc()
    AGENT_RUN_DURATION.labels(operation).observe(max(0.0, latency_ms / 1000))
    usage = result.usage
    for token_type, value in (
        ("input", usage.input_tokens),
        ("cached_input", usage.cached_input_tokens),
        ("cache_write", usage.cache_write_tokens),
        ("output", usage.output_tokens),
        ("reasoning", usage.reasoning_tokens),
        ("total", usage.total_tokens),
    ):
        amount = int(value or 0)
        if amount > 0:
            LLM_TOKENS.labels(provider, model, token_type).inc(amount)
    cost = getattr(run, "estimated_cost_usd", None)
    if cost is not None:
        try:
            amount = float(Decimal(str(cost)))
        except Exception:
            amount = 0.0
        if amount > 0:
            LLM_COST.labels(provider, model).inc(amount)
            TENANT_LLM_COST.labels(safe_tenant_label(run.tenant_id)).inc(amount)


def observe_llm_failure(*, run: Any, latency_ms: int) -> None:
    if not enabled():
        return
    provider = str(getattr(run, "provider", "unknown") or "unknown")
    model = str(getattr(run, "model", "unknown") or "unknown")
    operation = str(getattr(run, "operation", "unknown") or "unknown")
    LLM_REQUESTS.labels(provider, model, operation, "failed").inc()
    LLM_DURATION.labels(provider, model, operation).observe(max(0.0, latency_ms / 1000))
    AGENT_RUNS.labels(operation, "failed").inc()
    AGENT_RUN_DURATION.labels(operation).observe(max(0.0, latency_ms / 1000))
