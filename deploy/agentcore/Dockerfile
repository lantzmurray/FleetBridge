FROM python:3.12.8-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

RUN groupadd --system --gid 1001 appgroup \
    && useradd --system --uid 1001 --gid appgroup --home-dir /app appuser

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY deploy/agentcore/agentcore_worker.py ./agentcore_worker.py

RUN python -m pip install --no-cache-dir --upgrade "pip==25.2" \
    && python -m pip install --no-cache-dir .

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/ping', timeout=2)" || exit 1

CMD ["uvicorn", "agentcore_worker:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
