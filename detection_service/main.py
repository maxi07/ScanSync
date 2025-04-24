import os
import time
from scansynclib.logging import logger
import pika
from scansynclib.helpers import reconnect_rabbitmq, setup_rabbitmq_connection
from scansynclib.config import config
import json

SCAN_DIR = config.get("smb.path")
RABBITQUEUE = "metadata_queue"
logger.info("Starting detection service...")


def get_all_files(directory):
    """Rekursiv alle Dateien in einem Verzeichnis und Unterverzeichnissen abrufen"""
    all_files = set()
    for root, _, files in os.walk(directory):
        for file in files:
            all_files.add(os.path.join(root, file))
    return all_files


def ensure_scan_directory_exists(directory):
    if not os.path.exists(directory):
        logger.critical(f"{directory} does not exist!")
        exit(1)


def publish_new_files(channel, queue_name, new_files):
    for new_file in new_files:
        logger.info(f"Found new file: {new_file}")
        message = json.dumps({"file_path": new_file})
        channel.basic_publish(
            exchange="",
            routing_key=queue_name,
            body=message,
            properties=pika.BasicProperties(delivery_mode=2)  # Make message persistent
        )
        logger.info(f"Published {new_file} to RabbitMQ queue {queue_name}")


def main():
    ensure_scan_directory_exists(SCAN_DIR)
    connection, channel = setup_rabbitmq_connection(RABBITQUEUE)

    logger.info(f"Scanning {SCAN_DIR} for new files...")
    known_files = get_all_files(SCAN_DIR)

    while True:
        try:
            # Check if the connection is still alive
            if connection.is_closed or channel.is_closed:
                connection, channel = reconnect_rabbitmq([RABBITQUEUE])
            else:
                connection.process_data_events(1)

            current_files = get_all_files(SCAN_DIR)
            new_files = current_files - known_files

            if new_files:
                publish_new_files(channel, RABBITQUEUE, new_files)

            known_files = current_files

        except Exception as e:
            logger.error(f"Failed scanning {SCAN_DIR}: {e}")

        time.sleep(1)


if __name__ == "__main__":
    main()
