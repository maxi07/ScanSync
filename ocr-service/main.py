import pika
from shared_logging.logging import logger
import time
import socket

logger.info("Starting OCR service...")


def callback(ch, method, properties, body):
    logger.info(f"Received message: {body}")
    ch.basic_ack(delivery_tag=method.delivery_tag)


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
