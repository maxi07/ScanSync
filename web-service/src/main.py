import os
import msal
import requests
import json
from flask import Flask, redirect, request, session, url_for
import sys
sys.path.append('/app/src')
from shared.logging import logger
from shared.onedrive_settings import onedrive_settings
from routes.dashboard import dashboard_bp
from routes.sync import sync_bp
from routes.settings import settings_bp
from routes.api import api_bp


logger.info("Starting web service...")

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.register_blueprint(dashboard_bp)
app.register_blueprint(sync_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(api_bp)

TOKEN_FILE = '/app/data/token.json'


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
            onedrive_settings.client_id,
            authority=onedrive_settings.authority,
            client_credential=onedrive_settings.client_secret
        )
        if token_data.get('expires_in') > 0:
            return token_data['access_token']
        else:
            # token has expired, refresh it
            result = msal_app.acquire_token_by_refresh_token(
                token_data['refresh_token'], scopes=onedrive_settings.scope
            )
            if "access_token" in result:
                save_token(result)
                return result['access_token']
    return None


@app.route('/login')
def login():
    msal_app = msal.ConfidentialClientApplication(
        onedrive_settings.client_id,
        authority=onedrive_settings.authority,
        client_credential=onedrive_settings.client_secret
    )
    auth_url = msal_app.get_authorization_request_url(onedrive_settings.scope, redirect_uri=onedrive_settings.redirect_uri)
    return redirect(auth_url)


@app.route('/getAToken')
def get_atoken():
    code = request.args.get('code')
    msal_app = msal.ConfidentialClientApplication(
        onedrive_settings.client_id,
        authority=onedrive_settings.authority,
        client_credential=onedrive_settings.client_secret
    )
    result = msal_app.acquire_token_by_authorization_code(code, scopes=onedrive_settings.scope, redirect_uri=onedrive_settings.redirect_uri)

    if "access_token" in result:
        save_token(result)
        session['user'] = get_user_info(result['access_token'])
        return redirect(url_for('dashboard.index'))
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
