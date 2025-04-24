from flask import Blueprint, render_template, request, g
import math
from scansynclib.logging import logger
from scansynclib.helpers import format_time_difference
from scansynclib.ProcessItem import StatusProgressBar, ProcessStatus
from scansynclib.config import config
from datetime import datetime
import locale
import sqlite3


dashboard_bp = Blueprint('dashboard', __name__)
db_path = config.get("db.path")


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            db_path,
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row

    return g.db


@dashboard_bp.route('/')
def index():
    try:
        logger.info("Loading dashboard...")
        db = get_db()
        entries_per_page = 8
        try:
            page = request.args.get('page', 1, type=int)  # Get pagination from URL args
            offset = (page - 1) * entries_per_page

            # Single query to fetch all required data
            query = '''
                SELECT *,
                       DATETIME(created) AS local_created,
                       DATETIME(modified) AS local_modified,
                       (SELECT COUNT(*) FROM scanneddata) AS total_entries,
                       (SELECT COUNT(*) FROM scanneddata WHERE status_code = 5) AS processed_pdfs,
                       (SELECT COUNT(*) FROM scanneddata WHERE status_code BETWEEN 0 AND 4) AS processing_pdfs,
                       (SELECT DATETIME(created) FROM scanneddata WHERE status_code < 5 ORDER BY created DESC LIMIT 1) AS latest_processing,
                       (SELECT DATETIME(modified) FROM scanneddata WHERE status_code = 5 ORDER BY modified DESC LIMIT 1) AS latest_completed
                FROM scanneddata
                ORDER BY created DESC, id DESC
                LIMIT :limit OFFSET :offset
            '''
            result = db.execute(query, {'limit': entries_per_page, 'offset': offset}).fetchall()

            # Extract data from the query result
            if result:
                pdfs = result
                total_entries = result[0]['total_entries']
                processed_pdfs = result[0]['processed_pdfs']
                processing_pdfs = result[0]['processing_pdfs']
                latest_timestamp_processing = result[0]['latest_processing']
                latest_timestamp_completed = result[0]['latest_completed']
            else:
                pdfs = []
                total_entries = 0
                processed_pdfs = 0
                processing_pdfs = 0
                latest_timestamp_processing = None
                latest_timestamp_completed = None

            total_pages = math.ceil(total_entries / entries_per_page)

            if not latest_timestamp_processing:
                latest_timestamp_processing = latest_timestamp_completed

            # Format timestamps
            latest_timestamp_processing_string = (
                "Updated " + format_time_difference(latest_timestamp_processing)
                if latest_timestamp_processing else "Never"
            )
            latest_timestamp_completed_string = (
                "Updated " + format_time_difference(latest_timestamp_completed)
                if latest_timestamp_completed else "Never"
            )
        except (sqlite3.Error, Exception) as e:
            logger.error(f"Error processing request: {e}")
            pdfs = []
            total_entries = 0
            processed_pdfs = 0
            processing_pdfs = 0
            latest_timestamp_processing_string = "Unknown"
            latest_timestamp_completed_string = "Unknown"
            total_pages = 0
            page = 1
            offset = 0
            entries_per_page = 12
            logger.exception(e)

        # Set the locale to the user's default
        locale.setlocale(locale.LC_TIME, '')
        logger.debug(f"Locale set to {locale.getlocale()}")

        # Convert sqlite3.Row objects to dictionaries
        pdfs_dicts = list(reversed([dict(pdf) for pdf in pdfs]))

        # Get first use flag
        first_use = bool(config.get("web_service.first_use", False))

        if len(pdfs_dicts) > 0:
            for pdf in pdfs_dicts:
                try:
                    input_datetime_created = datetime.strptime(pdf['local_created'], "%Y-%m-%d %H:%M:%S")
                    input_datetime_modified = datetime.strptime(pdf['local_modified'], "%Y-%m-%d %H:%M:%S")
                    pdf['local_created'] = input_datetime_created.strftime('%d.%m.%Y %H:%M')
                    pdf['local_modified'] = input_datetime_modified.strftime('%d.%m.%Y %H:%M')
                except Exception as ex:
                    logger.exception(f"Failed setting datetime for {pdf['id']}. {ex}")

                try:
                    pdf['status_progressbar'] = StatusProgressBar.get_progress(ProcessStatus(pdf['file_status']))
                except Exception:
                    logger.exception(f"Failed setting progressbar for {pdf['id']}.")

        return render_template('dashboard.html',
                               pdfs=pdfs_dicts,
                               total_pages=total_pages,
                               page=page,
                               first_use=first_use,
                               entries_per_page=entries_per_page,
                               processing_pdfs=processing_pdfs,
                               processed_pdfs=processed_pdfs,
                               latest_timestamp_completed_string=latest_timestamp_completed_string,
                               latest_timestamp_processing_string=latest_timestamp_processing_string,)
    except Exception as e:
        logger.exception(e)
        return render_template("dashboard.html",
                               pdfs=[],
                               total_pages=0,
                               page=1,
                               first_use=False,
                               entries_per_page=12,
                               processing_pdfs=0,
                               processed_pdfs=0,
                               latest_timestamp_processing_string="Unknown",
                               latest_timestamp_completed_string="Unknown")
