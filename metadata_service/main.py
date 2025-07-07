import json
import os
import time
from scansynclib.logging import logger
from scansynclib.ProcessItem import ItemType, ProcessItem, ProcessStatus
from PIL import Image
from pypdf import PdfReader
import pika
import pika.exceptions
from scansynclib.sqlite_wrapper import execute_query, update_scanneddata_database
from scansynclib.helpers import connect_rabbitmq, move_to_failed
from scansynclib.config import config
import pymupdf
import pickle

RABBITQUEUE = "metadata_queue"
TIMEOUT_PDF_VALIDATION = 300
channel, connection = None, None


def on_created(filepath: str):
    # Test for valid path
    if os.path.exists(filepath) and os.path.isdir(filepath):
        logger.warning(f"Given path is a directory, will skip: {filepath}")
        return

    # Test for security files
    if ":Zone.Identifier" in filepath:
        logger.info(f"Ignoring Windows Security File file at {filepath}")
        try:
            os.remove(filepath)
        except OSError:
            pass
        return

    # Ignore hidden files
    if os.path.basename(filepath).startswith((".", "_")):
        logger.info(f"Ignoring hidden file at {filepath}")
        return

    # Ignore OCR files
    if "_OCR.pdf" in filepath:
        logger.info(f"Ignoring working _OCR file at {filepath}")
        return

    # Ignore folder failed-documents
    if config.get("failedDir") in filepath:
        logger.info(f"Ignoring failed documents folder at {filepath}")
        return

    # Test if file is PDF or image. if neither can be opened, wait five seconds and try again.
    # Repeat this process until a maximum TIMEOUT_PDF_VALIDATION of three minutes is reached
    start_time = time.time()

    logger.info(f"Gathering info about new file at {filepath}")
    item = ProcessItem(filepath, ItemType.UNKNOWN)
    item.db_id = execute_query('INSERT INTO scanneddata (file_name, local_filepath) VALUES (?, ?)', (item.filename, item.local_directory_above), return_last_id=True)
    logger.debug(f"Added {filepath} to database with id {item.db_id}")
    try:
        item.smb_target_id = execute_query("SELECT id FROM smb_onedrive WHERE smb_name = ?", (item.local_directory_above,), fetchone=True).get("id")
    except Exception as e:
        logger.exception(f"Error fetching SMB target ID for {item.local_directory_above}: {e}")
        item.smb_target_id = None
    update_scanneddata_database(item, {"file_status": item.status.value, "local_filepath": item.local_directory_above, "file_name": item.filename})

    # Match a remote destination
    query = "SELECT onedrive_path, folder_id, drive_id FROM smb_onedrive WHERE smb_name = ?"
    params = (item.local_directory_above,)
    result = execute_query(query, params, fetchone=True)
    if result:
        logger.debug(f"Found remote destination for {item.local_directory_above}: {result}")
        item.remote_file_path = result.get("onedrive_path")
        item.remote_folder_id = result.get("folder_id")
        item.remote_drive_id = result.get("drive_id")
    else:
        logger.warning(f"Could not find remote destination for {item.local_directory_above}")
    update_scanneddata_database(item, {'remote_filepath': item.remote_file_path})

    logger.info(f"Waiting for {item.filename} to be a valid PDF or image file")
    for i in range(TIMEOUT_PDF_VALIDATION):
        if is_pdf(filepath):
            item.item_type = ItemType.PDF
            break
        elif is_image(filepath):
            item.item_type = ItemType.IMAGE
            break
        else:
            logger.debug(f"Waiting for {filepath} for another {int(round(TIMEOUT_PDF_VALIDATION - (time.time() - start_time), 0))} seconds")
            time.sleep(5)
            if time.time() - start_time > TIMEOUT_PDF_VALIDATION:
                logger.warning(f"File {filepath} is neither a PDF or image file. Skipping.")
                item.status = ProcessStatus.INVALID_FILE
                update_scanneddata_database(item, {"file_status": item.status.value})
                move_to_failed(item)
                return

    # Check again if file exists
    if not os.path.exists(filepath):
        logger.warning(f"File {filepath} does not exist anymore. Skipping.")
        item.status = ProcessStatus.DELETED
        update_scanneddata_database(item, {"file_status": item.status.value})
        return

    item.status = ProcessStatus.READING_METADATA
    update_scanneddata_database(item, {"file_status": item.status.value})

    # Generate preview image
    try:
        preview_folder = "/app/preview-images/"
        logger.debug(f"Checking if {preview_folder} exists")
        if not os.path.exists(preview_folder):
            logger.debug(f"Creating folder {preview_folder}")
            os.mkdir(preview_folder)
        previewimage_path = preview_folder + str(item.db_id) + '.jpg'
        pdf_to_jpeg(item.local_file_path, previewimage_path, 512, 50)
        web_path_previewimage = "/static/images/pdfpreview/" + str(item.db_id) + ".jpg"
        item.preview_image_path = web_path_previewimage
        update_scanneddata_database(item, {'previewimage_path': web_path_previewimage})
    except Exception as e:
        logger.exception(f"Error adding preview image to database: {e}")

    # Read PDF file properties
    if item.item_type == ItemType.PDF:
        try:
            pdf_reader = PdfReader(item.local_file_path)
            item.pdf_pages = len(pdf_reader.pages)
            logger.info(f"{item.filename} has {item.pdf_pages} pages to process")
            update_scanneddata_database(item, {'pdf_pages': item.pdf_pages})
        except Exception:
            logger.exception(f"Error reading PDF file: {item.local_file_path}")
    item.status = ProcessStatus.OCR_PENDING
    update_scanneddata_database(item, {"file_status": item.status.value})
    channel.basic_publish(
                    exchange="",
                    routing_key="ocr_queue",
                    body=pickle.dumps(item),
                    properties=pika.BasicProperties(delivery_mode=2)
                )
    logger.info(f"Added {item.local_file_path} to OCR queue")


