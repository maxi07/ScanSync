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


@sync_bp.post('/add-path-mapping')
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
    old_smb_id = request.form.get('old_smb_id', -1)
    if old_smb_id == '' or old_smb_id is None:
        old_smb_id = -1
    else:
        old_smb_id = int(old_smb_id)

    if not smb_name or not onedrive_path or not drive_id or not folder_id:
        logger.error("Missing required form data")
        return jsonify({'error': 'Missing required data'}), 400

    if old_smb_id != -1:
        logger.debug(f"Editing existing SMB share with ID {old_smb_id}")
        success = onedrive_smb_manager.edit(old_smb_id, smb_name, drive_id, folder_id, onedrive_path, web_url)
        if not success:
            logger.error("Failed to edit SMB share in database")
            return jsonify({'error': 'Failed to edit SMB share in database'}), 500
        logger.info(f"SMB share edited successfully with ID: {old_smb_id}")
        return jsonify({'success': True}), 200
    else:
        logger.debug("Adding new SMB share")
        db_id = onedrive_smb_manager.add(smb_name, drive_id, folder_id, onedrive_path, web_url)
        if db_id == -1:
            logger.error("Failed to add SMB share to database")
            return jsonify({'error': 'Failed to add SMB share to database'}), 500
        logger.info(f"SMB share added to database with ID: {db_id}")
    return jsonify({'success': True, 'smb_id': db_id}), 200


@sync_bp.post('/delete-path-mapping')
def delete_path_mapping():
    logger.info("Request to delete path mapping")

    if not request.json:
        logger.error("No JSON data provided")
        return jsonify({'error': 'Invalid data'}), 400
    logger.debug(f"Request data: {request.json}")

    smb_id = request.json.get('smb_id')
    if not smb_id:
        logger.error("Missing SMB ID")
        return jsonify({'error': 'Missing SMB ID'}), 400

    smb_id = int(smb_id)
    success = onedrive_smb_manager.delete(smb_id)
    if not success:
        logger.error("Failed to delete SMB share from database")
        return jsonify({'error': 'Failed to delete SMB share from database'}), 500

    logger.info(f"SMB share deleted successfully with ID: {smb_id}")
    return jsonify({'success': True}), 200