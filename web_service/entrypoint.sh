#!/bin/sh

python - <<'PY'
import json
import os
from pathlib import Path

config = json.loads(Path(os.environ['CONFIG_PATH']).read_text())
os.makedirs(os.path.join(config['smb']['path'], config['failedDir']), exist_ok=True)
PY
echo "Fixing permissions for mounted volumes..."
chown -R appuser /app/data /mnt/scans /app/src/static/images/pdfpreview

cd /app
export FLASK_APP=src.main:app

# Use `exec` so the final process becomes PID 1 and receives SIGTERM directly
# from Docker. This enables graceful shutdown (Gunicorn workers finish in-flight
# requests, dev server stops cleanly) instead of being killed by a dying `su`
# session.
if [ "$FLASK_ENV" = "development" ]; then
    echo "Starting Flask development server..."
    exec gosu appuser flask run --host=0.0.0.0 --port=5001 --reload --debug
else
    echo "Starting app with Gunicorn..."
    exec gosu appuser gunicorn --worker-class gevent --bind 0.0.0.0:5001 --graceful-timeout 5 src.main:app
fi