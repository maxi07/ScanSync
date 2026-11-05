from datetime import datetime
import pickle
from scansynclib.ProcessItem import ProcessItem, ProcessStatus
from scansynclib.logging import logger
from scansynclib.analytics import elapsed_ms, file_metadata, track
from scansynclib.helpers import consume, move_to_failed
from scansynclib.sqlite_wrapper import update_scanneddata_database, execute_query
from scansynclib.onedrive_api import upload_small
from scansynclib.config import config
import os
import time

logger.info("Starting Upload service...")
RABBITQUEUE = "upload_queue"


def finalize_sync_job(item: ProcessItem, error: str = None):
    """Persist the final state of a sync (upload) job to the sync_jobs table."""
    success = 1 if item.status == ProcessStatus.COMPLETED else 0
    execute_query(
        "UPDATE sync_jobs SET sync_status = ?, success = ?, error_description = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
        (item.status.name, success, error, item.sync_db_id)
    )


def callback(ch, method, properties, body):
    item = None
    try:
        item: ProcessItem = pickle.loads(body)
        if not isinstance(item, ProcessItem):
            track("queue.message_rejected", queue_name=RABBITQUEUE, reason="invalid_item")
            logger.warning("Received object, that is not of type ProcessItem. Skipping.")
            return
        logger.info(f"Received PDF for Upload: {item.filename}")
        item.sync_db_id = execute_query(
            "INSERT INTO sync_jobs (scanneddata_id, sync_status) VALUES (?, ?)",
            (item.db_id, ProcessStatus.SYNC.name),
            return_last_id=True
        )
        if not os.path.exists(item.ocr_file):
            track("upload.failed", item=item, reason="no_ocr_file")
            track("document.failed", item=item, reason="no_ocr_file")
            logger.error(f"OCR file does not exist for upload: {item.ocr_file}", extra={"analytics_handled": True})
            item.status = ProcessStatus.SYNC_FAILED
            update_scanneddata_database(item, {"file_status": item.status.value})
            finalize_sync_job(item, "OCR file does not exist for upload")
            move_to_failed(item)
        else:
            start_processing(item)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as error:
        track("upload.failed", item=item, error=error, operation="callback")
        track("document.failed", item=item, error=error, reason="upload_callback")
        logger.exception(f"Failed processing {body}.", extra={"analytics_handled": True})
        if item is not None and isinstance(item, ProcessItem):
            item.status = ProcessStatus.SYNC_FAILED
            update_scanneddata_database(item, {"file_status": item.status.value})
            if item.sync_db_id is not None:
                finalize_sync_job(item, "Unexpected error during upload")


def start_processing(item: ProcessItem):
    started = time.monotonic()
    item.analytics_upload_retries = 0
    telemetry = file_metadata(item.ocr_file)
    track("upload.started", item=item, targets=len(item.OneDriveDestinations), **telemetry)
    item.status = ProcessStatus.SYNC
    update_scanneddata_database(item, {"file_status": item.status.value})
    item.time_upload_started = datetime.now()
    logger.info(f"Processing file for upload: {item.ocr_file}")
    results = []
    targets = [item.local_directory_above] + item.additional_remote_paths
    for i, onedriveitem in enumerate(item.OneDriveDestinations, start=1):
        logger.info(f"({i} / {len(item.OneDriveDestinations)}) Uploading {item.ocr_file} to {onedriveitem.remote_file_path} in folder {onedriveitem.remote_folder_id} on drive {onedriveitem.remote_drive_id} at SMB target {targets[i - 1] if i - 1 < len(targets) else "Unknown"}")
        item.current_uploading = i
        item.current_upload_target = targets[i - 1] if i - 1 < len(targets) else None
        update_scanneddata_database(item, {"file_status": item.status.value})
        target_started = time.monotonic()
        track("upload.target_started", item=item, attempt=i)
        res = upload_small(item, onedriveitem)
        results.append(res)
        track(
            "upload.target_completed" if res else "upload.target_failed",
            item=item, attempt=i, duration_ms=elapsed_ms(target_started),
            status_code=getattr(onedriveitem, "analytics_status_code", None),
        )

    # Collect all web URLs in the correct order after all uploads are completed
    web_urls = []
    for onedriveitem in item.OneDriveDestinations:
        if hasattr(onedriveitem, 'web_url') and onedriveitem.web_url:
            web_urls.append(onedriveitem.web_url)
        else:
            web_urls.append("")  # Empty placeholder to maintain order

    # Update the database with all web URLs in the correct order
    if web_urls:
        update_scanneddata_database(item, {'web_url': ",".join(web_urls)})
        logger.debug(f"Updated web URLs in correct order: {web_urls}")

    res = bool(results) and all(results)
    if res is False:
        track("upload.failed", item=item, duration_ms=elapsed_ms(started), successful_targets=sum(bool(result) for result in results), failed_targets=sum(not result for result in results), targets=len(results), retries=item.analytics_upload_retries, reason="target_failed" if results else "no_targets", **telemetry)
        track("document.failed", item=item, reason="upload_failed" if results else "no_targets")
        logger.error(f"Failed to upload {item.ocr_file}", extra={"analytics_handled": True})
        item.status = ProcessStatus.SYNC_FAILED
        move_to_failed(item)
        finalize_sync_job(item, "Failed to upload file to OneDrive")
    else:
        track("upload.completed", item=item, duration_ms=elapsed_ms(started), targets=len(results), retries=item.analytics_upload_retries, **telemetry)
        logger.info(f"Upload completed: {item.filename}")

        # Delete ocr file
        try:
            os.remove(item.ocr_file)
            logger.debug(f"Deleted local file {item.ocr_file}")
        except Exception:
            logger.exception(f"Failed to delete local file {item.ocr_file}")

        # Delete original file
        try:
            if config.get("smb.keepOriginals", False) is False:
                os.remove(item.local_file_path)
                logger.debug(f"Deleted original file {item.local_file_path}")
        except Exception:
            logger.exception(f"Failed to delete original file {item.local_file_path}")

        for additional_path in item.additional_local_paths:
            try:
                if os.path.exists(additional_path):
                    os.remove(additional_path)
                    logger.debug(f"Deleted additional local file {additional_path}")
            except Exception:
                logger.exception(f"Failed to delete additional local file {additional_path}")

        item.status = ProcessStatus.COMPLETED
        item.time_finished = datetime.now()
        finalize_sync_job(item)
        track("document.completed", item=item, total_duration_ms=max(0, round((item.time_finished - item.time_added).total_seconds() * 1000)), pages=item.pdf_pages, targets=len(results))
    update_scanneddata_database(item, {"file_status": item.status.value})


def start_consuming_with_reconnect():
    consume(RABBITQUEUE, callback, heartbeat=600)


# Start the consumer with reconnect logic
start_consuming_with_reconnect()
