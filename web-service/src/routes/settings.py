from flask import Blueprint, render_template
from shared.logging import logger
from shared.onedrive_settings import onedrive_settings

settings_bp = Blueprint('settings', __name__)


@settings_bp.route('/settings')
def settings():
    logger.info("Requested settings site")

    client_id = ""
    client_secret = ""

    try:
        client_id = onedrive_settings.client_id or ""
        if client_id:
            client_secret = "x" * 40
    except Exception:
        logger.exception("Failed to retrieve OneDrive settings")

    return render_template('settings.html', client_id=client_id, client_secret=client_secret)
