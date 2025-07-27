from flask import Blueprint, render_template, request, g
import math
from scansynclib.logging import logger
from scansynclib.helpers import format_time_difference, SMB_TAG_COLORS
from scansynclib.ProcessItem import StatusProgressBar, ProcessStatus
from scansynclib.config import config
from datetime import datetime
import locale
import sqlite3
import json


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
                    SELECT
                        *,
                        additional_smb AS smb_additional_target_ids,
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

            # Match additional SMB targets and create smb_target_ids structure
            new_pdfs = []
            for pdf in pdfs:
                pdf = dict(pdf)  # Make mutable

                # Build smb_target_ids structure for consistent badge generation
                smb_target_ids = []

                # Add main SMB target (from local_filepath)
                if pdf.get('smb_target_id'):
                    smb_target_ids.append({'id': pdf['smb_target_id']})

                # Process additional SMB targets
                names = [s.strip() for s in (pdf.get('smb_additional_target_ids') or '').split(',') if s.strip()]
                additional_target_ids = []
                additional_names = []

                if names:
                    placeholders = ','.join('?' * len(names))
                    rows = db.execute(
                        f"SELECT id, smb_name FROM smb_onedrive WHERE smb_name IN ({placeholders})",
                        names
                    ).fetchall()

                    # Maintain the original order of names
                    for name in names:
                        for row in rows:
                            if row['smb_name'] == name:
                                additional_target_ids.append(row['id'])
                                additional_names.append(row['smb_name'])
                                break

                    # Store matched IDs and names in correct order
                    pdf['smb_additional_target_ids'] = ','.join(str(id) for id in additional_target_ids)
                    pdf['additional_smb'] = additional_names

                    # Add additional targets to smb_target_ids (maintaining order)
                    for target_id in additional_target_ids:
                        smb_target_ids.append({'id': target_id})
                else:
                    pdf['smb_additional_target_ids'] = ''
                    pdf['additional_smb'] = []

                # Set the smb_target_ids structure
                pdf['smb_target_ids'] = smb_target_ids
                new_pdfs.append(pdf)

            pdfs = new_pdfs

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

                try:
                    # Generate badges with complete information server-side
                    badges = []

                    # Process smb_target_ids if available (new structure)
                    if pdf.get('smb_target_ids'):
                        target_ids = pdf['smb_target_ids']
                        if isinstance(target_ids, str):
                            try:
                                target_ids = json.loads(target_ids)
                            except (json.JSONDecodeError, TypeError):
                                target_ids = []

                        # Main badge (first in target_ids)
                        if target_ids and len(target_ids) > 0:
                            main_target = target_ids[0]
                            color_index = (main_target.get('id', 1) - 1) if isinstance(main_target, dict) else (main_target - 1)
                            color = SMB_TAG_COLORS[color_index % len(SMB_TAG_COLORS)] if color_index >= 0 else '#6c757d'

                            web_urls = pdf.get('web_url', [])
                            if isinstance(web_urls, str):
                                web_urls = [url.strip() for url in web_urls.split(',') if url.strip()]
                            elif not isinstance(web_urls, list):
                                web_urls = []

                            remote_paths = pdf.get('remote_filepath', [])
                            if isinstance(remote_paths, str):
                                remote_paths = [path.strip() for path in remote_paths.split(',') if path.strip()]
                            elif not isinstance(remote_paths, list):
                                remote_paths = []

                            main_badge = {
                                "id": f"{pdf['id']}_pdf_smb",
                                "text": pdf.get('local_filepath', 'N/A'),
                                "color": color,
                                "url": web_urls[0] if web_urls else None,
                                "title": remote_paths[0] if remote_paths else 'Open in OneDrive'
                            }
                            badges.append(main_badge)

                            # Additional badges
                            additional_smb = pdf.get('additional_smb', [])
                            if isinstance(additional_smb, str):
                                additional_smb = [name.strip() for name in additional_smb.split(',') if name.strip()]
                            elif not isinstance(additional_smb, list):
                                additional_smb = []

                            for i, target in enumerate(target_ids[1:], 1):  # Skip first element
                                target_id = target.get('id') if isinstance(target, dict) else target
                                color_index = (target_id - 1) if target_id else -1
                                color = SMB_TAG_COLORS[color_index % len(SMB_TAG_COLORS)] if color_index >= 0 else '#6c757d'

                                # Use i-1 to correctly index into additional_smb array
                                additional_badge = {
                                    "id": f"{pdf['id']}_badge_{i}",
                                    "text": additional_smb[i-1] if i-1 < len(additional_smb) else 'N/A',
                                    "color": color,
                                    "url": web_urls[i] if i < len(web_urls) else None,
                                    "title": remote_paths[i] if i < len(remote_paths) else 'Open in OneDrive'
                                }
                                badges.append(additional_badge)
                    else:
                        # Fallback to old structure
                        main_target_id = pdf.get('smb_target_id')
                        if main_target_id:
                            color_index = (main_target_id - 1)
                            color = SMB_TAG_COLORS[color_index % len(SMB_TAG_COLORS)] if color_index >= 0 else '#6c757d'

                            main_badge = {
                                "id": f"{pdf['id']}_pdf_smb",
                                "text": pdf.get('local_filepath', 'N/A'),
                                "color": color,
                                "url": None,
                                "title": 'Open in OneDrive'
                            }
                            badges.append(main_badge)

                    pdf['badges'] = badges
                    logger.debug(f"Generated badges for PDF {pdf['id']}: {badges}")

                except Exception as ex:
                    logger.exception(f"Failed setting badges for {pdf['id']}. {ex}")
                    pdf['badges'] = []

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
                               smb_tag_colors=SMB_TAG_COLORS,)
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
