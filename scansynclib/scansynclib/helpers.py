from datetime import datetime, timedelta
import os
import pickle
import re
import pika
import socket
import time
from scansynclib.ProcessItem import ProcessItem
from scansynclib.config import config
import pika.exceptions
from scansynclib.logging import logger


def connect_rabbitmq(queue_names: list = None, heartbeat: int = 30):
    """
    Establishes a connection to a RabbitMQ server and declares multiple queues.

    This function attempts to connect to a RabbitMQ server up to 10 times,
    with a 2-second delay between each attempt. If the connection is
    successful, it declares durable queues with the specified names.

    Args:
        queue_names (list): A list of RabbitMQ queue names to declare.
        heartbeat (int): The heartbeat timeout in seconds for the RabbitMQ connection.

    Returns:
        tuple: A tuple containing the RabbitMQ connection and channel objects
               if the connection is successful.
        None: If the connection could not be established after 10 attempts.

    Raises:
        None: The function handles `socket.gaierror` and
              `pika.exceptions.AMQPConnectionError` internally.
    """
    for i in range(10):
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host="rabbitmq", heartbeat=heartbeat))
            channel = connection.channel()
            if queue_names:
                for queue_name in queue_names:
                    channel.queue_declare(queue=queue_name, durable=True)
            channel.basic_qos(prefetch_count=1)
            return connection, channel
        except (socket.gaierror, pika.exceptions.AMQPConnectionError):
            time.sleep(2)
    logger.critical("Couldn't connect to RabbitMQ.")
    return None


def setup_rabbitmq_connection(queue_name):
    try:
        connection, channel = connect_rabbitmq([queue_name])
        logger.debug(f"Connected to RabbitMQ on {channel.channel_number}")
        logger.debug(f"Connected to queue {queue_name}")
        return connection, channel
    except Exception as e:
        logger.critical(f"Failed to connect to RabbitMQ: {e}")
        exit(1)


def reconnect_rabbitmq(queue_name):
    while True:
        try:
            logger.warning("Attempting to reconnect to RabbitMQ...")
            connection, channel = setup_rabbitmq_connection(queue_name)
            logger.info("Reconnected to RabbitMQ successfully.")
            return connection, channel
        except Exception as e:
            logger.critical(f"Failed to reconnect to RabbitMQ: {e}")
            time.sleep(5)  # Wait before retrying


def forward_to_rabbitmq(queue_name: str, item: ProcessItem):
    try:
        connection, channel = connect_rabbitmq([queue_name])
        channel.basic_publish(
            exchange='',
            routing_key=queue_name,
            body=pickle.dumps(item),
            properties=pika.BasicProperties(delivery_mode=2)  # Make message persistent
        )
        logger.info(f"Item {item.filename} forwarded to {queue_name}.")
        connection.close()
    except Exception as e:
        logger.error(f"Failed to forward item {item.filename} to RabbitMQ queue {queue_name}: {e}")


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

    # Trim whitespace and dots before length cutoff
    filename = filename.strip().strip('.')

    # Ensure the filename is at most 50 characters
    if len(filename) > 50:
        filename = filename[:50]

    # Final trim in case length cutoff introduced trailing space or dot
    filename = filename.strip().strip('.')

    # Ensure filename is not empty after sanitization
    if not filename:
        filename = "default_filename"

    return filename
