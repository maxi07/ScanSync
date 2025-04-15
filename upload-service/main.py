from datetime import datetime
import pickle
from shared.ProcessItem import ProcessItem, ProcessStatus
from shared.logging import logger
from shared.helpers import connect_rabbitmq
from shared.sqlite_wrapper import update_scanneddata_database
from shared.onedrive_api import upload

logger.info("Starting Upload service...")


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
    res = upload(item)
    if res is False:
        logger.error(f"Failed to upload {item.local_file_path}")
        item.status = ProcessStatus.SYNC_FAILED
    else:
        logger.info(f"Upload completed: {item.local_file_path}")
        item.status = ProcessStatus.COMPLETED
    update_scanneddata_database(item.db_id, {"file_status": item.status.value})


try:
    connection, channel = connect_rabbitmq("upload_queue")
except Exception as e:
    logger.critical(f"Couldn't connect to RabbitMQ: {e}")
    exit(1)
channel.queue_declare(queue="upload_queue", durable=True)
channel.basic_consume(queue="upload_queue", on_message_callback=callback)
logger.info("Upload service ready!")
channel.start_consuming()
