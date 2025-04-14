import base64
import json
import os
import time
import msal
import requests
from flask import Blueprint, jsonify, request, redirect, session, url_for
from shared.logging import logger
from shared.helpers import to_bool
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
    token["expires_at"] = int(time.time()) + int(token["expires_in"])
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

    expires_at = token_data.get("expires_at", 0)
    now = int(time.time())

    if token_data.get("access_token") and now < expires_at:
        return token_data["access_token"]
    elif token_data.get("refresh_token"):
        logger.debug("Microsoft Token expired, refreshing token")
        result = msal_app.acquire_token_by_refresh_token(
            token_data["refresh_token"],
            scopes=onedrive_settings.scope
        )
        if "access_token" in result:
            save_token(result)
            return result["access_token"]
        else:
            logger.error(f"Failed to refresh Microsoft token: {result}")
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
        if os.path.exists(USER_PROFILE_FILE):
            os.remove(USER_PROFILE_FILE)
            logger.debug("User profile file deleted")
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
        if os.path.exists(USER_IMAGE_FILE):
            os.remove(USER_IMAGE_FILE)
            logger.debug("User profile file deleted")
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


def fetch_graph_api_data(endpoint):
    try:
        access_token = get_access_token()
        if not access_token:
            logger.error(f"No access token available to fetch data from {endpoint}")
            return None

        headers = {'Authorization': 'Bearer ' + access_token}
        response = requests.get(endpoint, headers=headers)
        logger.debug(f"Fetching data from {endpoint}")
        if response.status_code == 200:
            logger.debug(f"Data retrieved successfully from {endpoint}")
            return response.json()
        else:
            logger.error(f"Failed to get data from {endpoint}: {response.status_code} - {response.text}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Request exception occurred while fetching data from {endpoint}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching data from {endpoint}: {str(e)}")
        return None


def get_user_root_drive_id():
    result: json = fetch_graph_api_data(
        'https://graph.microsoft.com/v1.0/me/drive/root/?$select=id'
    )
    if not result or 'id' not in result:
        logger.error(f"Failed reading root id of onedrive. {result}")
        return None
    return result['id']


def get_user_drive_items(id: str):
    result = fetch_graph_api_data(
        'https://graph.microsoft.com/v1.0/me/drive/items/' + id + '/children?$select=id,name,folder,webUrl,parentReference'
    )
    if not result:
        logger.error("Failed to fetch drive items")
        return None
    for item in result["value"]:
        item["shared"] = False
    return result


def get_user_shared_drive_items(driveid: str, folderid: str):
    result = fetch_graph_api_data(
        'https://graph.microsoft.com/v1.0/drives/' + driveid + '/items/' + folderid + '/children?$select=id,name,folder,webUrl,parentReference,remoteItem'
    )
    if not result:
        logger.error("Failed to fetch shared drive items")
        return None
    for item in result["value"]:
        item["shared"] = True
    return result


@onedrive_bp.post('/get-user-drive-items')
def get_user_drive_items_route():
    logger.info("Request to get user drive items")
    logger.debug(f"Request data: {request.data}")
    requested_root = False
    if not request.is_json:
        return jsonify({'error': 'Invalid data'}), 400

    data = request.get_json()
    folder_id = data.get('folderID')
    drive_id = data.get('driveID')
    shared = to_bool(data.get('isSharedWithMe'))
    onedrive_dir_level = data.get('onedriveDirLevel', 1)
    if onedrive_dir_level == 1:
        requested_root = True

    if not folder_id:
        folder_id = get_user_root_drive_id()
        requested_root = True

    if not folder_id:
        logger.error("No folderID provided")
        return jsonify({'error': 'folderID not provided'}), 400

    if shared is True and drive_id and not requested_root:
        # If we are in a shared drive, we need to get the items from the shared drive
        logger.debug(f"Fetching items from shared drive with ID: {drive_id} and folder ID: {folder_id}")
        drive_items = get_user_shared_drive_items(drive_id, folder_id)
    else:
        logger.debug(f"Fetching items from user drive with folder ID: {folder_id}")
        drive_items = get_user_drive_items(folder_id)

    if requested_root:
        # If we are on root, we not only want the onedrive folders, but also the folders shared with me
        shared_items = fetch_graph_api_data("https://graph.microsoft.com/v1.0/me/drive/sharedWithMe?$select=id,name,folder,webUrl,package,parentReference,remoteItem")
        if not shared_items:
            logger.error("Failed to get shared items")
            return jsonify({'error': 'Failed to get shared items'}), 500
        for item in shared_items["value"]:
            item["shared"] = True
        result = drive_items["value"] + shared_items["value"]
    else:
        result = drive_items["value"]

    if not drive_items:
        logger.error("Failed to fetch drive items")
        return jsonify({'error': 'Failed to fetch drive items'}), 500

    return json.dumps(result), 200, {'Content-Type': 'application/json'}
