#!/bin/sh
set -e

echo "==> Running migrations..."
python manage.py migrate --noinput

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

echo "==> Starting gunicorn..."
# Default 1 worker — small VPS / DO droplets often OOM with 3 Django workers
exec gunicorn core.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-1}" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
