from shared.logging import logger
from shared.ProcessItem import ProcessItem, ProcessStatus, OCRStatus
from shared.sqlite_wrapper import update_scanneddata_database
from shared.helpers import connect_rabbitmq, forward_to_rabbitmq
from shared.openai_settings import openai_settings
import pickle
import ocrmypdf
from datetime import datetime
import time
import pika.exceptions

logger.info("Starting OCR service...")
RABBITQUEUE = "ocr_queue"


def callback(ch, method, properties, body):
    try:
        item: ProcessItem = pickle.loads(body)
        if not isinstance(item, ProcessItem):
            logger.warning("Received object, that is not of type ProcessItem. Skipping.")
            return
        logger.info(f"Received PDF for OCR: {item.filename}")
        start_processing(item)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception:
        logger.exception(f"Failed processing {body}.")
        item.ocr_status = OCRStatus.FAILED


def start_processing(item: ProcessItem):
    item.status = ProcessStatus.OCR
    update_scanneddata_database(item.db_id, {"file_status": item.status.value})
    item.time_ocr_started = datetime.now()

    logger.info(f"Processing file with OCR: {item.local_file_path}")

    try:
        result = ocrmypdf.ocr(item.local_file_path, item.ocr_file, output_type='pdfa', skip_text=True, rotate_pages=True, jpg_quality=80, png_quality=80, optimize=2, language=["eng", "deu"], tesseract_timeout=120)
        logger.info(f"OCR processing completed: {item.local_file_path}")
        logger.debug(f"OCR exited with code {result}")
        logger.debug(f"Adding {item.ocr_file} to sync queue")
        item.ocr_status = OCRStatus.COMPLETED
    except ocrmypdf.UnsupportedImageFormatError:
        logger.error(f"Unsupported image format: {item.local_file_path}")
        item.ocr_status = OCRStatus.UNSUPPORTED
    except ocrmypdf.DpiError as dpiex:
        logger.error(f"DPI error: {item.local_file_path} {dpiex}")
        item.ocr_status = OCRStatus.DPI_ERROR
    except ocrmypdf.InputFileError as inex:
        logger.error(f"Input error: {item.local_file_path} {inex}")
        item.ocr_status = OCRStatus.INPUT_ERROR
    except ocrmypdf.OutputFileAccessError as outex:
        logger.error(f"Output error: {item.local_file_path} {outex}")
        item.ocr_status = OCRStatus.OUTPUT_ERROR
    except ocrmypdf.MissingDependencyError:
        logger.exception("Cannot process with OCR due to missing dependencies.")
        item.ocr_status = OCRStatus.FAILED
    except Exception as ex:
        logger.exception(f"Failed processing {item.local_file_path} with OCR: {ex}")
        item.ocr_status = OCRStatus.FAILED
    finally:
        item.time_ocr_finished = datetime.now()
        item.status = ProcessStatus.SYNC_PENDING

        try:
            logger.debug(f"Checking if OpenAI key is set: {openai_settings.api_key}")
            if openai_settings.api_key:
                logger.info(f"Forwarding item {item.filename} to OpenAI service.")
                item.status = ProcessStatus.FILENAME_PENDING
                forward_to_rabbitmq("openai_queue", item)
            else:
                logger.info(f"Forwarding item {item.filename} to Upload service.")
                item.status = ProcessStatus.SYNC_PENDING
                forward_to_rabbitmq("upload_queue", item)
        except Exception as e:
            logger.error(f"Failed to forward item {item.filename} to the next service: {e}")
            item.status = ProcessStatus.FAILED
        finally:
            update_scanneddata_database(item.db_id, {"file_status": item.status.value})
        return item


def start_consuming_with_reconnect():
    while True:
        try:
            connection, channel = connect_rabbitmq([RABBITQUEUE], heartbeat=600)
            channel.basic_consume(queue=RABBITQUEUE, on_message_callback=callback)
            logger.info("OCR service started, waiting for messages...")
            channel.start_consuming()
        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"Connection lost: {e}. Reconnecting in 5 seconds...")
            time.sleep(5)
        except Exception as e:
            logger.exception(f"Unexpected error: {e}. Restarting consumer...")
            time.sleep(5)


# Start the consumer with reconnect logic
start_consuming_with_reconnect()
