import os
import pickle
from scansynclib.ProcessItem import ProcessItem, ProcessStatus
from scansynclib.logging import logger
from scansynclib.helpers import connect_rabbitmq, forward_to_rabbitmq
import time
import pika.exceptions
from scansynclib.openai_helper import generate_filename
from scansynclib.sqlite_wrapper import update_scanneddata_database


RABBITQUEUE = "openai_queue"


def callback(ch, method, properties, body):
    try:
        item: ProcessItem = pickle.loads(body)
        if not isinstance(item, ProcessItem):
            logger.warning("Received object, that is not of type ProcessItem. Skipping.")
            return
        logger.info(f"Received PDF for OPENAI renaming: {item.filename}")
        new_filename = generate_filename(item)
        if new_filename and os.path.exists(item.ocr_file):
            os.rename(item.ocr_file, os.path.join(item.local_directory, new_filename + "_OCR.pdf"))
            item.filename_without_extension = new_filename
            item.filename = new_filename + ".pdf"
            item.ocr_file = os.path.join(item.local_directory, new_filename + "_OCR.pdf")
            logger.info(f"Generated filename: {new_filename}")
        try:
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except pika.exceptions.AMQPConnectionError:
            logger.error("Connection lost while acknowledging message. Reconnecting...")
            connection, channel = connect_rabbitmq([RABBITQUEUE], heartbeat=120)
            channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception:
        logger.exception(f"Failed processing {item.filename} with openai.")
    finally:
        item.status = ProcessStatus.SYNC_PENDING
        update_scanneddata_database(item, {"file_status": item.status.value})
        forward_to_rabbitmq("upload_queue", item)


def start_consuming_with_reconnect():
    global channel, connection
    while True:
        try:
            connection, channel = connect_rabbitmq([RABBITQUEUE], heartbeat=120)
            channel.basic_consume(queue=RABBITQUEUE, on_message_callback=callback)
            logger.info("OpenAI service started, waiting for messages...")
            channel.start_consuming()
        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"Connection lost: {e}. Reconnecting in 5 seconds...")
            time.sleep(5)
        except Exception as e:
            logger.exception(f"Unexpected error: {e}. Restarting consumer...")
            time.sleep(5)


# Start the consumer with reconnect logic
start_consuming_with_reconnect()
