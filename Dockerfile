# One image: hands API + operator console + CoreOne mock app + headless Chromium + the built web UI.

# ---- web UI build ----
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---- runtime: Playwright's image ships Chromium and its system libraries ----
FROM mcr.microsoft.com/playwright/python:v1.62.0-noble
ENV PYTHONUNBUFFERED=1 \
    UV_PYTHON=/usr/bin/python3 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    HANDS_HEADLESS=1 \
    HANDS_DATA_DIR=/data
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src/ src/
COPY policies/ policies/
COPY profiles/ profiles/
COPY artifacts/ artifacts/
COPY evidence/runs/ evidence/runs/
RUN uv sync --frozen --no-dev
COPY --from=web /web/dist web/dist

EXPOSE 8080
# Railway provides $PORT; `hands serve` reads it. /data should be a mounted volume.
CMD ["uv", "run", "--no-sync", "hands", "serve", "--host", "0.0.0.0"]
