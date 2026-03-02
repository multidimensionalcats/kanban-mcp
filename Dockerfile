FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml .
COPY kanban_mcp/ kanban_mcp/
RUN pip install --no-cache-dir .

EXPOSE 5000

CMD ["kanban-web", "--host", "0.0.0.0"]
