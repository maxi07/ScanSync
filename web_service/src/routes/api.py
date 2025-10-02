from flask import Blueprint, Response, json, request, jsonify
from scansynclib.logging import logger
from scansynclib.openai_helper import test_key
from scansynclib.sqlite_wrapper import execute_query
from scansynclib.ollama_helper import test_ollama_server
from scansynclib.settings import settings
from scansynclib.settings_schema import FileNamingMethod, FileNamingSettings

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

    if client_id:
        settings.onedrive.client_id = client_id
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

    try:
        if api_key:
            # Test API key
            logger.debug("Testing OpenAI API key...")
            code, message = test_key(api_key)
            if code != 200:
                logger.warning(f"Failed to validate OpenAI key: {message}")
                return jsonify({'error': message}), code
            settings.file_naming = FileNamingSettings(
                openai_api_key=api_key,
                method=FileNamingMethod.OPENAI
            )
            return jsonify({'message': 'OpenAI API key saved successfully! ScanSync now uses ChatGPT for automatic file names.'}), 200
        else:
            return jsonify({'error': 'Invalid data'}), 400
    except Exception as e:
        err = f"Error saving OpenAI settings: {e}"
        logger.exception(err)
        return jsonify({'error': err}), 500


@api_bp.delete('/api/openai-settings')
def delete_openai_settings():
    logger.info("Received request to delete OpenAI settings")
    settings.file_naming = FileNamingSettings()
    return jsonify({'message': 'Settings deleted successfully!'}), 200


@api_bp.get('/api/status')
def get_status():
    # logger.info("Received request to get status")
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


@api_bp.post('/api/disable-file-naming')
def disable_file_naming():
    logger.info("Received request to disable file naming")
    try:
        was_disabled = settings.file_naming.method == FileNamingMethod.NONE
        settings.file_naming = FileNamingSettings()  # Reset to default settings
        if was_disabled:
            return "File naming is already disabled. No settings to delete.", 204
        else:
            logger.info("File naming disabled successfully")
            return "File naming disabled successfully. ScanSync will use default file names.", 200
    except Exception as e:
        logger.exception("Error disabling file naming")
        return f"Error disabling file naming: {e}", 500


@api_bp.post('/api/ollama-settings')
def save_ollama_settings():
    logger.info("Received request to save Ollama settings")
    if not request.is_json:
        logger.error("Invalid request format: Expected JSON")
        return jsonify({'error': 'Invalid request format'}), 400

    try:
        logger.debug(f"Request data: {request.json}")
        data = request.json
        http_scheme = data.get('ollama_server_scheme', 'http')
        server_url = data.get('ollama_server_address')
        server_port = data.get('ollama_server_port')
        model = data.get('ollama_model_select')

        if server_url and http_scheme and server_port and model:
            if server_url == 'localhost':
                logger.warning("User requested localhost as Ollama server, will replace with host.docker.internal")
                server_url = 'host.docker.internal'
            baseurl = f"{http_scheme}://{server_url}"
            success, message = test_ollama_server(baseurl, server_port, model)
            if not success:
                return jsonify({'error': message}), 500
            settings.file_naming = FileNamingSettings(
                ollama_server_url=baseurl,
                ollama_server_port=int(server_port),
                ollama_model=model,
                method=FileNamingMethod.OLLAMA
            )
            return jsonify({'message': 'Ollama settings saved successfully!'}), 200
        else:
            return jsonify({'error': 'Invalid data'}), 400
    except Exception as e:
        err = f"Error saving Ollama settings: {e}"
        logger.exception(err)
        return jsonify({'error': err}), 500


@api_bp.delete('/api/ollama-settings')
def delete_ollama_settings():
    logger.info("Received request to delete Ollama settings")
    settings.file_naming = FileNamingSettings()
    return jsonify({'message': 'Ollama settings deleted successfully!'}), 200


@api_bp.get('/api/file-naming-logs')
def file_naming_logs():
    """
    Route to display the file naming logs with pagination.
    Accepts 'page' and 'per_page' as URL query parameters.
    """

    try:
        logger.info("Requested file naming logs")
        logger.debug(f"Request args: {request.args}")

        # Get pagination parameters from URL
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        filter = request.args.get('filter', 'all').lower()
        offset = (page - 1) * per_page

        # Build WHERE clause based on filter
        where_clause = ""
        params = []
        if filter == "success":
            where_clause = "WHERE file_naming_jobs.success = 1"
        elif filter == "failed":
            where_clause = "WHERE file_naming_jobs.success = 0"

        # Get the total count for pagination info with filter
        count_query = f"SELECT COUNT(*) FROM file_naming_jobs {where_clause}"
        total_count = execute_query(count_query, tuple(params), return_scalar=True)
        logger.debug(f"Total file naming jobs count (filter={filter}): {total_count}")

        # Get the paginated entries from the file_naming_jobs table with filter
        logs_query = f"""
            SELECT file_naming_jobs.*, scanneddata.file_name
            FROM file_naming_jobs
            LEFT JOIN scanneddata ON file_naming_jobs.scanneddata_id = scanneddata.id
            {where_clause}
            ORDER BY file_naming_jobs.started DESC
            LIMIT ? OFFSET ?
        """
        logs = execute_query(
            logs_query,
            (*params, per_page, offset),
            fetchall=True
        )
        logger.debug(f"Retrieved file naming logs: {logs}")

        response_data = {
            "logs": logs,
            "page": page,
            "per_page": per_page,
            "total_count": total_count,
            "total_pages": (total_count + per_page - 1) // per_page
        }

        return Response(json.dumps(response_data, default=str), mimetype='application/json', status=200)
    except Exception as e:
        logger.exception(f"Error retrieving file naming logs: {e}")
        return Response(json.dumps({}), mimetype='application/json', status=500)


@api_bp.get('/api/delete-id/<int:job_id>')
def delete_id_from_db(job_id: int):
    """
    Route to delete a job ID from the database.
    """
    try:
        logger.info(f"Received request to delete job ID {job_id} from the database")
        query = "UPDATE scanneddata SET file_status = 'Deleted', status_code = -1 WHERE id = ?"
        res = execute_query(query, (job_id,))
        if res is None:
            logger.error(f"Failed to delete job ID {job_id} from the database")
            return jsonify({'error': f'Failed to delete job ID {job_id}'}), 500
        logger.info(f"Successfully deleted job ID {job_id} from the database")
        return jsonify({'message': f'Job ID {job_id} deleted successfully!'}), 200
    except Exception as e:
        err = f"Error deleting job ID {job_id}: {e}"
        logger.exception(err)
        return jsonify({'error': err}), 500
