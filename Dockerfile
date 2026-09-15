FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANGGRAPH_STRICT_MSGPACK=true \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    RUN_MIGRATIONS=false \
    RUN_BOOTSTRAP=false

WORKDIR /app

RUN groupadd --gid 10001 app && \
    useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app

RUN pip install --no-cache-dir --upgrade pip
COPY pyproject.toml /app/

FROM base AS development
RUN pip install --no-cache-dir ".[dev,security]"
COPY . /app
# Defensive EOL normalization: shell scripts are executed by Linux even when
# the source tree was prepared on Windows or extracted from a ZIP.
RUN find /app/scripts -type f -name "*.sh" -exec sed -i 's/\r$//' {} + && \
    chmod +x /app/scripts/entrypoint.sh && \
    chown -R app:app /app
USER app
EXPOSE 8000
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

FROM base AS production
RUN pip install --no-cache-dir .
COPY app /app/app
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini
COPY scripts /app/scripts
# Same defense in production so a CRLF source file can never break the Linux
# shebang before the application starts.
RUN find /app/scripts -type f -name "*.sh" -exec sed -i 's/\r$//' {} + && \
    chmod +x /app/scripts/entrypoint.sh && \
    chown -R app:app /app
USER app
# Cloud Run injects PORT (normally 8080). The image still falls back to 8000
# outside managed serverless environments so local/other cloud usage remains compatible.
EXPOSE 8080
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
