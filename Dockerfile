# syntax=docker/dockerfile:1
# KALIMA — one container: the Python API and the built React bundle on a single
# origin. TLS terminates at the reverse proxy in front of this (deploy/Caddyfile);
# never publish this port directly to the internet.

# ---------------------------------------------------------------------------
# Stage 1 — build the React UI
# ---------------------------------------------------------------------------
FROM node:22-bookworm-slim AS ui
WORKDIR /ui
# Copy manifests first so a source-only change does not reinstall node_modules.
COPY frontend/ui/package.json frontend/ui/package-lock.json* ./
RUN npm ci 2>/dev/null || npm install
COPY frontend/ui/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime
# The playwright wheel expects its browsers at a shared path so the non-root
# runtime user can read the copies installed as root below.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    KALIMA_ENV=production \
    KALIMA_HOST=0.0.0.0 \
    KALIMA_PORT=8765 \
    KALIMA_UI_DIST=/app/frontend/ui/dist
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
 && playwright install --with-deps chromium
COPY app ./app
COPY pyproject.toml readme.md LICENSE ./
# Served verbatim by app/web.py (KALIMA_UI_DIST points here) — no second server.
COPY --from=ui /ui/dist ./frontend/ui/dist
# Runtime state (data/, temp/, output/) lives on volumes; create + own them.
RUN useradd --create-home --uid 10001 kalima \
 && mkdir -p /app/data /app/temp /app/output /app/config \
 && chown -R kalima:kalima /app
USER kalima
EXPOSE 8765
VOLUME ["/app/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/api/version', timeout=3).status == 200 else 1)"
CMD ["python", "-m", "app.web"]
