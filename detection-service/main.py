import os
import time
from shared.logging import logger
from shared.ProcessItem import ItemType, ProcessItem, ProcessStatus
from PIL import Image
from pypdf import PdfReader
import pika
from shared.sqlite_wrapper import execute_query, update_scanneddata_database
from shared.helpers import connect_rabbitmq
from shared.config import config
import pymupdf
import pickle

SCAN_DIR = config.get("smb.path")
RABBITQUEUE = "ocr_queue"

logger.info("Starting detection service...")
if not os.path.exists(SCAN_DIR):
    logger.critical(f"{SCAN_DIR} does not exist!")
    exit(1)


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
        logger.debug(f"Ignoring working _OCR file at {filepath}")
        return

    # Ignore folder failed-documents
    if config.get("failedDir") in filepath:
        logger.debug(f"Ignoring failed documents folder at {filepath}")
        return

    # Test if file is PDF or image. if neither can be opened, wait five seconds and try again.
    # Repeat this process until a maximum timeout of three minutes is reached
    timeout = 180
    start_time = time.time()

    logger.info(f"Gathering info about new file at {filepath}")
    for i in range(timeout):
        if is_pdf(filepath):
            item = ProcessItem(filepath, ItemType.PDF)
            break
        elif is_image(filepath):
            item = ProcessItem(filepath, ItemType.IMAGE)
            break
        else:
            logger.debug(f"Waiting for {filepath} for another {int(round(timeout - (time.time() - start_time), 0))} seconds")
            time.sleep(5)
            if time.time() - start_time > timeout:
                logger.warning(f"File {filepath} is neither a PDF or image file. Skipping.")
                return

    # Add pdf to database
    item.db_id = execute_query('INSERT INTO scanneddata (file_name, local_filepath) VALUES (?, ?)', (item.filename, item.local_directory_above), return_last_id=True)
    logger.debug(f"Added {filepath} to database with id {item.db_id}")
    update_scanneddata_database(item.db_id, {"file_status": item.status.value, "local_filepath": item.local_directory_above, "file_name": item.filename})

    # Generate preview image
    try:
        preview_folder = "/shared/preview-images/"
        logger.debug(f"Checking if {preview_folder} exists")
        if not os.path.exists(preview_folder):
            logger.debug(f"Creating folder {preview_folder}")
            os.mkdir(preview_folder)
        previewimage_path = preview_folder + str(item.db_id) + '.jpg'
        pdf_to_jpeg(item.local_file_path, previewimage_path, 128, 50)
        update_scanneddata_database(item.db_id, {'previewimage_path': "/static/images/pdfpreview/" + str(item.db_id) + ".jpg"})
    except Exception as e:
        logger.exception(f"Error adding preview image to database: {e}")

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
    update_scanneddata_database(item.db_id, {'remote_filepath': item.remote_file_path})

    # Read PDF file properties
    if item.item_type == ItemType.PDF:
        try:
            pdf_reader = PdfReader(item.local_file_path)
            item.pdf_pages = len(pdf_reader.pages)
            logger.debug(f"PDF file has {item.pdf_pages} pages to process")
            update_scanneddata_database(item.db_id, {'pdf_pages': item.pdf_pages})
        except Exception:
            logger.exception(f"Error reading PDF file: {item.local_file_path}")
    item.status = ProcessStatus.OCR_PENDING
    update_scanneddata_database(item.db_id, {"file_status": item.status.value})
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


def get_all_files(directory):
    """Rekursiv alle Dateien in einem Verzeichnis und Unterverzeichnissen abrufen"""
    all_files = set()
    for root, _, files in os.walk(directory):
        for file in files:
            all_files.add(os.path.join(root, file))
    return all_files


try:
    connection, channel = connect_rabbitmq("ocr_queue")
except Exception as e:
    logger.critical(f"Failed to connect to RabbitMQ: {e}")
    exit(1)
logger.debug(f"Connected to RabbitMQ on {channel.channel_number}")
channel.queue_declare(queue=RABBITQUEUE, durable=True)
logger.debug(f"Connected to queue {RABBITQUEUE}")

logger.info(f"Scanning {SCAN_DIR} for new files...")
known_files = get_all_files(SCAN_DIR)

while True:
    try:
        connection.process_data_events(1)
        current_files = get_all_files(SCAN_DIR)

        new_files = current_files - known_files
        if new_files:
            for new_file in new_files:
                logger.info(f"Found new file: {new_file}")
                on_created(new_file)

        known_files = current_files

    except Exception as e:
        logger.error(f"Failed scanning {SCAN_DIR}: {e}")

    time.sleep(1)
