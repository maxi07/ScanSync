import pika
from shared.logging import logger
import time
import socket
from shared.ProcessItem import ProcessItem
import pickle

logger.info("Starting OCR service...")


def callback(ch, method, properties, body):
    try:
        item: ProcessItem = pickle.loads(body)
        if not isinstance(item, ProcessItem):
            logger.warning("Received object, that is not of type ProcessItem. Skipping.")
            return
        logger.info(f"Received PDF for OCR: {item.filename}")
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception:
        logger.exception(f"Failed processing {body}.")


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
channel.basic_consume(queue="ocr_queue", on_message_callback=callback)
logger.info("OCR service ready!")
channel.start_consuming()
