import os
import msal
import requests
import json
from flask import Flask, redirect, request, session, url_for
from dotenv import load_dotenv
import sys
sys.path.append('/app/src')
from shared.logging import logger

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


@app.route('/')
def index():
    access_token = get_access_token()
    if not access_token:
        return redirect(url_for('login'))
    user_info = get_user_info(access_token)
    return f'Hallo, {user_info["displayName"]}! <br> <a href="/upload">Lade eine Datei hoch</a>'


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
