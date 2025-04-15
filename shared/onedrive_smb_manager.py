from shared.sqlite_wrapper import execute_query
from shared.logging import logger
from shared.config import config
import os


def add(smb_name: str, drive_id: str, folder_id: str, onedrive_path: str, web_url: str) -> int:
    logger.info("Adding SMB share to database")
    query = "INSERT INTO smb_onedrive (smb_name, drive_id, folder_id, onedrive_path, web_url) VALUES (?, ?, ?, ?, ?)"
    db_id = execute_query(query, (smb_name, drive_id, folder_id, onedrive_path, web_url), return_last_id=True)

    if db_id is None:
        logger.error("Failed to add SMB share to database")
        return -1

    logger.debug(f"SMB share added to database with ID: {db_id}")

    # Create the smb folder if it doesn't exist
    smb_folder = os.path.join(config.get("smb.path"), smb_name)
    if not os.path.exists(smb_folder):
        os.makedirs(smb_folder, mode=777)
        logger.info(f"Created SMB folder at {smb_folder}")
    else:
        logger.warning(f"SMB folder already exists at {smb_folder}")
    return db_id


def get_all():
    logger.info("Getting all SMB shares from database")
    query = "SELECT * FROM smb_onedrive"
    result = execute_query(query, fetchall=True)

    if result is None:
        logger.error("Failed to get SMB shares from database")
        return []

    logger.debug(f"SMB shares retrieved from database: {result}")
    return result
