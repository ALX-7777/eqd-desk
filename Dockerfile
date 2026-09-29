# syntax=docker/dockerfile:1.7
#
# EQD Desk: Streamlit app image.
#
#   docker build -t eqd-desk .
#   docker run --rm -p 8501:8501 eqd-desk        # → http://localhost:8501
#
# To serve on another container port, set it through the environment, not `--server.port`,
# so that the HEALTHCHECK below probes the same port:
#   docker run --rm -e STREAMLIT_SERVER_PORT=8080 -p 8080:8080 eqd-desk
#
# Two stages: `builder` resolves the locked environment with uv; the runtime stage copies
# only the virtualenv (no uv, no build cache, no sources) and runs as a non-root user.

ARG PYTHON_VERSION=3.13

# ------------------------------------------------------------------------------ builder
FROM python:${PYTHON_VERSION}-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# 1) Third-party dependencies only: this layer is cached until uv.lock changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

# 2) The project itself, installed as a regular (non-editable) package.
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ------------------------------------------------------------------------------ runtime
FROM python:${PYTHON_VERSION}-slim AS runtime

LABEL org.opencontainers.image.title="EQD Desk" \
      org.opencontainers.image.description="Equity-index derivatives trader training simulator (Streamlit)" \
      org.opencontainers.image.licenses="MIT"

RUN groupadd --system --gid 1000 app \
 && useradd --system --uid 1000 --gid app --create-home --home-dir /home/app app

COPY --from=builder --chown=app:app /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_FILE_WATCHER_TYPE=none \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501

USER app
WORKDIR /home/app
EXPOSE 8501

# Probes the port the server was told to use (STREAMLIT_SERVER_PORT), not a fixed 8501.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request as u; u.urlopen('http://127.0.0.1:%s/_stcore/health' % os.environ.get('STREAMLIT_SERVER_PORT', '8501'), timeout=4)"]

ENTRYPOINT ["eqd-desk"]
