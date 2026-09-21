from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import health


app = FastAPI()
app.include_router(health.router, prefix="/api/v1")
client = TestClient(app)


def test_liveness_returns_200():
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_returns_200_when_dependencies_are_healthy(monkeypatch):
    async def dependencies_ok():
        return True, True

    monkeypatch.setattr(health, "_dependency_status", dependencies_ok)

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["postgres"] is True
    assert response.json()["redis"] is True


def test_readiness_returns_503_when_postgres_is_down(monkeypatch):
    async def postgres_down():
        return False, True

    monkeypatch.setattr(health, "_dependency_status", postgres_down)

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["postgres"] is False
    assert response.json()["redis"] is True


def test_readiness_returns_503_when_redis_is_down(monkeypatch):
    async def redis_down():
        return True, False

    monkeypatch.setattr(health, "_dependency_status", redis_down)

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["postgres"] is True
    assert response.json()["redis"] is False
