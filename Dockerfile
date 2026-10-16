FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/ogu83/matchday-companion"
LABEL org.opencontainers.image.title="Matchday Companion"
LABEL org.opencontainers.image.description="Live multi-agent matchday companion for broadcast football with fact-checking and low-latency voice"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8010

WORKDIR /app

RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g appuser -s /bin/sh -m appuser

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY frontend ./frontend

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, os; port=os.environ.get('PORT', '8010'); res=urllib.request.urlopen(f'http://localhost:{port}/api/health'); exit(0 if res.status == 200 else 1)"

CMD ["sh", "-c", "uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8010}"]
