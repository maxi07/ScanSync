#!/bin/sh

echo "Fixing permissions for mounted volumes..."
chown -R appuser /app/data /mnt/scans /app/src/static/images/pdfpreview

if [ "$FLASK_ENV" = "development" ]; then
    echo "Starting Flask development server..."
    export FLASK_APP=src.main:app
    exec su appuser -c "flask run --host=0.0.0.0 --port=5001 --reload --debug"
else
    echo "Starting app with Gunicorn..."
    exec su appuser -c "gunicorn --worker-class gevent --bind 0.0.0.0:5001 src.main:app"
fi