# syntax=docker/dockerfile:1
# Agent Observatory backend image (ADR-0005; AO-P1-004).
# Build context: ./backend. Runtime config comes only from AO_* environment
# variables; no secrets are baked into the image.

ARG PYTHON_IMAGE=python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.18@sha256:3adc3706091ce7c2fe595e669628caedd6d951551b92b258b7e7dbe06d9440bc

FROM ${UV_IMAGE} AS uv

# ---- build: resolve strictly from uv.lock into /app/.venv ----
FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3.12 \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
# Dependencies first (cached layer), then the project itself (non-editable).
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ---- runtime: no build tools, non-root ----
FROM ${PYTHON_IMAGE} AS runtime
# The app runs from /app/.venv; the base image's pip/setuptools are not needed at runtime.
RUN python -m pip uninstall --yes --no-input pip setuptools wheel \
 && groupadd --system --gid 10001 observatory \
 && useradd --system --uid 10001 --gid observatory --no-create-home --home-dir /nonexistent \
      --shell /usr/sbin/nologin observatory
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
# Alembic environment for the one-shot `migrate` service (same image).
COPY alembic.ini ./
COPY migrations ./migrations
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]
CMD ["uvicorn", "observatory.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
