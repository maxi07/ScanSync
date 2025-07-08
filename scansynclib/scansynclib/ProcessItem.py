from enum import Enum
import os
from datetime import datetime
from scansynclib.logging import logger


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
    FILE_NOT_READY = "File Not Ready"
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
    INVALID_FILE = "Invalid File"
    SYNC_FAILED = "Sync Failed"
    DELETED = "Deleted"


class StatusProgressBar:
    """Class to map ProcessStatus to progress bar values."""
    _progress_map = {
        ProcessStatus.FILE_NOT_READY: 0,
        ProcessStatus.READING_METADATA: 1,
        ProcessStatus.OCR_PENDING: 1,
        ProcessStatus.OCR: 2,
        ProcessStatus.FILENAME_PENDING: 2,
        ProcessStatus.FILENAME: 3,
        ProcessStatus.SYNC_PENDING: 3,
        ProcessStatus.SYNC: 4,
        ProcessStatus.COMPLETED: 5,
        ProcessStatus.FAILED: -1,
        ProcessStatus.SYNC_FAILED: -1,
        ProcessStatus.INVALID_FILE: -1,
        ProcessStatus.DELETED: -1,
    }

    @classmethod
    def get_progress(cls, status: ProcessStatus) -> int:
        """Get the progress bar value for a given ProcessStatus."""
        return cls._progress_map.get(status, 0)  # Default to 0 if status is not found


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


class FileNamingStatus(Enum):
    """Enumeration of possible file naming statuses.

    PENDING: File naming is pending.
    PROCESSING: File naming is currently being processed.
    COMPLETED: File naming completed successfully.
    FAILED: File naming failed.
    SKIPPED: File naming was skipped.
    """
    PENDING = "Waiting for file naming"
    PROCESSING = "File naming in progress"
    COMPLETED = "File naming completed"
    FAILED = "File naming failed"
    SKIPPED = "File naming skipped"
    NO_OCR_FILE = "OCR failed on item, no OCR file available"
    NO_PDF_TEXT = "No text found in PDF for file naming"
    NO_SERVER_CONNECTION = "Could not connect to file naming server (ollama or OpenAI)"
    MODEL_NOT_FOUND = "LLM model not found on server"
    AUTHENTICATION_ERROR = "Authentication error with file naming server, check API key or permissions"
    RATE_LIMIT_ERROR = "Rate limit exceeded on file naming server, try again later"


class ItemType(Enum):
    PDF = 1
    IMAGE = 2
    UNKNOWN = 3


class OneDriveDestination:
    def __init__(self, remote_file_path: str, remote_folder_id: str, remote_drive_id: str):
        self.remote_file_path = remote_file_path
        self.remote_directory = None
        self.remote_folder_id = remote_folder_id
        self.remote_drive_id = remote_drive_id


class ProcessItem:
    """ProcessItem represents an item to be processed for OCR and syncing.

    This class contains metadata and status information about the processing
    of a file, including the local and remote file paths, OCR status, sync
    status, timestamps, etc.

    The __init__ method validates the input file and initializes all the
    processing metadata attributes.
    """
    def __init__(self, local_file_path: str, item_type: ItemType, status: ProcessStatus = ProcessStatus.FILE_NOT_READY):
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
        self.preview_image_path = None
        self.web_url = None
        self.additional_local_paths = []
        self.additional_remote_paths = []
        """Additional smb paths related to this item."""

        self.current_uploading = 0
        """Counter of currently uploading files used for web service."""

        self.current_upload_target = None
        """The current upload target for the item, if applicable."""

        self.OneDriveDestinations: list[OneDriveDestination] = []

        self.smb_target_ids = []
        """The IDs of the SMB target, if applicable."""

        self.ocr_db_id = None
        """The ID of the OCR entry in the database, if applicable."""

        self.file_naming_db_id = None
        """The ID of the file naming entry in the database, if applicable."""

        self.file_naming_status = FileNamingStatus.PENDING
        """The status of the file naming process."""

        # PDF Status
        self.pdf_pages = 0
        logger.debug(f"Created ProcessItem: {self.local_file_path}")

    def add_additional_file_paths(self, file_paths: list):
        """Add additional file paths to the item."""
        for path in file_paths:
            try:
                if os.path.exists(path) and path not in self.additional_local_paths:
                    self.additional_local_paths.append(path)
                    self.additional_remote_paths.append(os.path.basename(os.path.dirname(path)))
                    logger.debug(f"Added additional file path: {path}")
                else:
                    logger.warning(f"File does not exist or already added: {path}")
            except Exception as e:
                logger.error(f"Error adding additional file path {path}: {e}")
                continue
