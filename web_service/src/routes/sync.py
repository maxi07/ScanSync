from datetime import datetime
import os
from flask import Blueprint, render_template, request, jsonify, send_file
import scansynclib.onedrive_smb_manager as onedrive_smb_manager
from scansynclib.logging import logger
import math
from scansynclib.sqlite_wrapper import execute_query
from scansynclib.config import config
from scansynclib.helpers import validate_smb_filename, SMB_TAG_COLORS
import io
import csv

sync_bp = Blueprint('sync', __name__)


@sync_bp.route('/sync')
def sync():
    logger.info("Requested sync site")

    # Read URL args
    order_by = request.args.get('order', 'created ASC')

    # Get all SMB shares from the database
    smb_shares = onedrive_smb_manager.get_all(order=order_by)

    # Get all failed uploads
    try:
        page_failed_pdfs = request.args.get('page_failed_pdfs', 1, type=int)  # Get pageination from url args
        failed_query_count = r"SELECT COUNT(*) AS count FROM scanneddata WHERE status_code < 0 AND LOWER(file_status) NOT LIKE '%deleted%'"
        total_entries = execute_query(failed_query_count, fetchone=True).get('count', 0)
        entries_per_page = 20
        total_pages_failed_pdfs = math.ceil(total_entries / entries_per_page)
        offset = (page_failed_pdfs - 1) * entries_per_page
        failed_pdfs = execute_query(
            'SELECT *, DATETIME(created) AS local_created, DATETIME(modified) AS local_modified FROM scanneddata '
            'WHERE status_code < 0 AND LOWER(file_status) NOT LIKE "%deleted%" '
            'ORDER BY created DESC '
            'LIMIT ? OFFSET ?',
            (entries_per_page, offset), fetchall=True)
    except Exception:
        logger.exception("Failed retrieving failed pdfs.")
        failed_pdfs = []

    for smb_connection in smb_shares:
        try:
            datetime_created = datetime.strptime(smb_connection['created'], "%Y-%m-%d %H:%M:%S")
            smb_connection['created'] = datetime_created.strftime('%d.%m.%Y %H:%M')
        except Exception as ex:
            logger.exception(f"Failed setting datetime for {smb_connection['id']}. {ex}")
    return render_template('sync.html',
                           smb_shares=smb_shares,
                           failed_pdfs=failed_pdfs,
                           total_pages_failed_pdfs=total_pages_failed_pdfs,
                           page_failed_pdfs=page_failed_pdfs,
                           smb_tag_colors=SMB_TAG_COLORS,)


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

    # Validate SMB name
    smb_name = validate_smb_filename(smb_name)

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


@sync_bp.get("/failedpdf")
def downloadFailedPDF():
    """Downloads a failed PDF file for the given id from the failed PDF directory.
    Returns the file if it exists, handles invalid ids and other errors.

    Returns:
        File if it exists or error message
    """
    try:
        download_id = int(request.args.get('download_id'))
        if download_id is None or download_id <= 0:
            logger.warning(f"Downloading failed PDF with id {download_id}, invalid id")
            return "Invalid download id", 400
        logger.info(f"Downloading failed PDF with id {download_id}")

        # Get name in os from sql db
        item_name = execute_query('SELECT file_name FROM scanneddata WHERE id = ?', (download_id,), fetchone=True).get('file_name')

        # Check if file exists
        file_path = os.path.join(config.get("smb.path"), config.get("failedDir"), item_name)
        logger.debug(f"Checking if failed file exists: {file_path}")
        if not os.path.isfile(file_path):
            logger.warning(f"Downloading failed PDF with id {download_id}, file does not exist")
            return "File does not exist", 404
        else:
            logger.info(f"Downloading failed PDF with id {download_id}, file exists")
            return send_file(file_path, as_attachment=True)
    except ValueError:
        logger.warning(f"Downloading failed PDF with id {download_id}, invalid id")
        return "Invalid download id", 400
    except Exception as ex:
        logger.exception(f"Failed downloading PDF: {ex}")
        return "Failed downloading PDF", 500


