# Build from the REPO ROOT, not from this directory: the image needs shared/contracts and
# services/agents as well.
#   docker build -f services/gateway/Dockerfile -t trustshield-gateway .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

# Third-party dependencies first, so the layer is reused when only our source changes.
COPY services/gateway/requirements.txt /app/services/gateway/requirements.txt
COPY services/agents/requirements.txt /app/services/agents/requirements.txt
RUN pip install --no-cache-dir --prefer-binary \
      -r /app/services/gateway/requirements.txt \
      -r /app/services/agents/requirements.txt

# The two local packages. --no-deps: everything they need is already installed above.
COPY shared/contracts /app/shared/contracts
COPY services/agents /app/services/agents
RUN pip install --no-cache-dir --no-deps -e /app/shared/contracts -e /app/services/agents

COPY services/gateway /app/services/gateway

# Run as a non-root user; Cloud Run does not require it but it costs nothing.
RUN useradd --create-home --uid 1001 trustshield && chown -R trustshield /app
USER trustshield

WORKDIR /app/services/gateway
EXPOSE 8080

# Cloud Run injects $PORT; 8080 is the local default.
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT}
