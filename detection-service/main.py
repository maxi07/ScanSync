import os
import time
import socket
import pika.exceptions
from shared_logging.logging import logger
import pika

SCAN_DIR = "/mnt/scans"

logger.info("Starting detection service...")
if not os.path.exists(SCAN_DIR):
    logger.critical(f"{SCAN_DIR} does not exist!")
    exit(1)


# Connect to RabbitMQ
def connect_rabbitmq():
    for i in range(10):
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host="rabbitmq", heartbeat=30))
            channel = connection.channel()
            channel.queue_declare(queue="ocr_queue", durable=True)
            return connection, channel
        except (socket.gaierror, pika.exceptions.AMQPConnectionError):
            time.sleep(2)
    logger.critical("Couldn't connect to RabbitMQ.")
    exit(2)


# Verwende die Verbindung und den Kanal
connection, channel = connect_rabbitmq()
channel = connection.channel()
channel.queue_declare(queue="ocr_queue", durable=True)

logger.info(f"Scanning {SCAN_DIR} for new files...")

known_files = set(os.listdir(SCAN_DIR))

while True:
    try:
        connection.process_data_events(1)
        current_files = set(os.listdir(SCAN_DIR))

        new_files = current_files - known_files
        if new_files:
            for new_file in new_files:
                logger.info(f"Found new file: {new_file}")
                channel.basic_publish(
                    exchange="",
                    routing_key="ocr_queue",
                    body=new_file,
                    properties=pika.BasicProperties(delivery_mode=2)
                )

        known_files = current_files

    except Exception as e:
        logger.error(f"Failed scanning {SCAN_DIR}: {e}")

    time.sleep(1)
