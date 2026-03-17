FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir "kanban-mcp[mysql]" gunicorn

COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

EXPOSE 5000

ENTRYPOINT ["./entrypoint.sh"]