def is_image(file_path) -> bool:
    try:
        with Image.open(file_path):
            logger.debug(f"File {file_path} is an image file.")
            return True
    except (IOError, Image.DecompressionBombError):
        return False


def is_pdf(file_path):
    try:
        with open(file_path, "rb") as file:
            r = PdfReader(file)
            if len(r.pages) > 0:
                logger.debug(f"File {file_path} is a PDF file.")
            else:
                return False
        return True
    except Exception:
        return False


def pdf_to_jpeg(pdf_path: str, output_path: str, target_height=128, compression_quality=50):
    logger.debug(f"Creating JPEG preview image from {pdf_path} to {output_path}")
    # Open the PDF file
    pdf_document = pymupdf.open(pdf_path)

    # Get the first page
    first_page = pdf_document[0]

    # Get the aspect ratio of the page
    aspect_ratio = first_page.rect.width / first_page.rect.height

    # Calculate the corresponding width based on the target height
    target_width = int(target_height * aspect_ratio)

    # Create a matrix for the desired size
    matrix = pymupdf.Matrix(target_width / first_page.rect.width, target_height / first_page.rect.height)

    # Create a pixmap for the page with the specified size
    pixmap = first_page.get_pixmap(matrix=matrix)

    # Save the pixmap as a JPEG image with compression
    pixmap.save(output_path, "jpeg", jpg_quality=compression_quality)

    # Close the PDF document
    pdf_document.close()


def callback(ch, method, properties, body):
    try:
        data = json.loads(body)
        filepath = data["file_path"]
        logger.info(f"Received item for metadata service {filepath}")
        on_created(filepath)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception:
        logger.exception(f"Failed processing {body} in metadata_service.")
        return


def start_consuming_with_reconnect():
    global channel, connection
    while True:
        try:
            connection, channel = connect_rabbitmq([RABBITQUEUE, "ocr_queue"], heartbeat=600)
            channel.basic_consume(queue=RABBITQUEUE, on_message_callback=callback)
            logger.info("Metadata service started, waiting for messages...")
            channel.start_consuming()
        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"Connection lost: {e}. Reconnecting in 5 seconds...")
            time.sleep(5)
        except Exception as e:
            logger.exception(f"Unexpected error: {e}. Restarting consumer...")
            time.sleep(5)


# Start the consumer with reconnect logic
start_consuming_with_reconnect()
