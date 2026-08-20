FROM python:3.12-slim

WORKDIR /app

# ffmpeg: 동영상 썸네일(대표 프레임) 생성 및 ffprobe 메타(재생시간 등) 추출
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

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
