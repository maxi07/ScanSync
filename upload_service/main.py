from datetime import datetime
import pickle
from scansynclib.ProcessItem import ProcessItem, ProcessStatus
from scansynclib.logging import logger
from scansynclib.helpers import connect_rabbitmq, move_to_failed
from scansynclib.sqlite_wrapper import update_scanneddata_database
from scansynclib.onedrive_api import upload_small
from scansynclib.config import config
import os
import time
import pika.exceptions

logger.info("Starting Upload service...")
RABBITQUEUE = "upload_queue"


def callback(ch, method, properties, body):
    try:
        item: ProcessItem = pickle.loads(body)
        if not isinstance(item, ProcessItem):
            logger.warning("Received object, that is not of type ProcessItem. Skipping.")
            return
        logger.info(f"Received PDF for Upload: {item.filename}")
        if not os.path.exists(item.ocr_file):
            logger.error(f"OCR file does not exist for upload: {item.ocr_file}")
            item.status = ProcessStatus.SYNC_FAILED
            update_scanneddata_database(item, {"file_status": item.status.value})
            move_to_failed(item)
        else:
            start_processing(item)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception:
        logger.exception(f"Failed processing {body}.")
        item.status = ProcessStatus.SYNC_FAILED
        update_scanneddata_database(item, {"file_status": item.status.value})


def start_processing(item: ProcessItem):
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
        res = upload_small(item, onedriveitem)
        results.append(res)
    res = all(results)
    if res is False:
        logger.error(f"Failed to upload {item.ocr_file}")
        item.status = ProcessStatus.SYNC_FAILED
        move_to_failed(item)
    else:
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
    update_scanneddata_database(item, {"file_status": item.status.value})


def start_consuming_with_reconnect():
    while True:
        try:
            connection, channel = connect_rabbitmq([RABBITQUEUE], heartbeat=600)
            channel.basic_consume(queue=RABBITQUEUE, on_message_callback=callback)
            logger.info("Upload service started, waiting for messages...")
            channel.start_consuming()
        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"Connection lost: {e}. Reconnecting in 5 seconds...")
            time.sleep(5)
        except Exception as e:
            logger.exception(f"Unexpected error: {e}. Restarting consumer...")
            time.sleep(5)


# Start the consumer with reconnect logic
start_consuming_with_reconnect()
