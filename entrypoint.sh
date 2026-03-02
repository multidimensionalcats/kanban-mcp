#!/bin/bash
set -e

echo "Waiting for MySQL..."
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
        echo "ERROR: Could not connect to MySQL after 30 attempts."
        exit 1
    fi
    echo "  MySQL not ready, retrying in 2s... ($retries attempts left)"
    sleep 2
done
echo "MySQL is ready."

echo "Running database migrations..."
python -c "
import os
from kanban_mcp.setup import auto_migrate
auto_migrate({
    'host': os.environ.get('KANBAN_DB_HOST', 'localhost'),
    'user': os.environ['KANBAN_DB_USER'],
    'password': os.environ['KANBAN_DB_PASSWORD'],
    'database': os.environ['KANBAN_DB_NAME'],
})
"

exec gunicorn -b 0.0.0.0:5000 kanban_mcp.web:app
