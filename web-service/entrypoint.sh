#!/bin/sh

echo "Fixing permissions for mounted volumes..."
chown -R appuser /app/data /mnt/scans /app/src/static/images/pdfpreview

echo "Starting app as appuser..."
exec su appuser -c "gunicorn --bind 0.0.0.0:5001 src.main:app"