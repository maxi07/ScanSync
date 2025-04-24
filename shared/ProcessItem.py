from enum import Enum
import os
from datetime import datetime
from shared.logging import logger


class ProcessStatus(Enum):
    """Enumeration of possible process statuses.

    OCR_PENDING: OCR has not yet been run on the item.
    OCR: OCR is currently running on the item.
    SYNC_PENDING: Item is queued for syncing to remote storage.
    SYNC: Item is currently being synced to remote storage.
    COMPLETED: Item has been successfully OCR'd and synced.
    FAILED: An error occurred during processing.
    SKIPPED: Item was skipped and not processed.
    SYNC_FAILED: Syncing the item to remote storage failed.
    """
    READING_METADATA = "Reading Metadata"
    OCR_PENDING = "OCR Pending"
    OCR = "OCR Processing"
    FILENAME_PENDING = "File Name Pending"
    FILENAME = "File Name Processing"
    SYNC_PENDING = "Sync Pending"
    SYNC = "Syncing"
    COMPLETED = "Completed"
    FAILED = "Failed"
    SKIPPED = "Skipped"
    SYNC_FAILED = "Sync Failed"


class OCRStatus(Enum):
    """Enumeration of possible OCR statuses.

    UNKNOWN: OCR status not yet determined.
    PENDING: Item is queued for OCR.
    PROCESSING: OCR is currently running on the item.
    COMPLETED: OCR completed successfully on the item.
    FAILED: OCR failed on the item.
    SKIPPED: Item was skipped and OCR was not performed.
    UNSUPPORTED: Item type is not supported for OCR.
    DPI_ERROR: Image DPI is too low for accurate OCR.
    INPUT_ERROR: Error reading input image/PDF.
    OUTPUT_ERROR: Error writing OCR output file.
    """
    UNKNOWN = 0
    PENDING = 1
    PROCESSING = 2
    COMPLETED = 3
    FAILED = -1
    SKIPPED = -2
    UNSUPPORTED = -3
    DPI_ERROR = -4
    INPUT_ERROR = -5
    OUTPUT_ERROR = -6


class ItemType(Enum):
    PDF = 1
    IMAGE = 2
    UNKNOWN = 3


class ProcessItem:
    """ProcessItem represents an item to be processed for OCR and syncing.

    This class contains metadata and status information about the processing
    of a file, including the local and remote file paths, OCR status, sync
    status, timestamps, etc.

    The __init__ method validates the input file and initializes all the
    processing metadata attributes.
    """
    def __init__(self, local_file_path: str, item_type: ItemType, status: ProcessStatus = ProcessStatus.OCR_PENDING):
        try:
            self.local_file_path = local_file_path
            if not os.path.exists(local_file_path):
                logger.error(f"File does not exist: {local_file_path}")
                return
            if not os.path.isfile(local_file_path):
                logger.error(f"Path is not a file: {local_file_path}")
                return
            if not os.access(local_file_path, os.R_OK):
                logger.error(f"File is not readable: {local_file_path}")
                return
        except Exception as e:
            logger.exception(f"Error creating ProcessItem: {e}")
            return
        self.remote_file_path: str = None
        self.remote_directory: str = None
        self.status: ProcessStatus = status
        self.connection = None
        self.filename = os.path.basename(local_file_path)
        self.filename_without_extension = os.path.splitext(self.filename)[0]
        self.local_directory = os.path.dirname(local_file_path)
        self.local_directory_above = os.path.basename(os.path.dirname(local_file_path))
        self.time_added = datetime.now()
        self.time_ocr_started = None
        self.time_ocr_finished = None
        self.time_upload_started = None
        self.time_finished = None
        self.item_type = item_type
        self.ocr_status = OCRStatus.UNKNOWN
        self.ocr_file = os.path.join(self.local_directory, self.filename_without_extension + "_OCR.pdf")
        self.db_id = None
        self.remote_folder_id = None
        self.remote_drive_id = None

        # PDF Status
        self.pdf_pages = 0
        self.pdf_pages_processed = 0
        logger.debug(f"Created ProcessItem: {self.local_file_path}")
