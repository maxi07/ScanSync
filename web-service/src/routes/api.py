from flask import Blueprint, request, jsonify
from shared.logging import logger
from shared.onedrive_settings import onedrive_settings


api_bp = Blueprint('api', __name__)


@api_bp.route('/api/onedrive-settings', methods=['POST'])
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
