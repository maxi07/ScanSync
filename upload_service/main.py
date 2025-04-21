from datetime import datetime
import pickle
from shared.ProcessItem import ProcessItem, ProcessStatus
from shared.logging import logger
from shared.helpers import connect_rabbitmq
from shared.sqlite_wrapper import update_scanneddata_database
from shared.onedrive_api import upload_small
from shared.config import config
import os

logger.info("Starting Upload service...")
SMB_PATH = config.get("smb.path")


def callback(ch, method, properties, body):
    try:
        item: ProcessItem = pickle.loads(body)
        if not isinstance(item, ProcessItem):
            logger.warning("Received object, that is not of type ProcessItem. Skipping.")
            return
        logger.info(f"Received PDF for Upload: {item.filename}")
        start_processing(item)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception:
        logger.exception(f"Failed processing {body}.")
        item.status = ProcessStatus.SYNC_FAILED
        update_scanneddata_database(item.db_id, {"file_status": item.status.value})


def start_processing(item: ProcessItem):
    item.status = ProcessStatus.SYNC
    update_scanneddata_database(item.db_id, {"file_status": item.status.value})
    item.time_upload_started = datetime.now()
    logger.info(f"Processing file for upload: {item.local_file_path}")
    res = upload_small(item)
    if res is False:
        logger.error(f"Failed to upload {item.local_file_path}")
        item.status = ProcessStatus.SYNC_FAILED

        # Move failed document to failed folder
        failedDir = os.path.join(SMB_PATH, config.get("failedDir"))
        if failedDir:
            if not os.path.exists(failedDir):
                try:
                    os.makedirs(failedDir)
                except Exception:
                    logger.exception(f"Failed to create failed directory {failedDir}")
            try:
                os.rename(item.local_file_path, os.path.join(failedDir, os.path.basename(item.filename)))
            except Exception:
                logger.exception(f"Failed to move item {item.local_file_path} to failed directory {failedDir}")
            logger.info(f"Moved {item.local_file_path} to {failedDir}")

            # Delete OCR file if present
            if os.path.exists(item.ocr_file):
                try:
                    os.remove(item.ocr_file)
                    logger.info(f"Removed OCR file {item.ocr_file}")
                except Exception:
                    logger.exception(f"Failed to remove OCR file {item.ocr_file}")
        else:
            logger.warning("Failed directory not set in config. Skipping move.")
    else:
        logger.info(f"Upload completed: {item.local_file_path}")

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

        item.status = ProcessStatus.COMPLETED
    update_scanneddata_database(item.db_id, {"file_status": item.status.value})


try:
    connection, channel = connect_rabbitmq(["upload_queue"])
except Exception as e:
    logger.critical(f"Couldn't connect to RabbitMQ: {e}")
    exit(1)
channel.basic_consume(queue="upload_queue", on_message_callback=callback)
logger.info("Upload service ready!")
channel.start_consuming()
