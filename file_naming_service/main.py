import os
import pickle


from scansynclib.ProcessItem import ProcessItem, ProcessStatus, FileNamingStatus
from scansynclib.logging import logger
from scansynclib.helpers import connect_rabbitmq, forward_to_rabbitmq
import time
import pika.exceptions
from scansynclib.openai_helper import generate_filename_openai
from scansynclib.ollama_helper import generate_filename_ollama
from scansynclib.sqlite_wrapper import execute_query, update_scanneddata_database
from scansynclib.settings import settings


RABBITQUEUE = "file_naming_queue"


def callback(ch, method, properties, body):
    try:
        item: ProcessItem = pickle.loads(body)

        if not isinstance(item, ProcessItem):
            logger.warning("Received object, that is not of type ProcessItem. Skipping.")
            raise TypeError("Received object is not a ProcessItem")
        logger.debug(f"Received PDF for automatic file naming: {item.filename}")

        # Create db element
        item.file_naming_db_id = execute_query('INSERT INTO file_naming_jobs (scanneddata_id, file_naming_status) VALUES (?, ?)', (item.db_id, FileNamingStatus.PENDING.name), return_last_id=True)
        logger.debug(f"Added file naming job for {item.filename} to database with id {item.file_naming_db_id}")

        if not os.path.exists(item.ocr_file):
            raise FileNotFoundError(f"OCR file does not exist: {item.ocr_file}")

        # test if openai or ollama will be used
        ollama_enabled = bool(settings.file_naming.ollama_server_url and settings.file_naming.ollama_server_port and settings.file_naming.ollama_model)
        openai_enabled = bool(settings.file_naming.openai_api_key)

        if openai_enabled and ollama_enabled:
            logger.error("Both OpenAI and Ollama are enabled. Please disable one of them in the settings.")

        if not openai_enabled and not ollama_enabled:
            logger.error("Neither OpenAI nor Ollama is enabled. Please enable one of them in the settings.")
        execute_query('UPDATE file_naming_jobs SET file_naming_status = ? WHERE id = ?', (FileNamingStatus.PROCESSING.name, item.file_naming_db_id))

        if openai_enabled:
            new_filename = generate_filename_openai(item)
        elif ollama_enabled:
            new_filename = generate_filename_ollama(item)
        else:
            logger.info("No file naming method configured. Using default filename.")
            new_filename = item.filename_without_extension
        if new_filename and os.path.exists(item.ocr_file):
            os.rename(item.ocr_file, os.path.join(item.local_directory, new_filename + "_OCR.pdf"))
            item.filename_without_extension = new_filename
            item.filename = new_filename + ".pdf"
            item.ocr_file = os.path.join(item.local_directory, new_filename + "_OCR.pdf")
            logger.info(f"Generated filename: {new_filename}")

    except FileNotFoundError:
        logger.error(f"OCR file does not exist: {item.ocr_file}. Cannot generate filename.")
        execute_query("UPDATE file_naming_jobs SET file_naming_status = ?, error_description = ?, finished = DATETIME('now', 'localtime') WHERE id = ?", (FileNamingStatus.FAILED.name, "OCR file does not exist", item.file_naming_db_id))
    except TypeError as e:
        logger.error(f"Received object is not a ProcessItem: {e}. Skipping.")
        execute_query("UPDATE file_naming_jobs SET file_naming_status = ?, error_description = ?, finished = DATETIME('now', 'localtime'), WHERE id = ?", (FileNamingStatus.FAILED.name, str(e), item.file_naming_db_id))
        return
    except Exception as e:
        logger.exception(f"Failed processing {item.filename}.")
        execute_query("UPDATE file_naming_jobs SET file_naming_status = ?, error_description = ?, finished = DATETIME('now', 'localtime'), WHERE id = ?", (FileNamingStatus.FAILED.name, str(e), item.file_naming_db_id))
    finally:
        try:
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except pika.exceptions.AMQPConnectionError:
            logger.error("Connection lost while acknowledging message. Reconnecting...")
            connection, channel = connect_rabbitmq([RABBITQUEUE], heartbeat=120)
            channel.basic_ack(delivery_tag=method.delivery_tag)
        if item:
            item.status = ProcessStatus.SYNC_PENDING
            update_scanneddata_database(item, {"file_status": item.status.value})
            forward_to_rabbitmq("upload_queue", item)
        else:
            logger.error("Item is None, cannot forward to upload queue.")


def start_consuming_with_reconnect():
    global channel, connection
    while True:
        try:
            connection, channel = connect_rabbitmq([RABBITQUEUE], heartbeat=120)
            channel.basic_consume(queue=RABBITQUEUE, on_message_callback=callback)
            logger.info("File naming service started, waiting for messages...")
            channel.start_consuming()
        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"Connection lost: {e}. Reconnecting in 5 seconds...")
            time.sleep(5)
        except Exception as e:
            logger.exception(f"Unexpected error: {e}. Restarting consumer...")
            time.sleep(5)


# Start the consumer with reconnect logic
start_consuming_with_reconnect()
