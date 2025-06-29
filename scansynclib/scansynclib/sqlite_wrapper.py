from contextlib import contextmanager
import pickle
import sqlite3
import pika.exceptions
from scansynclib.config import config
from scansynclib.logging import logger
from scansynclib.ProcessItem import ProcessItem, StatusProgressBar
import os
import pika

# Initialize RabbitMQ connection and channel globally
rabbit_connection = None
rabbit_channel = None


@contextmanager
def db_connection():
    """Creates SQLite connection and closes it automatically."""
    conn = sqlite3.connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def execute_query(
    query: str,
    params=(),
    fetchone=False,
    fetchall=False,
    return_last_id=False,
    return_scalar=False
):
    """Executes a SQLite3 query and handles cursor.

    Args:
        query (str): The SQL Query, e.g. 'SELECT * FROM users WHERE id = ?'
        params (tuple, optional): Query parameters. Defaults to ().
        fetchone (bool, optional): Return one result as dict. Defaults to False.
        fetchall (bool, optional): Return all results as list of dicts. Defaults to False.
        return_last_id (bool, optional): Return the last inserted row ID.
        return_scalar (bool, optional): Return the first column of the first row (e.g. for COUNT(*)).

    Returns:
        Query result or None if not fetching.
    """
    try:
        logger.debug(f"Executing SQL query: {query} with params {params}")
        with db_connection() as conn:
            conn.row_factory = sqlite3.Row  # Use Row factory to return rows as dictionaries
            cursor = conn.cursor()
            cursor.execute(query, params)

            if return_scalar:
                row = cursor.fetchone()
                return row[0] if row else None
            elif fetchone:
                row = cursor.fetchone()
                return dict(row) if row else None
            elif fetchall:
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
            elif return_last_id:
                logger.debug(f"Returning last row id: {cursor.lastrowid}")
                return cursor.lastrowid
            else:
                return True
    except Exception:
        logger.exception("Failed executing SQL query.")
        return None


def update_scanneddata_database(item: ProcessItem, update_values: dict):
    """Updates the scanned data database table with new values for the given ID.

    Connects to the SQLite database, constructs a dynamic SQL query to update
    the row with the given ID and the provided update_values dictionary.
    Commits the changes and closes the connection.

    Handles any errors and logs exceptions.
    """
    try:
        with db_connection() as connection:
            # Create a cursor object
            cursor = connection.cursor()
            logger.debug(f"Received values: {update_values} with keys {update_values.keys()} to update SQL db for id {item.db_id}")

            # Construct the SET part of the query dynamically based on the dictionary
            set_clause = ', '.join(f'{key} = ?' for key in update_values.keys())

            # Update the scanneddata table
            query = f"UPDATE scanneddata SET {set_clause}, modified = DATETIME('now', 'localtime'), status_code = ? WHERE id = ?"
            cursor.execute(query, (*update_values.values(), StatusProgressBar().get_progress(item.status), item.db_id))
            logger.debug(f"Updated database scanneddata for id {item.db_id} with values {update_values}")

            # Commit the changes and close the connection
            connection.commit()
            notify_sse_clients(item)
    except Exception:
        logger.exception(f"Error updating database for id {id}.")


def initialize_rabbitmq():
    global rabbit_connection, rabbit_channel
    try:
        rabbit_connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
        rabbit_channel = rabbit_connection.channel()
        # Declare the fanout exchange (idempotent)
        rabbit_channel.exchange_declare(exchange='sse_updates_fanout', exchange_type='fanout')
        logger.info("RabbitMQ connection initialized successfully.")
    except Exception:
        logger.exception("Failed to initialize RabbitMQ connection.")


def notify_sse_clients(item: ProcessItem, retry_count=0, max_retries=3):
    try:
        if rabbit_channel is None or rabbit_connection is None or rabbit_connection.is_closed:
            initialize_rabbitmq()
        rabbit_channel.basic_publish(
            exchange='sse_updates_fanout',
            routing_key='',  # fanout ignores this
            body=pickle.dumps(item),
        )
    except pika.exceptions.StreamLostError:
        if retry_count < max_retries:
            logger.warning(f"RabbitMQ connection lost. Retrying... Attempt {retry_count + 1}/{max_retries}")
            initialize_rabbitmq()
            notify_sse_clients(item, retry_count=retry_count + 1, max_retries=max_retries)
        else:
            logger.error("Max retries reached. Failed to send update to SSE queue.")
    except Exception:
        logger.exception("Error sending update to SSE queue.")


db_path = config.get("db.path")

logger.info("Initializing database...")
with db_connection() as conn:
    logger.debug(f"Working with database at {os.path.abspath(db_path)}")
    schema_path = "scansynclib/scansynclib/db/schema.sql"
    if not os.path.exists(schema_path):
        logger.error(f"Schema file not found: {schema_path}")
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    with open(schema_path, "r") as f:
        conn.executescript(f.read())
logger.info("Database initialized successfully.")
