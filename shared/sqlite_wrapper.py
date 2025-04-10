from contextlib import contextmanager
import sqlite3
from shared.config import config
from shared.logging import logger
import os
from flask import g


@contextmanager
def db_connection():
    """Creates SQLite connection and closes it automatically."""
    conn = sqlite3.connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def execute_query(query: str, params=(), fetchone=False, fetchall=False, return_last_id=False):
    """Executes a SQLite3 query and handles cursor.

    Args:
        query (str): The SQL Query, eg. 'SELECT * FROM users WHERE id = ?'
        params (tuple, optional): _description_. Defaults to ().
        fetchone (bool, optional): _description_. Defaults to False.
        fetchall (bool, optional): _description_. Defaults to False.
        return_last_id (bool, optional:) __description__. Returns the id of the just added row.

    Returns:
        Query result or None if not fetching.
    """
    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)

            if fetchone:
                return cursor.fetchone()
            elif fetchall:
                return cursor.fetchall()
            elif return_last_id:
                return cursor.lastrowid

    except Exception:
        logger.exception("Faild sending SQL query.")


def update_scanneddata_database(id: int, update_values: dict):
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
            logger.debug(f"Received values: {update_values} with keys {update_values.keys()} to update SQL db for id {id}")

            # Construct the SET part of the query dynamically based on the dictionary
            set_clause = ', '.join(f'{key} = ?' for key in update_values.keys())

            # Update the scanneddata table
            query = f'UPDATE scanneddata SET {set_clause}, modified = CURRENT_TIMESTAMP WHERE id = ?'
            cursor.execute(query, (*update_values.values(), id))
            logger.debug(f"Updated database scanneddata for id {id} with values {update_values}")

            # Commit the changes and close the connection
            connection.commit()
    except Exception:
        logger.exception(f"Error updating database for id {id}.")


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            db_path,
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row

    return g.db


db_path = os.path.join("src", config.get("db.path"))
if not os.path.exists(db_path):
    logger.info("Initializing database...")
    with db_connection() as conn:
        with open(os.path.join("src", config.get("db.schema")), "r") as f:
            conn.executescript(f.read())
    logger.info("Database initialized successfully.")
