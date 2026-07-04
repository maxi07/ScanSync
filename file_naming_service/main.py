import os
import pickle


from scansynclib.ProcessItem import ProcessItem, ProcessStatus, FileNamingStatus
from scansynclib.logging import logger
from scansynclib.helpers import consume, forward_to_rabbitmq
import pika.exceptions
from scansynclib.openai_helper import generate_filename_openai
from scansynclib.ollama_helper import generate_filename_ollama
from scansynclib.settings_schema import FileNamingMethod
from scansynclib.sqlite_wrapper import execute_query, update_scanneddata_database
from scansynclib.settings import settings


RABBITQUEUE = "file_naming_queue"


def get_latest_file_naming_status(item: ProcessItem):
    status_name = execute_query(
        "SELECT file_naming_status FROM file_naming_jobs WHERE id = ?",
        (item.file_naming_db_id,),
        return_scalar=True
    )
    if status_name:
        try:
            return FileNamingStatus[status_name]
        except KeyError:
            logger.warning(f"Unknown file naming status '{status_name}' for item {item.filename}")
    return item.file_naming_status


def callback(ch, method, properties, body):
    item = None
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
        item.file_naming_status = FileNamingStatus.PROCESSING
        execute_query('UPDATE file_naming_jobs SET file_naming_status = ? WHERE id = ?', (FileNamingStatus.PROCESSING.name, item.file_naming_db_id))

        method_setting = settings.file_naming.method

        if method_setting == FileNamingMethod.OPENAI:
            new_filename = generate_filename_openai(item)
        elif method_setting == FileNamingMethod.OLLAMA:
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
        item_file_naming_db_id = getattr(item, "file_naming_db_id", None)
        if item_file_naming_db_id:
            execute_query(
                "UPDATE file_naming_jobs SET file_naming_status = ?, error_description = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
                (FileNamingStatus.FAILED.name, str(e), item_file_naming_db_id)
            )
        return
    except Exception as e:
        logger.exception(f"Failed processing {item.filename}.")
        execute_query("UPDATE file_naming_jobs SET file_naming_status = ?, error_description = ?, finished = DATETIME('now', 'localtime') WHERE id = ?", (FileNamingStatus.FAILED.name, str(e), item.file_naming_db_id))
    finally:
        ack_ok = True
        try:
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except pika.exceptions.AMQPError:
            ack_ok = False
            # The connection was lost before we could acknowledge. The unified
            # consumer will reconnect and the broker will redeliver the message.
            logger.error("Connection lost while acknowledging message. It will be redelivered after reconnect.")
        if ack_ok:
            if isinstance(item, ProcessItem):
                item_file_naming_db_id = getattr(item, "file_naming_db_id", None)
                if item_file_naming_db_id:
                    item.file_naming_status = get_latest_file_naming_status(item)
                item.status = ProcessStatus.SYNC_PENDING
                update_scanneddata_database(item, {"file_status": item.status.value})
                forward_to_rabbitmq("upload_queue", item)
            else:
                logger.error("Item is None, cannot forward to upload queue.")


def start_consuming_with_reconnect():
    consume(RABBITQUEUE, callback, heartbeat=120)


if __name__ == "__main__":
    # Start the consumer with reconnect logic
    start_consuming_with_reconnect()
