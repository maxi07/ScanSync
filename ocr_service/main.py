from scansynclib.logging import logger
from scansynclib.ProcessItem import ProcessItem, ProcessStatus, OCRStatus
from scansynclib.sqlite_wrapper import execute_query, update_scanneddata_database
from scansynclib.helpers import consume, forward_to_rabbitmq, extract_text
import pickle
import ocrmypdf
import os
from datetime import datetime
from scansynclib.settings import settings

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
    item.ocr_status = OCRStatus.PROCESSING
    item.ocr_db_id = execute_query(
        'INSERT INTO ocr_jobs (scanneddata_id, ocr_status) VALUES (?, ?)',
        (item.db_id, OCRStatus.PROCESSING.name),
        return_last_id=True
    )
    update_scanneddata_database(item, {"file_status": item.status.value})
    item.time_ocr_started = datetime.now()

    logger.info(f"Processing file with OCR: {item.filename}")
    ocr_error = None
    result = None

    try:
        result = ocrmypdf.ocr(item.local_file_path, item.ocr_file, output_type='pdfa', skip_text=True, rotate_pages=True, jpg_quality=80, png_quality=80, optimize=2, language=["eng", "deu"], tesseract_timeout=120)
        logger.debug(f"OCR exited with code {result}")

        if result != 0:
            logger.error(f"OCR exited with code {result}")
            item.ocr_status = OCRStatus.FAILED
            ocr_error = f"OCR exited with code {result}"
        else:
            logger.info(f"OCR processing completed: {item.filename}")

            # Verify that the OCR file actually contains text
            if os.path.exists(item.ocr_file):
                extracted_text = (extract_text(item.ocr_file, max_pages=5, max_chars=2048) or "").strip()
                if extracted_text:
                    logger.info(f"OCR verification successful: extracted {len(extracted_text)} characters from {item.filename}")
                    item.ocr_status = OCRStatus.COMPLETED
                else:
                    logger.warning(f"OCR verification failed: no text found in OCR output file {item.ocr_file}")
                    item.ocr_status = OCRStatus.NO_TEXT
            else:
                logger.error(f"OCR output file not found: {item.ocr_file}")
                item.ocr_status = OCRStatus.OUTPUT_ERROR
    except ocrmypdf.UnsupportedImageFormatError:
        logger.error(f"Unsupported image format: {item.local_file_path}")
        item.ocr_status = OCRStatus.UNSUPPORTED
        ocr_error = OCRStatus.UNSUPPORTED.value
    except ocrmypdf.DpiError as dpiex:
        logger.error(f"DPI error: {item.local_file_path} {dpiex}")
        item.ocr_status = OCRStatus.DPI_ERROR
        ocr_error = str(dpiex)
    except ocrmypdf.InputFileError as inex:
        logger.error(f"Input error: {item.local_file_path} {inex}")
        item.ocr_status = OCRStatus.INPUT_ERROR
        ocr_error = str(inex)
    except ocrmypdf.OutputFileAccessError as outex:
        logger.error(f"Output error: {item.local_file_path} {outex}")
        item.ocr_status = OCRStatus.OUTPUT_ERROR
        ocr_error = str(outex)
    except ocrmypdf.MissingDependencyError:
        logger.exception("Cannot process with OCR due to missing dependencies.")
        item.ocr_status = OCRStatus.FAILED
        ocr_error = "Missing OCR dependency"
    except Exception as ex:
        logger.exception(f"Failed processing {item.local_file_path} with OCR: {ex}")
        item.ocr_status = OCRStatus.FAILED
        ocr_error = str(ex)
    finally:
        item.time_ocr_finished = datetime.now()
        if result is not None and result != 0:
            item.ocr_status = OCRStatus.FAILED
            if not ocr_error:
                ocr_error = f"OCR exited with code {result}"
        if item.ocr_db_id:
            execute_query(
                "UPDATE ocr_jobs SET ocr_status = ?, ocr_error = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
                (item.ocr_status.name, ocr_error, item.ocr_db_id)
            )
        item.status = ProcessStatus.SYNC_PENDING

        try:
            logger.debug("Checking if File Naming is enabled")
            ollama_enabled = bool(settings.file_naming.ollama_server_url and settings.file_naming.ollama_server_port and settings.file_naming.ollama_model)
            openai_enabled = bool(settings.file_naming.openai_api_key)
            if openai_enabled or ollama_enabled:
                logger.info(f"Forwarding item {item.filename} to File Naming service.")
                item.status = ProcessStatus.FILENAME_PENDING
                forward_to_rabbitmq("file_naming_queue", item)
            else:
                logger.info(f"Forwarding item {item.filename} to Upload service.")
                item.status = ProcessStatus.SYNC_PENDING
                forward_to_rabbitmq("upload_queue", item)
        except Exception as e:
            logger.error(f"Failed to forward item {item.filename} to the next service: {e}")
            item.status = ProcessStatus.FAILED
        finally:
            update_scanneddata_database(item, {"file_status": item.status.value, "ocr_status": item.ocr_status.name})
        return item


def start_consuming_with_reconnect():
    consume(RABBITQUEUE, callback, heartbeat=600)


# Start the consumer with reconnect logic
if __name__ == "__main__":
    start_consuming_with_reconnect()
