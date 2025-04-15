from flask import Blueprint, render_template, request, jsonify
import shared.onedrive_smb_manager as onedrive_smb_manager
from shared.logging import logger

sync_bp = Blueprint('sync', __name__)


@sync_bp.route('/sync')
def sync():
    logger.info("Requested sync site")

    # Get all SMB shares from the database
    smb_shares = onedrive_smb_manager.get_all()
    return render_template('sync.html', smb_shares=smb_shares)


@sync_bp.post('/add_path_mapping')
def add_path_mapping():
    logger.info("Request to add path mapping")

    if not request.form:
        logger.error("No form data provided")
        return jsonify({'error': 'Invalid data'}), 400
    logger.debug(f"Request data: {request.form}")

    smb_name = request.form.get('smb_name')
    onedrive_path = request.form.get('remote_path')
    drive_id = request.form.get('drive_id')
    folder_id = request.form.get('folder_id')
    web_url = request.form.get('web_url')

    if not smb_name or not onedrive_path or not drive_id or not folder_id:
        logger.error("Missing required form data")
        return jsonify({'error': 'Missing required data'}), 400

    db_id = onedrive_smb_manager.add(smb_name, drive_id, folder_id, onedrive_path, web_url)
    if db_id == -1:
        logger.error("Failed to add SMB share to database")
        return jsonify({'error': 'Failed to add SMB share to database'}), 500
    logger.info(f"SMB share added to database with ID: {db_id}")
    return jsonify({'success': True, 'smb_id': db_id}), 200
