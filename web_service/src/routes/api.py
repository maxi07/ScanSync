from flask import Blueprint, request, jsonify
from shared.logging import logger
from shared.onedrive_settings import onedrive_settings
from shared.openai_settings import openai_settings
from shared.openai_helper import test_and_add_key


api_bp = Blueprint('api', __name__)


@api_bp.post('/api/onedrive-settings')
def save_onedrive_settings():
    logger.info("Received request to save OneDrive settings")
    if not request.is_json:
        logger.error("Invalid request format: Expected JSON")
        return jsonify({'error': 'Invalid request format'}), 400

    logger.debug(f"Request data: {request.json}")
    data = request.json
    client_id = data.get('clientID')
    client_secret = data.get('clientSecret')

    if client_id and client_secret:
        onedrive_settings.client_id = client_id
        onedrive_settings.client_secret = client_secret
        onedrive_settings.save()
        return jsonify({'message': 'Settings saved successfully!'}), 200
    else:
        return jsonify({'error': 'Invalid data'}), 400


@api_bp.post('/api/openai-settings')
def save_openai_settings():
    logger.info("Received request to save OpenAI settings.")
    if not request.is_json:
        logger.error("Invalid request format: Expected JSON")
        return jsonify({'error': 'Invalid request format'}), 400

    logger.debug(f"Request data: {request.json}")
    data = request.json
    api_key = data.get('openai_key')

    if api_key:
        # Test API key
        logger.debug("Testing OpenAI API key...")
        code, message = test_and_add_key(api_key)
        if code != 200:
            logger.warning(f"Failed to validate OpenAI key: {message}")
            return jsonify({'error': message}), code
        return jsonify({'message': 'OpenAI API key saved successfully! ScanSync now uses ChatGPT for automatic file names.'}), 200
    else:
        return jsonify({'error': 'Invalid data'}), 400


@api_bp.delete('/api/openai-settings')
def delete_openai_settings():
    logger.info("Received request to delete OpenAI settings")
    res = openai_settings.delete()
    if res:
        return jsonify({'message': 'Settings deleted successfully!'}), 200
    else:
        return jsonify({'error': 'Failed to delete settings'}), 500
