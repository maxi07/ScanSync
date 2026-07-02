from datetime import datetime, timedelta
import os
import re
from scansynclib.ProcessItem import ProcessItem
from scansynclib.config import config
from scansynclib.logging import logger
# RabbitMQ handling now lives in the unified scansynclib.rabbitmq module. The
# functions are re-exported here for backwards compatibility with existing
# imports (e.g. ``from scansynclib.helpers import forward_to_rabbitmq``).
from scansynclib.rabbitmq import (  # noqa: F401
    RabbitMQClient,
    connect_rabbitmq,
    consume,
    forward_to_rabbitmq,
    publish,
    publish_to_exchange,
)
from pypdf import PdfReader

SMB_TAG_COLORS = [
            '#BC243C', '#CD6155', '#5499C7', '#F7CAC9', '#3498DB',
            '#7E5109', '#DD4124', '#F4D03F', '#2874A6', '#F8C471',
            '#138D75', '#A569BD', '#EDEAE0', '#EC7063', '#EFC050',
            '#AF601A', '#98B4D4', '#FF6F61', '#A3E4D7', '#F0B27A',
            '#48C9B0', '#DFCFBE', '#55B4B0', '#2471A3', '#A04000',
            '#88B04B', '#117864', '#16A085', '#F7DC6F', '#5B5EA6',
            '#F5CBA7', '#F1948A', '#52BE80', '#76D7C4', '#82E0AA',
            '#C3447A', '#F5B041', '#73C6B6', '#CA6F1E', '#1F618D',
            '#85C1E9', '#BFD8B8', '#1ABC9C', '#45B8AC', '#BB8FCE',
            '#27AE60', '#1E8449', '#196F3D', '#784212', '#2E86C1',
            '#D7BDE2', '#E6B0AA', '#148F77', '#7D6608', '#DC7633',
            '#C46210', '#E59866', '#D98880', '#EDBB99', '#17A589',
            '#92A8D1', '#B565A7', '#AF7AC5', '#D2B4DE', '#009B77',
            '#E15D44', '#7FCDCD', '#F9E79F', '#955251', '#A9CCE3',
            '#6C4F3D', '#229954', '#AED6F1', '#FAD7A0', '#6B5B95',
            '#9B2335', '#F0EAD6', '#5DADE2', '#45B39D', '#D65076',
            '#7DCEA0'
        ]


def parse_timestamp(timestamp: str) -> datetime:
    try:
        return datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass

    try:
        return datetime.strptime(timestamp, "%d.%m.%Y %H:%M:%S")
    except ValueError:
        pass

    raise ValueError("Invalid timestamp format")


def format_time_difference(timestamp: str) -> str:
    updated_time = parse_timestamp(timestamp)
    now = datetime.now()
    time_difference = now - updated_time

    if time_difference < timedelta(0):
        raise ValueError("Time difference cannot be negative.")
    elif time_difference < timedelta(seconds=60):
        return "just now"
    elif time_difference < timedelta(minutes=60):
        minutes = time_difference.seconds // 60
        return f"{minutes} {'minute' if minutes == 1 else 'minutes'} ago"
    elif time_difference < timedelta(hours=24):
        hours = time_difference.seconds // 3600
        return f"{hours} {'hour' if hours == 1 else 'hours'} ago"
    elif time_difference < timedelta(days=7):
        days = time_difference.days
        if now.date() - updated_time.date() >= timedelta(days=1):
            days += 1
        return f"{days} {'day' if days == 1 else 'days'} ago"
    elif time_difference < timedelta(days=30):
        weeks = (now.date() - updated_time.date()).days // 7
        return f"{weeks} {'week' if weeks == 1 else 'weeks'} ago"
    elif time_difference < timedelta(days=365):
        months = (now.date() - updated_time.date()).days // 30
        return f"{months} {'month' if months == 1 else 'months'} ago"
    else:
        years = (now.date() - updated_time.date()).days // 365
        return f"{years} {'year' if years == 1 else 'years'} ago"


