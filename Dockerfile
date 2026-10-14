# The drawspec MCP server, for registries that build a server to run it (Glama).
# It speaks MCP over stdio: `docker run -i --rm drawspec-mcp`.
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY schema ./schema
RUN pip install --no-cache-dir '.[mcp]'

CMD ["drawspec-mcp"]
