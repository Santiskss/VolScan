# VolScan production image: builds the web app, then serves API + UI with uvicorn.
# docker build -t volscan . && docker run -p 8200:8200 --env-file .env volscan

FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PORT=8200 VOLSCAN_PUBLIC_DEMO=on VOLSCAN_AUTH=off
WORKDIR /app
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY volscan/ volscan/
RUN pip install --no-cache-dir -e ".[server]"
COPY data/ data/
COPY knowledge/ knowledge/
COPY --from=web /web/dist web/dist
# out/ holds caches and the audit trail; it must be writable
RUN useradd -m -u 1000 volscan && mkdir -p out && chown -R volscan /app
USER volscan
EXPOSE 8200
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/status',timeout=4)"
CMD ["sh", "-c", "uvicorn volscan.api.app:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
