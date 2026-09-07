from __future__ import annotations

import json
import logging
from pathlib import Path

from prometheus_client import generate_latest

from app.core.config import settings
from app.core.logging import JsonFormatter
from app.observability.context import bind_context, clear_context, snapshot
from app.observability.redaction import redact_value


def test_v012_settings_contract():
    assert settings.app_version == "0.12.0"
    assert settings.observability_enabled is True
    assert settings.observability_metrics_enabled is True
    assert settings.observability_tracing_enabled is True
    assert settings.observability_service_name == "ai-sales-agent-platform"


def test_prometheus_contract_exposes_core_metric_names():
    from app.observability import metrics  # noqa: F401

    text = generate_latest().decode("utf-8")
    for name in (
        "http_requests_total",
        "http_request_duration_seconds",
        "llm_requests_total",
        "llm_tokens_total",
        "llm_cost_usd_total",
        "agent_runs_total",
        "tool_calls_total",
        "rag_search_total",
        "voice_sessions_total",
        "voice_stt_duration_seconds",
        "voice_realtime_duration_seconds",
        "twilio_calls_total",
        "active_voice_sessions",
    ):
        assert name in text


def test_json_logging_contains_context_and_redacts_secret():
    clear_context()
    bind_context(request_id="req-v012", tenant_id="tenant-v012")
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test.observability",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="observability_ok",
        args=(),
        exc_info=None,
    )
    record.api_key = "super-secret"
    record.http_status = 200
    payload = json.loads(formatter.format(record))
    assert payload["message"] == "observability_ok"
    assert payload["request_id"] == "req-v012"
    assert payload["tenant_id"] == "tenant-v012"
    assert payload["api_key"] == "***REDACTED***"
    assert payload["http_status"] == 200
    clear_context()


def test_context_snapshot_has_controlled_fields():
    clear_context()
    bind_context(request_id="r1", tenant_id="t1", conversation_id="c1", call_sid="ca1")
    data = snapshot()
    assert data["request_id"] == "r1"
    assert data["tenant_id"] == "t1"
    assert data["conversation_id"] == "c1"
    assert data["call_sid"] == "ca1"
    assert "trace_id" in data and "span_id" in data
    clear_context()


def test_redaction_masks_phone_and_tokens():
    assert redact_value("Authorization", "Bearer abc") == "***REDACTED***"
    assert redact_value("openai_api_key", "sk-test") == "***REDACTED***"
    assert "***PHONE***" in str(redact_value("message", "ligue para +5511999999999"))


def test_observability_stack_files_are_provisioned():
    root = Path(__file__).resolve().parents[1]
    compose = (root / "docker-compose.observability.yml").read_text(encoding="utf-8")
    assert "prometheus:" in compose
    assert "grafana:" in compose
    assert "tempo:" in compose
    assert "OBSERVABILITY_OTLP_ENDPOINT" in compose
    assert (root / "observability/prometheus/prometheus.yml").exists()
    assert (root / "observability/grafana/dashboards/ai-sales-agent-sre.json").exists()
    middleware = (root / "app/observability/middleware.py").read_text(encoding="utf-8")
    assert "BaseHTTPMiddleware" not in middleware
    assert "class ObservabilityMiddleware" in middleware
    assert 'or "__unmatched__"' in middleware


def test_metrics_endpoint_is_exact_without_redirect_mount():
    root = Path(__file__).resolve().parents[1]
    main_py = (root / "app/main.py").read_text(encoding="utf-8")
    assert '@app.get("/metrics", include_in_schema=False)' in main_py
    assert 'app.mount("/metrics"' not in main_py
    assert "generate_latest()" in main_py
    assert "CONTENT_TYPE_LATEST" in main_py
