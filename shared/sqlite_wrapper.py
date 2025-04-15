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
        query (str): The SQL Query, e.g. 'SELECT * FROM users WHERE id = ?'
        params (tuple, optional): Query parameters. Defaults to ().
        fetchone (bool, optional): Return one result as dict. Defaults to False.
        fetchall (bool, optional): Return all results as list of dicts. Defaults to False.
        return_last_id (bool, optional): Return the last inserted row ID.

    Returns:
        Query result or None if not fetching.
    """
    try:
        logger.debug(f"Executing SQL query: {query} with params {params}")
        with db_connection() as conn:
            conn.row_factory = sqlite3.Row  # Use Row factory to return rows as dictionaries
            cursor = conn.cursor()
            cursor.execute(query, params)

            if fetchone:
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


db_path = config.get("db.path")
if not os.path.exists(db_path):
    logger.info("Initializing database...")
    with db_connection() as conn:
        with open(config.get("db.schema"), "r") as f:
            conn.executescript(f.read())
    logger.info("Database initialized successfully.")
