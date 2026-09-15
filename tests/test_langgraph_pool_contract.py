from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME = PROJECT_ROOT / "app" / "agent" / "runtime.py"
SETUP = PROJECT_ROOT / "scripts" / "setup_langgraph.py"


def test_runtime_uses_psycopg_async_connection_pool() -> None:
    text = RUNTIME.read_text(encoding="utf-8")

    assert "AsyncConnectionPool" in text
    assert "check=AsyncConnectionPool.check_connection" in text
    assert "open=False" in text
    assert "AsyncPostgresSaver(pool)" in text
    assert "AsyncPostgresSaver.from_conn_string" not in text


def test_langgraph_schema_setup_remains_explicit_one_off() -> None:
    text = SETUP.read_text(encoding="utf-8")

    assert "AsyncPostgresSaver.from_conn_string" in text
    assert "await checkpointer.setup()" in text
