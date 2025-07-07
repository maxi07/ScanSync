from enum import Enum
import json
from flask import Blueprint, Response, redirect, render_template, request, url_for
import requests
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


@settings_bp.get("/settings/ollama/version")
def get_ollama_version():
    """
    Endpoint to get the version of the Ollama server.
    """
    logger.info("Requested Ollama version")
    logger.debug(f"Request args: {request.args}")
    url = request.args.get("url")
    port = request.args.get("port")
    scheme = request.args.get("scheme", "http")
    if not url or not port or not scheme:
        logger.error("Missing required 'url' or 'port' or 'scheme' parameter")
        return Response("Missing required 'url' or 'port' or 'scheme' parameter", status=400, mimetype='text/plain')

    if url == "localhost":
        logger.warning("User requested localhost as Ollama server, will replace with host.docker.internal")
        url = "host.docker.internal"
    logger.debug(f"Connecting to Ollama server at {scheme}://{url}:{port}/api/version")
    try:
        full_url = f"{scheme}://{url}:{port}/api/version"
        response = requests.get(full_url, timeout=10)
        if response.status_code == 200:
            logger.debug(f"Ollama server version response: {response.json()}")
            return Response(json.dumps(response.json()), status=200, mimetype='application/json')
        else:
            logger.error(f"Ollama server returned an error: {response.status_code} - {response.text}")
            return Response(f"Error: {response.status_code} - {response.text}", status=response.status_code, mimetype='text/plain')
    except requests.RequestException as e:
        if isinstance(e, requests.ConnectionError):
            logger.error("Connection error, possibly Ollama server is not running or URL is incorrect.")
            return Response(f"Connection error: {str(e)}", status=502, mimetype='text/plain')
        elif isinstance(e, requests.Timeout):
            logger.error("Timeout error, Ollama server might be slow to respond or not reachable.")
            return Response(f"Timeout error: {str(e)}", status=504, mimetype='text/plain')
        elif isinstance(e, requests.HTTPError):
            logger.error(f"HTTP error occurred: {e.response.status_code} - {e.response.text}")
            return Response(f"HTTP error: {e.response.status_code} - {e.response.text}", status=e.response.status_code, mimetype='text/plain')
        else:
            logger.error(f"An unexpected error occurred: {str(e)}")
            return Response(f"Unexpected error: {str(e)}", status=500, mimetype='text/plain')
    except Exception as e:
        logger.exception(f"Unexpected error while getting Ollama version: {str(e)}")
        return Response(f"Unexpected error while getting Ollama version: {str(e)}", status=500, mimetype='text/plain')


@settings_bp.get("/settings/ollama/models")
def get_ollama_models():
    """
    Endpoint to get the list of models available on the Ollama server.
    """
    logger.info("Requested Ollama models")
    logger.debug(f"Request args: {request.args}")
    url = request.args.get("url")
    port = request.args.get("port")
    scheme = request.args.get("scheme", "http")
    if not url or not port or not scheme:
        logger.error("Missing required 'url' or 'port' or 'scheme' parameter")
        return Response("Missing required 'url' or 'port' or 'scheme' parameter", status=400, mimetype='text/plain')

    if url == "localhost":
        logger.warning("User requested localhost as Ollama server, will replace with host.docker.internal")
        url = "host.docker.internal"
    logger.debug(f"Connecting to Ollama server at {scheme}://{url}:{port}/api/tags")
    try:
        full_url = f"{scheme}://{url}:{port}/api/tags"
        response = requests.get(full_url, timeout=10)
        logger.debug(f"Ollama server models response: {response.status_code} - {response.text}")
        if response.status_code == 200:
            return Response(json.dumps(response.json()), status=200, mimetype='application/json')
        else:
            logger.error(f"Ollama server returned an error: {response.status_code} - {response.text}")
            return Response(f"Error: {response.status_code} - {response.text}", status=response.status_code, mimetype='text/plain')
    except requests.RequestException as e:
        logger.error(f"Error connecting to Ollama server: {str(e)}")
        return Response(f"Error connecting to Ollama server: {str(e)}", status=500, mimetype='text/plain')
    except Exception as e:
        logger.exception(f"Unexpected error while getting Ollama models: {str(e)}")
        return Response(f"Unexpected error while getting Ollama models: {str(e)}", status=500, mimetype='text/plain')
