from flask import Blueprint, render_template
from scansynclib.logging import logger
from scansynclib.onedrive_settings import onedrive_settings
from scansynclib.ollama_settings import ollama_settings
from scansynclib.onedrive_api import get_user_info, get_user_photo
from scansynclib.openai_settings import openai_settings

settings_bp = Blueprint('settings', __name__)


@settings_bp.route('/settings')
def index():
    logger.info("Requested settings site")

    client_id = ""

    user_name = ""
    user_email = ""
    user_picture = ""
    openai_key = ""

    ollama_server_url = ""
    ollama_server_port = ""
    ollama_model = ""
    ollama_enabled = False

    try:
        client_id = onedrive_settings.client_id or ""
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

    try:
        ollama_enabled = bool(ollama_settings.server_url and ollama_settings.server_port and ollama_settings.model)
        if ollama_enabled:
            ollama_server_url = ollama_settings.server_url
            if "host.docker.internal" in ollama_server_url:
                # Special case for Docker, use localhost instead
                ollama_server_url = "localhost"
                logger.warning("Ollama server URL is set to 'host.docker.internal', replacing with 'localhost' for Docker compatibility.")
            ollama_server_port = ollama_settings.server_port
            ollama_model = ollama_settings.model
            logger.debug("Ollama settings found")
        else:
            logger.info("Ollama settings not configured")
    except Exception:
        logger.exception("Failed to retrieve Ollama settings")
        ollama_enabled = False

    if ollama_enabled and openai_key:
        logger.warning("Both OpenAI and Ollama are enabled, this is not recommended. Please disable one of them in the settings.")

    return render_template('settings.html',
                           client_id=client_id,
                           user_name=user_name,
                           user_email=user_email,
                           user_picture=user_picture,
                           openai_key=openai_key,
                           ollama_enabled=ollama_enabled,
                           ollama_server_url=ollama_server_url,
                           ollama_server_port=ollama_server_port,
                           ollama_model=ollama_model)
