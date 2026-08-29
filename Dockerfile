FROM ghcr.io/bessazs/docker-images/python:3.10-slim 

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN useradd -m -u 1000 appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser alembic.ini .
COPY --chown=appuser:appuser alembic ./alembic
COPY --chown=appuser:appuser scripts ./scripts

RUN mkdir -p /app/uploads/media && chown -R appuser:appuser /app/uploads

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')"

CMD ["gunicorn", "app.main:app", \
    "--workers", "3", \
    "--worker-class", "uvicorn.workers.UvicornWorker", \
    "--bind", "0.0.0.0:8000", \
    "--timeout", "120", \
    "--max-requests", "1000", \
    "--max-requests-jitter", "100", \
    "--access-logfile", "-", \
    "--error-logfile", "-", \
    "--log-level", "info"]

