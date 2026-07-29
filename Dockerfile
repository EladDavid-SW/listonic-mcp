# Minimal image so registries like Glama can start the server and introspect its
# tools. The server boots WITHOUT credentials (tools report the missing login when
# called); provide them at runtime for real use:
#   docker run -i -e LISTONIC_EMAIL=you@example.com -e LISTONIC_PASSWORD=secret listonic-mcp
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir .
ENTRYPOINT ["listonic-mcp"]
