from datetime import datetime
import locale
import math
import os
import sqlite3
import msal
import requests
import json
from flask import Flask, g, redirect, render_template, request, session, url_for
from dotenv import load_dotenv
import sys
sys.path.append('/app/src')
from shared.logging import logger
from shared.helpers import format_time_difference

from shared.config import config

logger.info("Starting web service...")

app = Flask(__name__)
app.secret_key = os.urandom(24)

TOKEN_FILE = '/app/data/token.json'

# Read environment env
try:
    logger.debug("Loading environment variables")
    load_dotenv()
    CLIENT_ID = os.getenv('CLIENT_ID')
    CLIENT_SECRET = os.getenv('CLIENT_SECRET')
    AUTHORITY = "https://login.microsoftonline.com/consumers"
    SCOPE = ['Files.ReadWrite', 'User.Read']
    REDIRECT_URI = os.getenv('REDIRECT_URI')
except Exception:
    logger.critical("Failed loading environment variable. Please make sure to set the values inside the .env file correctly.")
    exit(1)


def load_token():
    """Reads OneDrive Token from file"""
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'r') as file:
            return json.load(file)
    return None


def save_token(token):
    """Saves token to file"""
    with open(TOKEN_FILE, 'w') as file:
        json.dump(token, file)


def get_access_token():
    """Returns token and renews it if necessary"""
    token_data = load_token()
    if not token_data:
        return None

    if 'access_token' in token_data and 'expires_in' in token_data:
        msal_app = msal.ConfidentialClientApplication(
            CLIENT_ID,
            authority=AUTHORITY,
            client_credential=CLIENT_SECRET
        )
        if token_data.get('expires_in') > 0:
            return token_data['access_token']
        else:
            # token has expired, refresh it
            result = msal_app.acquire_token_by_refresh_token(
                token_data['refresh_token'], scopes=SCOPE
            )
            if "access_token" in result:
                save_token(result)
                return result['access_token']
    return None


def get_db():
    # logger.debug("Creating database connection")
    if 'db' not in g:
        g.db = sqlite3.connect(
            os.path.join("src", config.get("db.path")),
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row

    return g.db


@app.route('/')
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


@app.route('/login')
def login():
    msal_app = msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET
    )
    auth_url = msal_app.get_authorization_request_url(SCOPE, redirect_uri=REDIRECT_URI)
    return redirect(auth_url)


@app.route('/getAToken')
def get_atoken():
    code = request.args.get('code')
    msal_app = msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET
    )
    result = msal_app.acquire_token_by_authorization_code(code, scopes=SCOPE, redirect_uri=REDIRECT_URI)

    if "access_token" in result:
        save_token(result)
        session['user'] = get_user_info(result['access_token'])
        return redirect(url_for('index'))
    return "Fehler bei der Anmeldung!"


def get_user_info(access_token):
    graph_api_url = 'https://graph.microsoft.com/v1.0/me'
    headers = {'Authorization': 'Bearer ' + access_token}
    response = requests.get(graph_api_url, headers=headers)
    return response.json()


@app.route('/upload')
def upload():
    access_token = get_access_token()
    if not access_token:
        return redirect(url_for('login'))

    file_path = '/Users/maxikrause/Downloads/CS50x.png'
    file_name = 'CS50x.png'

    with open(file_path, 'rb') as file:
        headers = {
            'Authorization': 'Bearer ' + access_token,
            'Content-Type': 'application/octet-stream'
        }

        upload_url = f'https://graph.microsoft.com/v1.0/me/drive/root:/{file_name}:/content'
        response = requests.put(upload_url, headers=headers, data=file)

        if response.status_code == 201:
            return f"Datei {file_name} wurde erfolgreich hochgeladen!"
        else:
            return f"Fehler beim Hochladen der Datei: {response.text}"


if __name__ == '__main__':
    app.run(debug=True, port=5001)
