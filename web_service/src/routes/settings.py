from enum import Enum
from flask import Blueprint, redirect, render_template, request, url_for
from scansynclib.logging import logger
from scansynclib.onedrive_api import get_user_info, get_user_photo
from scansynclib.settings import settings
from scansynclib.settings_schema import FileNamingMethod
from scansynclib.settings import settings_manager

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
        client_id = settings.onedrive.client_id or ""
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
        res = settings.file_naming.openai_api_key
        if res:
            logger.debug("Found OpenAI key")
            openai_key = "x" * 40
    except Exception:
        logger.exception("Failed to retrieve OpenAI settings")
        openai_key = ""
        logger.info("No OpenAI key available")

    try:
        ollama_enabled = settings.file_naming.method == FileNamingMethod.OLLAMA
        if ollama_enabled:
            ollama_server_url = settings.file_naming.ollama_server_url
            if "host.docker.internal" in ollama_server_url:
                # Special case for Docker, use localhost instead
                ollama_server_url = "localhost"
                logger.warning("Ollama server URL is set to 'host.docker.internal', replacing with 'localhost' for Docker compatibility.")
            ollama_server_port = settings.file_naming.ollama_server_port
            ollama_model = settings.file_naming.ollama_model
            logger.debug(f"Ollama settings found: url={ollama_server_url}, port={ollama_server_port}, model={ollama_model}")
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


def flatten_settings(model, prefix=""):
    """
    Rekursive Funktion, die alle Einstellungen flach als Dict zurückgibt.
    Schlüssel sind z.B. "file_naming.method" und Werte die Feldwerte.
    """
    result = {}
    for field_name, value in model._model.model_fields.items():
        attr = getattr(model, field_name)
        full_key = f"{prefix}.{field_name}" if prefix else field_name
        # Ist Wert selbst ein BaseModel Proxy? Dann rekursiv tiefer
        if hasattr(attr, "_model"):  # Proxy-Erkennung
            result.update(flatten_settings(attr, full_key))
        else:
            result[full_key] = attr
    return result


@settings_bp.route("/settings/advanced", methods=["GET", "POST"])
def settings_view():
    if request.method == "POST":
        # Alle Felder durchgehen und updaten
        for key, value in request.form.items():
            # key ist z.B. "file_naming.method"
            parts = key.split(".")
            target = settings_manager.settings
            # Bis zum letzten Attribut navigieren
            for part in parts[:-1]:
                target = getattr(target, part)
            attr_name = parts[-1]

            # Typ ermitteln für passende Umwandlung
            current_value = getattr(target, attr_name)
            if isinstance(current_value, int):
                value = int(value)
            elif isinstance(current_value, list):
                value = [v.strip() for v in value.split(",")]
            elif isinstance(current_value, Enum):
                enum_cls = type(current_value)
                value = enum_cls(value)
            # Sonst string

            setattr(target, attr_name, value)

        return redirect(url_for("settings.settings_view"))

    # GET: Settings flach auslesen und an Template geben
    flat_settings = flatten_settings(settings_manager.settings)
    return render_template("settings-advanced.html", settings=flat_settings)
