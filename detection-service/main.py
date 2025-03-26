import os
import time
from shared_logging.logging import logger

SCAN_DIR = "/mnt/scans"
logger.info("Starting detection service...")
if not os.path.exists(SCAN_DIR):
    logger.critical(f"{SCAN_DIR} does not exist!")
    exit(1)

logger.info(f"Scanning {SCAN_DIR} for new files...")

known_files = set(os.listdir(SCAN_DIR))

while True:
    try:
        current_files = set(os.listdir(SCAN_DIR))

        new_files = current_files - known_files
        if new_files:
            for new_file in new_files:
                logger.info(f"Found new file: {new_file}")

        known_files = current_files

    except Exception as e:
        logger.error(f"Failed scanning {SCAN_DIR}: {e}")

    time.sleep(1)
