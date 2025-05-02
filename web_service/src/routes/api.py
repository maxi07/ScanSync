from flask import Blueprint, request, jsonify
from scansynclib.logging import logger
from scansynclib.onedrive_settings import onedrive_settings
from scansynclib.openai_settings import openai_settings
from scansynclib.openai_helper import test_and_add_key
from scansynclib.sqlite_wrapper import execute_query

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
    hostname = data.get('hostname')

    if client_id and client_secret and hostname:
        onedrive_settings.client_id = client_id
        onedrive_settings.client_secret = client_secret
        onedrive_settings.redirect_uri = f"http://{hostname}:5001/getAToken"

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


@api_bp.get('/api/status')
def get_status():
    logger.info("Received request to get status")
    try:
        query = """
            SELECT *,
                (SELECT COUNT(*) FROM scanneddata WHERE status_code = 5) AS processed_pdfs,
                (SELECT COUNT(*) FROM scanneddata WHERE status_code BETWEEN 0 AND 4) AS processing_pdfs,
                (SELECT DATETIME(created) FROM scanneddata WHERE status_code < 5 ORDER BY created DESC LIMIT 1) AS latest_processing_timestamp,
                (SELECT DATETIME(modified) FROM scanneddata WHERE status_code = 5 ORDER BY modified DESC LIMIT 1) AS latest_completed_timestamp,
                (SELECT file_name FROM scanneddata ORDER BY created DESC LIMIT 1) AS latest_created_name,
                (SELECT status_code FROM scanneddata ORDER BY created DESC LIMIT 1) AS latest_created_status
            FROM scanneddata
            ORDER BY created DESC, id DESC
        """
        result = execute_query(query, fetchone=True)
        if result:
            response = {
                'processed_pdfs': result.get('processed_pdfs', 0),
                'processing_pdfs': result.get('processing_pdfs', 0),
                'latest_processing_timestamp': result.get('latest_processing_timestamp', None),
                'latest_completed_timestamp': result.get('latest_completed_timestamp', None),
                'latest_created_name': result.get('latest_created_name', None),
                'latest_created_status': result.get('latest_created_status', None)
            }
            return jsonify(response), 200
        else:
            return jsonify({'error': 'No data found'}), 404
    except Exception as e:
        err = f"Error fetching status: {e}"
        logger.exception(err)
        return jsonify({'error': err}), 500
