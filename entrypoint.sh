#!/bin/bash
set -e

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
