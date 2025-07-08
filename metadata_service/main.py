import json
import os
import time
from scansynclib.logging import logger
from scansynclib.ProcessItem import ItemType, ProcessItem, ProcessStatus, OneDriveDestination
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


def on_created(filepaths: list):
    # Test for valid path
    if os.path.exists(filepaths[0]) and os.path.isdir(filepaths[0]):
        logger.warning(f"Given path is a directory, will skip: {filepaths}")
        return

    # Test for security files
    if ":Zone.Identifier" in filepaths[0]:
        logger.info(f"Ignoring Windows Security File file at {filepaths[0]}")
        try:
            for file in filepaths:
                if os.path.exists(file):
                    logger.debug(f"Removing security file at {file}")
                    os.remove(file)
        except OSError:
            pass
        return

    # Ignore hidden files
    if os.path.basename(filepaths[0]).startswith((".", "_")):
        logger.info(f"Ignoring hidden file at {filepaths[0]}")
        return

    # Ignore OCR files
    if "_OCR.pdf" in filepaths[0]:
        logger.info(f"Ignoring working _OCR file at {filepaths[0]}")
        return

    # Ignore folder failed-documents
    if config.get("failedDir") in filepaths[0]:
        logger.info(f"Ignoring failed documents folder at {filepaths[0]}")
        return

    # Test if file is PDF or image. if neither can be opened, wait five seconds and try again.
    # Repeat this process until a maximum TIMEOUT_PDF_VALIDATION of three minutes is reached
    start_time = time.time()

    logger.info(f"Gathering info about new file{"s" if len(filepaths) > 1 else ""} at {filepaths}")
    item = ProcessItem(filepaths[0], ItemType.UNKNOWN)
    item.db_id = execute_query('INSERT INTO scanneddata (file_name, local_filepath) VALUES (?, ?)', (item.filename, item.local_directory_above), return_last_id=True)
    logger.debug(f"Added {filepaths[0]} to database with id {item.db_id}")

    # Now add additional smb paths to the item
    if len(filepaths) > 1:
        try:
            item.add_additional_file_paths(filepaths[1:])
            additional_smbs_str = ",".join(item.additional_remote_paths)
            execute_query("UPDATE scanneddata SET additional_smb = ? WHERE id = ?", (additional_smbs_str, item.db_id))
            logger.debug(f"Added additional smb destinations to item: {additional_smbs_str}")
        except Exception as e:
            logger.exception(f"Error adding additional file paths to item: {e}")
            item.additional_local_paths = []
            item.additional_remote_paths = []

    try:
        # TODO: Fetch the smb_target_ids from the database
        items = [item.local_directory_above] + item.additional_local_paths
        placeholders = ",".join("?" for _ in items)
        query = f"SELECT id FROM smb_onedrive WHERE smb_name IN ({placeholders})"
        item.smb_target_ids = execute_query(query, tuple(items), fetchall=True)
    except Exception as e:
        logger.exception(f"Error fetching SMB target IDs for {item.local_directory_above}: {e}")
        item.smb_target_ids = []
    update_scanneddata_database(item, {"file_status": item.status.value, "local_filepath": item.local_directory_above, "file_name": item.filename})

    # Match a remote destination
    smb_names = [item.local_directory_above] + item.additional_remote_paths

    if smb_names:
        placeholders = ",".join("?" for _ in smb_names)
        query = f"""
            SELECT onedrive_path, folder_id, drive_id
            FROM smb_onedrive
            WHERE smb_name IN ({placeholders})
        """
        result = execute_query(query, tuple(smb_names), fetchall=True)
    else:
        result = []
    if result:
        for res in result:
            item.OneDriveDestinations.append(
                OneDriveDestination(
                    remote_file_path=res.get("onedrive_path"),
                    remote_folder_id=res.get("folder_id"),
                    remote_drive_id=res.get("drive_id")
                )
            )
            logger.debug(f"Found remote destination for {res}: {res.get("onedrive_path")}")
    else:
        logger.warning(f"Could not find remote destination for {item.local_directory_above}")
    update_scanneddata_database(item, {'remote_filepath': ",".join([dest.remote_file_path for dest in item.OneDriveDestinations])})

    logger.info(f"Waiting for {item.filename} to be a valid PDF or image file")
    for i in range(TIMEOUT_PDF_VALIDATION):
        if is_pdf(filepaths[0]):
            item.item_type = ItemType.PDF
            break
        elif is_image(filepaths[0]):
            item.item_type = ItemType.IMAGE
            break
        else:
            logger.debug(f"Waiting for {filepaths[0]} for another {int(round(TIMEOUT_PDF_VALIDATION - (time.time() - start_time), 0))} seconds")
            time.sleep(5)
            if time.time() - start_time > TIMEOUT_PDF_VALIDATION:
                logger.warning(f"File {filepaths[0]} is neither a PDF or image file. Skipping.")
                item.status = ProcessStatus.INVALID_FILE
                update_scanneddata_database(item, {"file_status": item.status.value})
                move_to_failed(item)
                return

    # Check again if file exists
    if not os.path.exists(filepaths[0]):
        logger.warning(f"File {filepaths[0]} does not exist anymore. Skipping.")
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
        filepaths: list = data["file_paths"]
        logger.info(f"Received item{"s" if len(filepaths) > 1 else ""} for metadata service {filepaths}")
        on_created(filepaths)
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
