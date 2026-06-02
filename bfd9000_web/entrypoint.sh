#!/usr/bin/env bash
set -e

echo "Running database migrations..."
python manage.py migrate --noinput

echo "Starting gunicorn..."
exec gunicorn BFD9000.wsgi:application --bind 0.0.0.0:9000
