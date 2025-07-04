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
                SELECT
                    d.*,
                    stats.total_entries,
                    stats.processed_pdfs,
                    stats.processing_pdfs,
                    stats.latest_processing,
                    stats.latest_completed,
                    smb.id AS smb_target_id
                FROM (
                    SELECT
                        COUNT(*) AS total_entries,
                        SUM(CASE WHEN status_code = 5 THEN 1 ELSE 0 END) AS processed_pdfs,
                        SUM(CASE WHEN status_code BETWEEN 0 AND 4 THEN 1 ELSE 0 END) AS processing_pdfs,
                        MAX(DATETIME(modified)) AS latest_processing,
                        MAX(CASE WHEN status_code = 5 THEN DATETIME(modified) ELSE NULL END) AS latest_completed
                    FROM scanneddata
                ) stats
                LEFT JOIN (
                    SELECT *,
                        DATETIME(created) AS local_created,
                        DATETIME(modified) AS local_modified
                    FROM scanneddata
                    ORDER BY created DESC, id DESC
                    LIMIT :limit OFFSET :offset
                ) d ON 1=1
                LEFT JOIN smb_onedrive smb ON d.local_filepath = smb.smb_name
            '''
            result = db.execute(query, {'limit': entries_per_page, 'offset': offset}).fetchall()

            # Extract data from the query result
            if result:
                if result[0]['id'] is None:
                    pdfs = []
                else:
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

        smb_tag_colors = [
            "#FF6F61", "#6B5B95", "#88B04B", "#F7CAC9", "#92A8D1",
            "#955251", "#B565A7", "#009B77", "#DD4124", "#45B8AC",
            "#EFC050", "#5B5EA6", "#9B2335", "#DFCFBE", "#55B4B0",
            "#E15D44", "#7FCDCD", "#BC243C", "#C3447A", "#98B4D4",
            "#C46210", "#6C4F3D", "#F0EAD6", "#D65076", "#EDEAE0",
            "#BFD8B8", "#E6B0AA", "#A569BD", "#5499C7", "#48C9B0",
            "#F4D03F", "#DC7633", "#CA6F1E", "#F1948A", "#7DCEA0",
            "#73C6B6", "#85C1E9", "#BB8FCE", "#F7DC6F", "#F0B27A",
            "#E59866", "#EC7063", "#45B39D", "#5DADE2", "#AF7AC5",
            "#F8C471", "#F5B041", "#DC7633", "#A04000", "#D98880",
            "#82E0AA", "#73C6B6", "#76D7C4", "#85C1E9", "#A9CCE3",
            "#D2B4DE", "#F9E79F", "#F7DC6F", "#EDBB99", "#D7BDE2",
            "#AED6F1", "#A3E4D7", "#FAD7A0", "#F5CBA7", "#E59866",
            "#D98880", "#CD6155", "#AF601A", "#7E5109", "#784212",
            "#7D6608", "#196F3D", "#1E8449", "#27AE60", "#52BE80",
            "#229954", "#117864", "#138D75", "#148F77", "#17A589",
            "#45B39D", "#1ABC9C", "#16A085", "#2471A3", "#2E86C1",
            "#5499C7", "#5DADE2", "#85C1E9", "#2471A3", "#1F618D",
            "#2874A6", "#2E86C1", "#3498DB", "#5DADE2", "#85C1E9"
        ]

        return render_template('dashboard.html',
                               pdfs=pdfs_dicts,
                               total_pages=total_pages,
                               page=page,
                               total_entries=total_entries,
                               entries_per_page=entries_per_page,
                               processing_pdfs=processing_pdfs,
                               processed_pdfs=processed_pdfs,
                               latest_timestamp_completed_string=latest_timestamp_completed_string,
                               latest_timestamp_processing_string=latest_timestamp_processing_string,
                               smb_tag_colors=smb_tag_colors,)
    except Exception as e:
        logger.exception(e)
        return render_template("dashboard.html",
                               pdfs=[],
                               total_pages=0,
                               total_entries=0,
                               page=1,
                               entries_per_page=12,
                               processing_pdfs=0,
                               processed_pdfs=0,
                               latest_timestamp_processing_string="Unknown",
                               latest_timestamp_completed_string="Unknown")
