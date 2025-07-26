from scansynclib.sqlite_wrapper import execute_query
from scansynclib.logging import logger
from scansynclib.config import config
import os
import shutil


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
        os.makedirs(smb_folder, mode=0o777)
        logger.info(f"Created SMB folder at {smb_folder}")
    else:
        logger.warning(f"SMB folder already exists at {smb_folder}")
    return db_id


def edit(smb_id: int, smb_name: str, drive_id: str, folder_id: str, onedrive_path: str, web_url: str) -> bool:
    logger.info(f"Editing SMB share with ID {smb_id} in database")

    # get old smb name
    query = "SELECT smb_name FROM smb_onedrive WHERE id = ?"
    old_smb_name = execute_query(query, (smb_id,), fetchone=True)
    if old_smb_name is None:
        logger.error("Failed to get old SMB name from database")
        return False
    old_smb_name = old_smb_name.get("smb_name")
    logger.debug(f"Old SMB name: {old_smb_name}")

    # Check if the new SMB name is different from the old one
    if smb_name != old_smb_name:
        # Rename the folder on the filesystem
        old_smb_folder = os.path.join(config.get("smb.path"), old_smb_name)
        new_smb_folder = os.path.join(config.get("smb.path"), smb_name)

        if os.path.exists(old_smb_folder):
            os.rename(old_smb_folder, new_smb_folder)
            logger.info(f"Renamed SMB folder from {old_smb_folder} to {new_smb_folder}")
        else:
            logger.warning(f"Old SMB folder does not exist: {old_smb_folder}")
            # Create the new folder if it doesn't exist
            if not os.path.exists(new_smb_folder):
                os.makedirs(new_smb_folder, mode=0o777)
                logger.info(f"Created new SMB folder at {new_smb_folder}")
            else:
                logger.warning(f"New SMB folder already exists: {new_smb_folder}")
    else:
        logger.debug("SMB name has not changed, no need to rename folder")

    # Update the SMB share in the database
    query = "UPDATE smb_onedrive SET smb_name = ?, drive_id = ?, folder_id = ?, onedrive_path = ?, web_url = ? WHERE id = ?"
    result = execute_query(query, (smb_name, drive_id, folder_id, onedrive_path, web_url, smb_id))

    if result is not True:
        logger.error("Failed to edit SMB share in database")
        return False

    logger.debug(f"SMB share with ID {smb_id} edited successfully")
    return True


def delete(smb_id: int) -> bool:
    logger.info(f"Deleting SMB share with ID {smb_id} from database")

    # Get the SMB name to delete the folder
    query = "SELECT smb_name FROM smb_onedrive WHERE id = ?"
    smb_name = execute_query(query, (smb_id,), fetchone=True)
    if smb_name is None:
        logger.error("Failed to get SMB name from database")
        return False
    smb_name = smb_name.get("smb_name")

    # Delete the folder from the filesystem
    smb_folder = os.path.join(config.get("smb.path"), smb_name)
    if os.path.exists(smb_folder):
        shutil.rmtree(smb_folder, ignore_errors=True)
        logger.info(f"Deleted SMB folder at {smb_folder}")
    else:
        logger.warning(f"SMB folder does not exist: {smb_folder}")

    # Delete the SMB share from the database
    query = "DELETE FROM smb_onedrive WHERE id = ?"
    result = execute_query(query, (smb_id,))

    if result is not True:
        logger.error("Failed to delete SMB share from database")
        return False

    logger.debug(f"SMB share with ID {smb_id} deleted successfully")
    return True


def get_all(order=""):
    logger.info("Getting all SMB shares from database")
    # Check if order is valid
    if order and order not in ["smb_name ASC", "smb_name DESC", "created ASC", "created DESC"]:
        logger.error(f"Invalid order parameter: {order}")
        order = "created ASC"
    query = "SELECT * FROM smb_onedrive ORDER BY " + (order if order else "id")
    result = execute_query(query, fetchall=True)

    if result is None:
        logger.error("Failed to get SMB shares from database")
        return []

    logger.debug(f"SMB shares retrieved from database: {result}")
    return result


def get_by_id(smb_id: int):
    """Get a specific SMB share by its ID."""
    logger.info(f"Getting SMB share with ID {smb_id} from database")
    query = "SELECT * FROM smb_onedrive WHERE id = ?"
    result = execute_query(query, (smb_id,), fetchone=True)

    if result is None:
        logger.warning(f"SMB share with ID {smb_id} not found in database")
        return None

    logger.debug(f"SMB share retrieved from database: {result}")
    return result
