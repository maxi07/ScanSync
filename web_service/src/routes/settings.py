from flask import Blueprint, render_template
from scansynclib.logging import logger
from scansynclib.onedrive_settings import onedrive_settings
from scansynclib.onedrive_api import get_user_info, get_user_photo
from scansynclib.openai_settings import openai_settings

settings_bp = Blueprint('settings', __name__)


@settings_bp.route('/settings')
def index():
    logger.info("Requested settings site")

    client_id = ""
    client_secret = ""

    user_name = ""
    user_email = ""
    user_picture = ""
    openai_key = ""

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

    try:
        res = openai_settings.api_key
        if res:
            logger.debug("Found OpenAI key")
            openai_key = "x" * 40
    except Exception:
        logger.exception("Failed to retrieve OpenAI settings")
        openai_key = ""
        logger.info("No OpenAI key available")

    return render_template('settings.html',
                           client_id=client_id,
                           client_secret=client_secret,
                           user_name=user_name,
                           user_email=user_email,
                           user_picture=user_picture,
                           openai_key=openai_key,)
