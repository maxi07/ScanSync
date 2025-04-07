from datetime import datetime, timedelta
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
        return f"{days} {'day' if days == 1 else 'days'} ago"
    elif time_difference < timedelta(days=30):
        weeks = time_difference.days // 7
        return f"{weeks} {'week' if weeks == 1 else 'weeks'} ago"
    elif time_difference < timedelta(days=365):
        months = time_difference.days // 30
        return f"{months} {'month' if months == 1 else 'months'} ago"
    else:
        years = time_difference.days // 365
        return f"{years} {'year' if years == 1 else 'years'} ago"
