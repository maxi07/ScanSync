import base64
import json
import os
import msal
import requests
from flask import Blueprint, request, redirect, session, url_for
from shared.logging import logger
from shared.onedrive_settings import onedrive_settings

onedrive_bp = Blueprint('onedrive', __name__)

TOKEN_FILE = '/app/data/token.json'
USER_PROFILE_FILE = '/app/data/user_profile.json'
USER_IMAGE_FILE = '/app/data/user_image.jpeg'


def load_token():
    """Reads OneDrive Token from file"""
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'r') as file:
            logger.debug("Token file found, loading token")
            return json.load(file)
    return None


def save_token(token):
    """Saves token to file"""
    with open(TOKEN_FILE, 'w') as file:
        json.dump(token, file)
    logger.debug("Token saved to file")


def get_access_token():
    """Returns token and renews it if necessary"""
    token_data = load_token()
    if not token_data:
        logger.debug("No microsoft token found")
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
            logger.debug("Microsoft Token expired, refreshing token")
            result = msal_app.acquire_token_by_refresh_token(
                token_data['refresh_token'], scopes=onedrive_settings.scope
            )
            if "access_token" in result:
                save_token(result)
                return result['access_token']
    return None


@onedrive_bp.route('/login')
def login():
    msal_app = msal.ConfidentialClientApplication(
        onedrive_settings.client_id,
        authority=onedrive_settings.authority,
        client_credential=onedrive_settings.client_secret
    )
    auth_url = msal_app.get_authorization_request_url(onedrive_settings.scope, redirect_uri=onedrive_settings.redirect_uri)
    return redirect(auth_url)


@onedrive_bp.route('/getAToken')
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
        session['user'] = get_user_info()
        logger.info(f"Welcome {session['user']['displayName']}")
        return redirect(url_for('settings.index'))
    return "Fehler bei der Anmeldung!"


def get_user_info(refresh=False):
    if not refresh and os.path.exists(USER_PROFILE_FILE):
        with open(USER_PROFILE_FILE, 'r') as file:
            logger.debug("User info file found, loading cached user info")
            return json.load(file)

    access_token = get_access_token()
    if not access_token:
        logger.error("No access token available to fetch user info")
        return None

    graph_api_url = 'https://graph.microsoft.com/v1.0/me?$select=id,displayName,mail'
    headers = {'Authorization': 'Bearer ' + access_token}
    response = requests.get(graph_api_url, headers=headers)

    if response.status_code == 200:
        logger.debug("User info retrieved successfully")
        user_info = response.json()
        with open(USER_PROFILE_FILE, 'w') as file:
            json.dump(user_info, file)
        return user_info
    else:
        logger.error(f"Failed to get user info: {response.status_code} - {response.text}")
        return None


def get_user_photo(refresh=False):
    if not refresh and os.path.exists(USER_IMAGE_FILE):
        logger.debug("User photo file found, loading cached photo")
        with open(USER_IMAGE_FILE, 'rb') as file:
            image_base64 = base64.b64encode(file.read()).decode("utf-8")
            return image_base64

    access_token = get_access_token()
    if not access_token:
        logger.error("No access token available to fetch user photo")
        return None

    graph_api_url = 'https://graph.microsoft.com/v1.0/me/photo/$value'
    headers = {'Authorization': 'Bearer ' + access_token}
    response = requests.get(graph_api_url, headers=headers)
    if response.status_code == 200:
        logger.debug("User photo retrieved successfully")
        with open(USER_IMAGE_FILE, 'wb') as file:
            file.write(response.content)
        image_base64 = base64.b64encode(response.content).decode("utf-8")
        return image_base64
    else:
        logger.error(f"Failed to get user photo: {response.status_code} - {response.text}")
        return None


@onedrive_bp.route('/upload')
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