@sync_bp.delete("/failedpdf")
def deleteFailedPDF():
    """Deletes a failed PDF file from the failed PDF directory.

    Expects a JSON request with the ID of the failed PDF to delete.
    Looks up the file name for the ID, deletes the file,
    and updates the database.

    Returns a success or error message.
    """
    try:
        json_data = request.get_json()
        if not json_data:
            logger.warning("No data received!")
            return "No data received!", 400
        else:
            logger.info(f"Received data to delete: {json_data}")

            if not json_data.get('id'):
                logger.warning("No ID provided!")
                return "No ID provided!", 400

            item_name = execute_query('SELECT file_name FROM scanneddata WHERE id = ?', (json_data['id'],), fetchone=True).get('file_name')
            file_path = os.path.join(config.get("smb.path"), config.get("failedDir"), item_name)
            logger.info(f"Removing {file_path}")
            if os.path.exists(file_path):
                os.remove(file_path)
            else:
                logger.warning(f"File {item_name} does not exist in failed directory!")

            # Update the database
            delete_query = 'UPDATE scanneddata SET file_status = ?, modified = CURRENT_TIMESTAMP WHERE id = ?'
            db = execute_query(delete_query, ("Deleted", json_data['id']))
            if db is None:
                logger.error("Failed to update database")
                return "Failed to update database", 500
            logger.info(f"Updated database for {item_name}")
            return f"Success deleting {item_name}", 200
    except Exception as ex:
        logger.exception(f"Error deleting file: {ex}")
        return "Failed deleting requested item", 500


@sync_bp.get("/sync/export")
def export_sync_data():
    """Exports the sync data as a CSV file."""
    try:
        logger.info("Exporting sync data to CSV")
        smb_shares = onedrive_smb_manager.get_all(order='created ASC')

        str_io = io.StringIO()
        writer = csv.writer(str_io)
        writer.writerow(['id', 'smb_name', 'onedrive_path', 'drive_id', 'folder_id', 'web_url', 'created'])

        errors = 0
        logger.debug(f"Exporting {len(smb_shares)} SMB shares to CSV")
        for smb in smb_shares:
            try:
                writer.writerow([
                    smb['id'],
                    smb['smb_name'],
                    smb['onedrive_path'],
                    smb['drive_id'],
                    smb['folder_id'],
                    smb['web_url'],
                    smb['created']
                ])
            except Exception as ex:
                logger.exception(f"Failed writing SMB share {smb['id']} to CSV: {ex}")
                errors += 1

        if errors > 0:
            logger.warning(f"Exported sync data with {errors} errors.")
        else:
            logger.info("Exported sync data successfully without errors.")

        # String in Bytes umwandeln
        byte_io = io.BytesIO()
        byte_io.write(str_io.getvalue().encode('utf-8'))
        byte_io.seek(0)

        return send_file(byte_io, mimetype='text/csv', as_attachment=True, download_name='sync_data.csv')

    except Exception as ex:
        logger.exception(f"Failed exporting sync data: {ex}")
        return "Failed exporting sync data", 500


@sync_bp.get('/get-path-mapping-details/<int:smb_id>')
def get_path_mapping_details(smb_id):
    """Get details of a specific path mapping for editing purposes."""
    logger.info(f"Request to get path mapping details for ID: {smb_id}")

    try:
        # Get the SMB share details
        smb_share = onedrive_smb_manager.get_by_id(smb_id)
        if not smb_share:
            logger.error(f"SMB share with ID {smb_id} not found")
            return jsonify({'error': 'Path mapping not found'}), 404

        # Return the relevant details for editing
        response_data = {
            'smb_name': smb_share.get('smb_name'),
            'onedrive_path': smb_share.get('onedrive_path'),
            'folder_id': smb_share.get('folder_id'),
            'drive_id': smb_share.get('drive_id'),
            'web_url': smb_share.get('web_url')
        }

        logger.debug(f"Returning path mapping details: {response_data}")
        return jsonify(response_data), 200

    except Exception as ex:
        logger.exception(f"Failed to get path mapping details for ID {smb_id}: {ex}")
        return jsonify({'error': 'Failed to get path mapping details'}), 500
