# syntax=docker/dockerfile:1

# ---------- Stage 1: build frontend ----------
FROM node:22-alpine AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: install backend deps ----------
FROM python:3.14-slim AS backend-deps
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

# ---------- Stage 3: runtime ----------
FROM python:3.14-slim AS runtime
LABEL org.opencontainers.image.title="PromPilot" \
      org.opencontainers.image.description="Chat-driven Prometheus visualization with Grafana export" \
      org.opencontainers.image.licenses="Apache-2.0"

RUN groupadd --system --gid 1000 prompilot \
 && useradd --system --uid 1000 --gid prompilot --home /app prompilot \
 && mkdir -p /data && chown prompilot:prompilot /data

WORKDIR /app
COPY --from=backend-deps /opt/venv /opt/venv
COPY --chown=prompilot:prompilot backend/app ./app
COPY --from=frontend --chown=prompilot:prompilot /src/dist ./app/static

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    PORT=8080

USER prompilot
VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request,os,sys; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8080\")}/healthz', timeout=2).status==200 else 1)"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --log-level ${LOG_LEVEL:-info}"]