def to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def move_to_failed(item: ProcessItem):
    """
    Moves a given item to the "failed" directory and performs cleanup operations.

    This function attempts to move the file associated with the provided `ProcessItem`
    to a designated "failed" directory. If the directory does not exist, it will be created.
    Additionally, if an OCR file associated with the item exists, it will be deleted.

    Args:
        item (ProcessItem): The item to be moved to the "failed" directory. This object
                            should have the attributes `local_file_path`, `filename`,
                            and `ocr_file`.

    Raises:
        - No exceptions are raised directly; all exceptions are logged.
    """

    SMB_PATH = config.get("smb.path")
    failedDir = os.path.join(SMB_PATH, config.get("failedDir"))
    if failedDir:
        if not os.path.exists(failedDir):
            try:
                os.makedirs(failedDir)
            except Exception:
                logger.exception(f"Failed to create failed directory {failedDir}")
        try:
            os.rename(item.local_file_path, os.path.join(failedDir, os.path.basename(item.filename)))
        except Exception:
            logger.exception(f"Failed to move item {item.local_file_path} to failed directory {failedDir}")
        logger.info(f"Moved {item.local_file_path} to {failedDir}")

        # Delete additional local paths if they exist
        for additional_path in item.additional_local_paths:
            if os.path.exists(additional_path):
                try:
                    os.remove(additional_path)
                    logger.info(f"Removed additional local path {additional_path}")
                except Exception:
                    logger.exception(f"Failed to remove additional local path {additional_path}")

        # Delete OCR file if present
        if os.path.exists(item.ocr_file):
            try:
                os.remove(item.ocr_file)
                logger.info(f"Removed OCR file {item.ocr_file}")
            except Exception:
                logger.exception(f"Failed to remove OCR file {item.ocr_file}")
    else:
        logger.error("Failed directory not set in config. Skipping move.")


def validate_smb_filename(filename: str) -> str:
    """
    Validates and adjusts a string to be a valid Windows SMB filename (without extension)
    and ensures it is at most 50 characters long.

    Parameters:
    - filename (str): The input filename to validate.

    Returns:
    - str: A valid SMB filename.
    """
    # Remove invalid characters for Windows filenames
    invalid_chars = r'[<>:"/\\|?*\x00-\x1F]'
    filename = re.sub(invalid_chars, '', filename)

    # Remove special chars from the beginning and end
    filename = re.sub(r'^[\s._]+|[\s._]+$', '', filename)

    # Make sure there is no file extension
    filename = os.path.splitext(filename)[0]

    # Trim whitespace and dots before length cutoff
    filename = filename.strip().strip('.')

    # Replace spaces with underscores
    filename = filename.replace(' ', '_')

    # Ensure the filename is at most 50 characters
    if len(filename) > 50:
        filename = filename[:50]

    # Final trim in case length cutoff introduced trailing space or dot
    filename = filename.strip().strip('.')

    # Ensure filename is not empty after sanitization
    if not filename:
        filename = "default_filename"

    return filename


def extract_text(pdf_path: str, max_pages: int = 10, max_chars: int = 50_000) -> str:
    """Extracts text from a PDF file with configurable limits.

    To avoid excessive memory usage on large documents, extraction stops after
    *max_pages* pages have been read or *max_chars* characters have been
    accumulated (whichever comes first).

    Args:
        pdf_path (str): The path to the PDF file.
        max_pages (int): Maximum number of pages to read (default 10).
        max_chars (int): Maximum number of characters to return (default 50 000).

    Returns:
        str: The extracted text from the PDF, truncated to the limits above.
            An empty string is returned if the extraction fails or no text is
            present.
    """
    try:
        reader = PdfReader(pdf_path)
        parts: list[str] = []
        total_chars = 0
        for i, page in enumerate(reader.pages):
            if i >= max_pages:
                break
            page_text = page.extract_text() or ""
            if page_text:
                remaining = max_chars - total_chars
                if remaining <= 0:
                    break
                parts.append(page_text[:remaining])
                total_chars += min(len(page_text), remaining)
                if total_chars >= max_chars:
                    break
        result = "\n".join(parts)
        return result[:max_chars]
    except Exception as ex:
        logger.exception(f"Failed extracting text: {ex}")
        return ""
