FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && setpriv --version

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${APP_PORT:-8080}"]
