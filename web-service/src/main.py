import os
from flask import Flask
import sys
sys.path.append('/app/src')
from shared.logging import logger
from routes.dashboard import dashboard_bp
from routes.sync import sync_bp
from routes.settings import settings_bp
from routes.api import api_bp
from routes.onedrive import onedrive_bp
from shared.sqlite_wrapper import execute_query
from shared.config import config


logger.info("Starting web service...")

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.register_blueprint(dashboard_bp)
app.register_blueprint(sync_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(api_bp)
app.register_blueprint(onedrive_bp)


@app.context_processor
def inject_config():
    """Inject config values into templates."""
    # Count failed documents
    try:
        failed_document_count = execute_query(r"SELECT COUNT(*) AS count FROM scanneddata WHERE LOWER(file_status) LIKE '%failed%'", fetchone=True).get('count', 0)
    except Exception:
        logger.exception("Failed counting failed documents.")
        failed_document_count = 0

    return dict(
        failed_document_count=failed_document_count,
        version=config.get("version", "Unknown"),
    )


if __name__ == '__main__':
    app.run(debug=True, port=5001)
