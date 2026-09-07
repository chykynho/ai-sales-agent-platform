from __future__ import annotations

import json
import re
import sys

import httpx

BASE = "http://127.0.0.1:8000"
API = BASE + "/api/v1"
REQUEST_ID = "v012-observability-smoke"
TRACE_RE = re.compile(r"^[0-9a-f]{32}$")


def fail(message: str) -> None:
    raise AssertionError(message)


def login(client: httpx.Client) -> str:
    response = client.post(
        API + "/auth/login",
        headers={"X-Tenant-Slug": "demo"},
        data={"username": "admin@example.com", "password": "ChangeMe123!"},
    )
    response.raise_for_status()
    token = str(response.json().get("access_token") or "")
    if not token:
        fail("Login nao retornou access_token")
    return token


def main() -> int:
    print("=== AI Sales Agent Platform v0.12 - Observability/SRE Smoke Test ===")
    with httpx.Client(timeout=15.0) as client:
        print("\n[1/6] Liveness + correlacao request/trace...")
        response = client.get(API + "/health/live", headers={"X-Request-ID": REQUEST_ID})
        response.raise_for_status()
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.12.0"
        assert response.headers.get("x-request-id") == REQUEST_ID
        trace_id = str(response.headers.get("x-trace-id") or "")
        assert TRACE_RE.match(trace_id), f"X-Trace-ID invalido: {trace_id!r}"
        print(json.dumps({"request_id": REQUEST_ID, "trace_id": trace_id}, ensure_ascii=False, indent=2))

        print("\n[2/6] Readiness PostgreSQL + Redis...")
        response = client.get(API + "/health/ready")
        response.raise_for_status()
        ready = response.json()
        assert ready["status"] == "ok"
        assert ready["postgres"] is True
        assert ready["redis"] is True
        print(json.dumps(ready, ensure_ascii=False, indent=2))

        print("\n[3/6] Login e configuracao de observabilidade...")
        token = login(client)
        auth = {"Authorization": "Bearer " + token}
        response = client.get(API + "/observability/config", headers=auth)
        response.raise_for_status()
        config = response.json()
        assert config["enabled"] is True
        assert config["app_version"] == "0.12.0"
        assert config["metrics"]["enabled"] is True
        assert config["tracing"]["enabled"] is True
        assert set(config["sre"]["golden_signals"]) == {"latency", "traffic", "errors", "saturation"}
        print(json.dumps(config, ensure_ascii=False, indent=2))

        print("\n[4/6] Trafego autenticado para metricas por tenant...")
        for path in ("/users/me", "/tenant/config", "/ai/config"):
            r = client.get(API + path, headers=auth)
            r.raise_for_status()
        print("[OK] Requisicoes autenticadas executadas")

        print("\n[5/6] Endpoint Prometheus e metricas essenciais...")
        response = client.get(BASE + "/metrics")
        response.raise_for_status()
        metrics = response.text
        required = (
            "http_requests_total",
            "http_request_duration_seconds",
            "http_in_flight_requests",
            "tenant_requests_total",
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
            "process_resident_memory_bytes",
            "process_cpu_seconds_total",
        )
        missing = [name for name in required if name not in metrics]
        assert not missing, f"Metricas ausentes: {missing}"
        assert "tenant_requests_total" in metrics and "4c58e10a-91e5-4e68-8d29-6e24dea34858" in metrics
        print(f"[OK] {len(required)} contratos de metricas encontrados")

        print("\n[6/6] Versao raiz + ausencia de segredos na exposicao Prometheus...")
        root = client.get(BASE + "/")
        root.raise_for_status()
        assert root.json().get("version") == "0.12.0"
        forbidden = ("OPENAI_API_KEY", "TWILIO_AUTH_TOKEN", "ChangeMe123!")
        for item in forbidden:
            assert item not in metrics
        print("[OK] / reporta v0.12.0 e /metrics nao expoe segredos conhecidos")

    print("\n=== v0.12 OBSERVABILITY/SRE VALIDADA COM SUCESSO ===")
    print("Metrics   : http://localhost:8000/metrics")
    print("Liveness  : http://localhost:8000/api/v1/health/live")
    print("Readiness : http://localhost:8000/api/v1/health/ready")
    print("Trace ID  : " + trace_id)
    print("Stack     : execute scripts/start_observability_v12.ps1 para Prometheus/Grafana/Tempo")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"v0.12 observability smoke test failed: {type(exc).__name__}({exc})", file=sys.stderr)
        raise
