#!/bin/bash
set -e

echo "Waiting for database..."
retries=30
until python -c "
import os, mysql.connector
mysql.connector.connect(
    host=os.environ.get('KANBAN_DB_HOST', 'localhost'),
    user=os.environ['KANBAN_DB_USER'],
    password=os.environ['KANBAN_DB_PASSWORD'],
    database=os.environ['KANBAN_DB_NAME'],
).close()
" 2>/dev/null; do
    retries=$((retries - 1))
    if [ $retries -le 0 ]; then
        echo "ERROR: Could not connect to database after 30 attempts."
        exit 1
    fi
    echo "  Database not ready, retrying in 2s... ($retries attempts left)"
    sleep 2
done
echo "Database is ready."

echo "Running database migrations..."
python -c "
from kanban_mcp.db import create_backend
from kanban_mcp.setup import auto_migrate
backend = create_backend()
auto_migrate(backend)
"

exec gunicorn -b 0.0.0.0:5000 --worker-class gthread --threads 4 --preload kanban_mcp.web:app
