from flask import Blueprint, render_template
from shared.logging import logger
from shared.onedrive_settings import onedrive_settings
from shared.onedrive_api import get_user_info, get_user_photo

settings_bp = Blueprint('settings', __name__)


@settings_bp.route('/settings')
def index():
    logger.info("Requested settings site")

    client_id = ""
    client_secret = ""

    user_name = ""
    user_email = ""
    user_picture = ""

    try:
        client_id = onedrive_settings.client_id or ""
        if client_id:
            client_secret = "x" * 40
    except Exception:
        logger.exception("Failed to retrieve OneDrive settings")

    if client_id:
        user_info = get_user_info()
        if user_info:
            logger.info(f"User info: {user_info}")
            user_name = user_info.get("displayName", "Unknown Name")
            user_email = user_info.get("mail", "Unknown email")
            user_picture = get_user_photo()
        else:
            logger.info("No user info available")

    return render_template('settings.html',
                           client_id=client_id,
                           client_secret=client_secret,
                           user_name=user_name,
                           user_email=user_email,
                           user_picture=user_picture,)
