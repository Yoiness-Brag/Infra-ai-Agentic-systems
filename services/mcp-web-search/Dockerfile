FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=3001

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir "mcp>=1.2.0" "ddgs>=9.0.0" "httpx>=0.27.0"

COPY server.py ./

RUN useradd --create-home --uid 10001 appuser
USER 10001

EXPOSE 3001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import socket,sys; s=socket.socket(); s.settimeout(3); sys.exit(0 if s.connect_ex(('127.0.0.1',3001))==0 else 1)"

CMD ["python", "server.py"]
