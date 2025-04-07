import pika
import socket
import time
import pika.exceptions
from shared.logging import logger


def connect_rabbitmq(queue_name: str):
    """
    Establishes a connection to a RabbitMQ server and declares a queue.

    This function attempts to connect to a RabbitMQ server up to 10 times, 
    with a 2-second delay between each attempt. If the connection is 
    successful, it declares a durable queue with the specified name.

    Args:
        queue_name (str): The name of the RabbitMQ queue to declare.

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
            connection = pika.BlockingConnection(pika.ConnectionParameters(host="rabbitmq", heartbeat=30))
            channel = connection.channel()
            channel.queue_declare(queue=queue_name, durable=True)
            return connection, channel
        except (socket.gaierror, pika.exceptions.AMQPConnectionError):
            time.sleep(2)
    logger.critical("Couldn't connect to RabbitMQ.")
    return None
