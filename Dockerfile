FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANGGRAPH_STRICT_MSGPACK=true

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip
COPY pyproject.toml /app/
RUN pip install --no-cache-dir ".[dev]"

COPY . /app
RUN chmod +x /app/scripts/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
