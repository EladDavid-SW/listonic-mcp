# Production image for remote hosting (Render Free, 512 MB RAM).
#
# Defaults to the Streamable HTTP transport on $PORT (Render sets it; 8000 if
# unset) with MCP at /mcp and a public GET /health. Required at runtime:
#   MCP_AUTH_TOKEN, LISTONIC_EMAIL, LISTONIC_PASSWORD  (see .env.example)
#
#   docker build -t listonic-mcp .
#   docker run --rm -p 8000:8000 --env-file .env listonic-mcp
#
# Local stdio use is still possible with the same image:
#   docker run -i --rm -e MCP_TRANSPORT=stdio --env-file .env listonic-mcp
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MCP_TRANSPORT=http \
    HOST=0.0.0.0

WORKDIR /app
COPY pyproject.toml README.md listonic_mcp.py server.py LICENSE ./
RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 app

USER app
EXPOSE 8000
ENTRYPOINT ["listonic-mcp"]
