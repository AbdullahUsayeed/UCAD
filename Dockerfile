# Optional containerized deploy: postgres + app behind this single image.
# Preferred path is deploy.sh (systemd + nginx). Use this if you prefer Docker.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/app

COPY server.py database.py ./
COPY deploy/requirements-server.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 7999
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS http://127.0.0.1:7999/health || exit 1

CMD ["gunicorn", "server:app", "--workers", "2", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:7999", "--access-logfile", "-", "--error-logfile", "-"]
