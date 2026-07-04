import os
import time
import hashlib
from collections import defaultdict
from scansynclib.logging import logger
import pika
from scansynclib.rabbitmq import RabbitMQClient
from scansynclib.config import config
import json

SCAN_DIR = config.get("smb.path")
RABBITQUEUE = "metadata_queue"
DUPLICATE_DETECTION_WINDOW = 5
logger.info("Starting detection service...")


def get_file_hash(file_path):
    """Berechnet den SHA256-Hash einer Datei"""
    try:
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        logger.debug(f"Calculated hash for {file_path}: {hasher.hexdigest()}")
        return hasher.hexdigest()
    except Exception as e:
        logger.error(f"Error calculating hash for {file_path}: {e}")
        return None


def group_files_by_content(file_paths):
    """Gruppiert Dateien basierend auf ihrem Inhalt (Hash)"""
    file_groups = defaultdict(list)
    for file_path in file_paths:
        file_hash = get_file_hash(file_path)
        if file_hash:
            file_groups[file_hash].append(file_path)
    return file_groups


def get_all_files(directory):
    """Rekursiv alle Dateien in einem Verzeichnis und Unterverzeichnissen abrufen"""
    all_files = set()
    for root, _, files in os.walk(directory):
        for file in files:
            if file.startswith('.'):
                # Ignore hidden files
                continue

            if file.endswith('_OCR.pdf'):
                # Ignore OCR files
                continue
            all_files.add(os.path.join(root, file))
    return all_files


def ensure_scan_directory_exists(directory):
    if not os.path.exists(directory):
        logger.critical(f"{directory} does not exist!")
        exit(1)


def publish_new_files(channel, queue_name, grouped_files):
    """Veröffentlicht gruppierte Dateien, wobei identische Dateien zusammen gesendet werden"""
    for file_hash, file_paths in grouped_files.items():
        if len(file_paths) > 1:
            logger.info(f"Found {len(file_paths)} identical files: {file_paths}")
        else:
            logger.info(f"Found new file: {file_paths[0]}")

        message = json.dumps({
            "file_paths": file_paths,
            "file_hash": file_hash,
            "is_duplicate_group": len(file_paths) > 1
        })

        channel.basic_publish(
            exchange="",
            routing_key=queue_name,
            body=message,
            properties=pika.BasicProperties(delivery_mode=2)  # Make message persistent
        )

        if len(file_paths) > 1:
            logger.info(f"Published {len(file_paths)} identical files as one group to RabbitMQ queue {queue_name}")
        else:
            logger.info(f"Published {file_paths[0]} to RabbitMQ queue {queue_name}")


def main():
    # Imported lazily so that importing this module (e.g. in tests) does not
    # trigger the database initialisation performed by scansynclib.sqlite_wrapper.
    from scansynclib.cleanup import cleanup_dangling_documents

    ensure_scan_directory_exists(SCAN_DIR)
    cleanup_dangling_documents()
    client = RabbitMQClient(name="detection")
    while not client.ensure_connection():
        logger.warning("RabbitMQ is not available. Retrying detection startup in 5 seconds...")
        time.sleep(5)
    client.declare_queue(RABBITQUEUE)

    logger.info(f"Scanning {SCAN_DIR} for new files...")
    known_files = get_all_files(SCAN_DIR)
    pending_files = []
    last_file_time = None

    while True:
        try:
            # Keep the single connection alive and reconnect if it was dropped.
            if not client.is_open():
                logger.warning("RabbitMQ connection lost. Reconnecting...")
                if not client.ensure_connection():
                    logger.warning("RabbitMQ reconnect failed. Retrying in 5 seconds...")
                    time.sleep(5)
                    continue
                client.declare_queue(RABBITQUEUE)
            else:
                # Give pika a chance to send heartbeats between scans.
                client.process_events(1)

            current_files = get_all_files(SCAN_DIR)
            new_files = current_files - known_files

            if new_files:
                pending_files.extend(new_files)
                last_file_time = time.time()
                logger.info(f"Found {len(new_files)} new files, waiting for potential duplicates...")

            # Prüfen, ob genug Zeit vergangen ist, um pending_files zu verarbeiten
            if pending_files and last_file_time and (time.time() - last_file_time >= DUPLICATE_DETECTION_WINDOW):
                logger.info(f"Processing {len(pending_files)} pending files after {DUPLICATE_DETECTION_WINDOW}s wait...")
                grouped_files = group_files_by_content(pending_files)
                if client.is_open():
                    publish_new_files(client.channel, RABBITQUEUE, grouped_files)
                    pending_files = []  # Pending-Liste leeren
                    last_file_time = None

            known_files = current_files

        except Exception as e:
            logger.error(f"Failed scanning {SCAN_DIR}: {e}")

        time.sleep(1)


if __name__ == "__main__":
    main()
