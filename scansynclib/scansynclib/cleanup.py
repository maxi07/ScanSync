import os
from scansynclib.logging import logger
from scansynclib.config import config
from scansynclib.ProcessItem import ProcessStatus, StatusProgressBar
from scansynclib.sqlite_wrapper import execute_query


def _move_leftover_to_failed(file_name: str, local_dir: str, failed_name: str | None = None):
    """Move a leftover source file into the failed directory and drop its OCR file.

    The original (non OCR) scan is moved into the failed directory so it stays
    recoverable from the web UI, while any leftover ``*_OCR.pdf`` working file is
    removed. Missing files are tolerated and only logged.

    Args:
        file_name (str): The original base file name of the scan.
        local_dir (str): The SMB share sub directory the scan lives in.
        failed_name (str): The visible file name used by the download endpoint.
    """
    if not file_name:
        logger.warning("Cannot move leftover file to failed directory: missing file name.")
        return

    smb_path = config.get("smb.path")
    failed_dir = os.path.join(smb_path, config.get("failedDir"))
    moved_name = None

    if not os.path.exists(failed_dir):
        try:
            os.makedirs(failed_dir)
        except Exception:
            logger.exception(f"Failed to create failed directory {failed_dir}")
            return

    if local_dir:
        source_path = os.path.join(smb_path, local_dir, file_name)
        if os.path.exists(source_path):
            try:
                destination_name = failed_name or file_name
                dest_path = os.path.join(failed_dir, destination_name)
                base, ext = os.path.splitext(destination_name)
                suffix = 0
                while os.path.exists(dest_path):
                    suffix += 1
                    dest_path = os.path.join(failed_dir, f"{base}_{local_dir}_{suffix}{ext}")
                os.rename(source_path, dest_path)
                moved_name = os.path.basename(dest_path)
                logger.info(f"Moved leftover file {source_path} to failed directory {dest_path}")
            except Exception:
                logger.exception(f"Failed to move leftover file {source_path} to failed directory {failed_dir}")
        else:
            logger.debug(f"Leftover file {source_path} not found, nothing to move.")

        # Remove leftover OCR working file if present
        ocr_file = os.path.join(smb_path, local_dir, os.path.splitext(file_name)[0] + "_OCR.pdf")
        if os.path.exists(ocr_file):
            try:
                os.remove(ocr_file)
                logger.info(f"Removed leftover OCR file {ocr_file}")
            except Exception:
                logger.exception(f"Failed to remove leftover OCR file {ocr_file}")
    else:
        logger.warning(f"No source directory recorded for {file_name}, cannot move it to failed directory.")
    return moved_name


def cleanup_dangling_documents():
    """Mark documents left in an in-progress state as failed on startup.

    When the services (re)start after a crash or redeploy, any document that was
    still being processed is stuck in a pending/processing state and will never
    finish on its own. To make sure a scan is never silently lost, such documents
    are marked as failed and their leftover source files are moved to the failed
    directory so they remain recoverable from the web UI.
    """
    pending = execute_query(
        "SELECT id, file_name, source_file_name, local_filepath FROM scanneddata WHERE status_code BETWEEN 0 AND 4",
        fetchall=True,
    )
    if pending is None:
        logger.error("Startup cleanup: failed querying dangling documents (database query returned None).")
        return
    pending = pending or []

    if not pending:
        logger.info("Startup cleanup: no dangling documents found.")
        return

    logger.warning(f"Startup cleanup: found {len(pending)} dangling document(s), marking as failed.")
    for row in pending:
        doc_id = row.get("id")
        file_name = row.get("file_name")
        source_name = row.get("source_file_name") or file_name
        local_dir = row.get("local_filepath")
        recovered_name = None
        try:
            recovered_name = _move_leftover_to_failed(source_name, local_dir, failed_name=file_name)
        except Exception:
            logger.exception(f"Failed moving leftover file for document id {doc_id} to failed directory.")

        try:
            execute_query(
                "UPDATE scanneddata SET file_status = ?, status_code = ?, file_name = ?, modified = DATETIME('now', 'localtime') WHERE id = ?",
                (ProcessStatus.FAILED.value, StatusProgressBar.get_progress(ProcessStatus.FAILED), recovered_name or file_name, doc_id),
            )
            logger.info(f"Startup cleanup: marked document id {doc_id} ({file_name}) as failed.")
        except Exception:
            logger.exception(f"Failed marking document id {doc_id} as failed during startup cleanup.")
