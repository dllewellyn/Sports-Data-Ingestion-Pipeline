FROM python:3.12-slim

# uv for fast, reproducible dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    # Keep the venv OUTSIDE /app so a bind-mount of the source over /app
    # (for live code reload in dev) does not shadow installed dependencies.
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    DAGSTER_HOME=/app/.dagster

RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first for better layer caching, pinned by the lockfile.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen

# Application code (also bind-mounted in dev, baked in for prod).
COPY . .

RUN mkdir -p /app/.dagster /app/data/bronze /app/data/silver /app/data/gold

EXPOSE 3000 8888
