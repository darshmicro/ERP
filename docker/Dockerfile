# Multi-stage build: SPA + API. (Written for Linux containers; not executed in the Phase 1 build environment.)
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends curl gnupg unixodbc-dev gcc \
 && curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/ms.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/ms.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql.list \
 && apt-get update && ACCEPT_EULA=Y apt-get install -y msodbcsql18 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt backend/
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend backend
COPY database database
COPY scripts scripts
COPY --from=web /web/dist frontend/dist
RUN useradd -r -u 10001 merp && mkdir -p /data/documents /data/logs && chown -R merp /data
USER merp
ENV PYTHONPATH=/app/backend MERP_FILE_STORAGE_PATH=/data/documents MERP_LOG_DIR=/data/logs
EXPOSE 8000
CMD ["gunicorn", "app.main:create_app()", "-k", "uvicorn.workers.UvicornWorker", "-w", "4", "-b", "0.0.0.0:8000", "--chdir", "/app/backend"]
