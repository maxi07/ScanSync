from flask import Blueprint, render_template, request
import math
from shared.logging import logger
from shared.helpers import format_time_difference
from shared.sqlite_wrapper import get_db
from shared.config import config
from datetime import datetime
import locale

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
def index():
    # access_token = get_access_token()
    # if not access_token:
    #     return redirect(url_for('login'))
    # user_info = get_user_info(access_token)
    # return f'Hallo, {user_info["displayName"]}! <br> <a href="/upload">Lade eine Datei hoch</a>'
    try:
        logger.info("Loading dashboard...")
        db = get_db()
        entries_per_page = 8
        try:
            page = request.args.get('page', 1, type=int)  # Get pageination from url args
            total_entries = db.execute('SELECT COUNT(*) FROM scanneddata').fetchone()[0]
            total_pages = math.ceil(total_entries / entries_per_page)
            offset = (page - 1) * entries_per_page
            pdfs = db.execute(
                'SELECT *, DATETIME(created, "localtime") AS local_created, DATETIME(modified, "localtime") AS local_modified FROM scanneddata '
                'ORDER BY created DESC, id DESC '
                'LIMIT :limit OFFSET :offset',
                {'limit': entries_per_page, 'offset': offset}
            ).fetchall()
            logger.debug(f"Loaded {len(pdfs)} pdfs")
        except Exception as e:
            logger.exception(f"Error while loading pdfs: {e}")
            pdfs = []
            total_pages = 1
            page = 1

        # Count total processed PDFs (with status completed)
        try:
            processed_pdfs = db.execute(
                'SELECT COUNT(*) FROM scanneddata '
                'WHERE file_status = "Completed"'
                ).fetchone()[0]
            logger.debug(f"Found {processed_pdfs} processed pdfs")
        except Exception as e:
            logger.exception(f"Error while counting processed pdfs: {e}")
            processed_pdfs = "Unknown"

        # Count total queued PDFs (with status pending)
        try:
            queued_pdfs = db.execute(
                'SELECT COUNT(*) FROM scanneddata '
                'WHERE LOWER(file_status) LIKE "pending"'
                ).fetchone()[0]
            logger.debug(f"Found {queued_pdfs} queued pdfs")
        except Exception as e:
            logger.exception(f"Error while counting queued pdfs: {e}")
            queued_pdfs = "Unknown"

        # Get the latest timestamp from the file_status=pending
        try:
            latest_timestamp_pending = db.execute(
                'SELECT DATETIME(created, "localtime") FROM scanneddata '
                'WHERE file_status = "Pending" '
                'ORDER BY created DESC '
                'LIMIT 1'
                ).fetchone()
            if latest_timestamp_pending is not None:
                logger.debug(f"Found latest timestamp for pending documents: {latest_timestamp_pending[0]}")
                latest_timestamp_pending_string = "Updated " + format_time_difference(latest_timestamp_pending[0])
            else:
                latest_timestamp_pending = db.execute(
                    'SELECT DATETIME(modified, "localtime") FROM scanneddata '
                    'WHERE file_status != "Pending" '
                    'ORDER BY created DESC '
                    'LIMIT 1'
                ).fetchone()

                if latest_timestamp_pending is None:
                    latest_timestamp_pending_string = "Never"
                else:
                    latest_timestamp_pending_string = "Updated " + format_time_difference(latest_timestamp_pending[0])
                logger.debug("No latest timestamp for pending documents found")
        except Exception as e:
            logger.exception(f"Error while getting latest pending timestamp: {e}")
            latest_timestamp_pending_string = "Unknown"

        # Get the latest timestamp from the file_status=completed
        try:
            latest_timestamp_completed = db.execute(
                'SELECT DATETIME(modified, "localtime") FROM scanneddata '
                'WHERE file_status = "Completed" '
                'ORDER BY modified DESC '
                'LIMIT 1'
                ).fetchone()
            if latest_timestamp_completed is not None:
                logger.debug(f"Found latest timestamp for synced documents: {latest_timestamp_completed[0]}")
                latest_timestamp_completed_string = "Updated " + format_time_difference(latest_timestamp_completed[0])
            else:
                latest_timestamp_completed_string = "Never"
                logger.debug("No latest timestamp for synced documents found")
        except Exception as e:
            logger.exception(f"Error while getting latest synced timestamp: {e}")
            latest_timestamp_completed_string = "Unknown"

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

        return render_template('dashboard.html',
                               pdfs=pdfs_dicts,
                               total_pages=total_pages,
                               page=page,
                               first_use=first_use,
                               entries_per_page=entries_per_page,
                               queued_pdfs=queued_pdfs,
                               processed_pdfs=processed_pdfs,
                               latest_timestamp_completed_string=latest_timestamp_completed_string,
                               latest_timestamp_pending_string=latest_timestamp_pending_string)
    except Exception as e:
        logger.exception(e)
        return render_template("dashboard.html",
                               pdfs=[],
                               total_pages=0,
                               page=1,
                               first_use=False,
                               entries_per_page=12,
                               queued_pdfs="Unknown",
                               processed_pdfs="Unknown",
                               latest_timestamp_pending_string="Unknown",
                               latest_timestamp_completed_string="Unknown")