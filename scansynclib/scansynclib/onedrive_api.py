from scansynclib.ProcessItem import ProcessItem
from scansynclib.logging import logger
import json
import os
import time
import msal
import requests
import base64
from scansynclib.onedrive_settings import onedrive_settings
from scansynclib.sqlite_wrapper import update_scanneddata_database

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
    try:
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
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error occurred while getting access token: {str(e)}")
    except Exception as e:
        logger.exception(f"An unexpected error occurred in get_access_token: {str(e)}")
    return None


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


def upload_small(item: ProcessItem) -> bool:
    try:
        logger.info(f"Uploading file {item.ocr_file} to OneDrive")

        # Check if file is smaller than 250MB
        file_size = os.path.getsize(item.ocr_file)
        if file_size > 250 * 1024 * 1024:
            logger.error(f"File {item.ocr_file} is larger than 250MB, using chunked upload")
            return upload(item)
        file_size_kb = file_size / 1024
        file_size_mb = file_size_kb / 1024
        logger.debug(f"File size: {file_size} bytes ({file_size_kb:.2f} KB, {file_size_mb:.2f} MB)")

        access_token = get_access_token()
        if not access_token:
            logger.error("No access token available to upload file")
            return False

        upload_url = f"https://graph.microsoft.com/v1.0/drives/{item.remote_drive_id}/items/{item.remote_folder_id}:/{item.filename}:/content?@microsoft.graph.conflictBehavior=rename"
        headers = {'Authorization': 'Bearer ' + access_token, 'Content-Type': 'text/plain'}

        with open(item.ocr_file, 'rb') as file:
            response = requests.put(upload_url, headers=headers, data=file)

        if response.status_code == 201:
            logger.debug("Upload completed successfully")
            webUrl = response.json().get("webUrl")
            if webUrl:
                logger.debug(f"File is accessible at {webUrl}")
                item.web_url = webUrl
                update_scanneddata_database(item, {"web_url": webUrl, "remote_filepath": item.remote_file_path, "file_name": response.json().get("name", item.filename)})
            return True
        else:
            logger.error(f"Failed to upload file: {response.status_code} - {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Request exception occurred during upload: {str(e)}")
    except Exception as e:
        logger.exception(f"An unexpected error occurred during upload: {str(e)}")
    return False


def upload(item: ProcessItem) -> bool:
    try:
        logger.info(f"Uploading file {item.ocr_file} to OneDrive")
        access_token = get_access_token()
        if not access_token:
            logger.error("No access token available to upload file")
            return False

        file_size = os.path.getsize(item.ocr_file)
        upload_session_url = f"https://graph.microsoft.com/v1.0/drives/{item.remote_drive_id}/items/{item.remote_folder_id}:/{item.filename}:/createUploadSession"

        # Create an upload session
        logger.debug(f"Creating upload session for {item.ocr_file} to {upload_session_url}")
        session_response = requests.post(
            upload_session_url,
            headers={'Authorization': 'Bearer ' + access_token},
            json={"item": {"@microsoft.graph.conflictBehavior": "rename"}}
        )

        if session_response.status_code != 200:
            logger.error(f"Failed to create upload session: {session_response.status_code} - {session_response.text}")
            return False

        upload_url = session_response.json().get("uploadUrl")
        if not upload_url:
            logger.error("No upload URL returned in session response")
            return False
        short_url = upload_url[:50] + "..."
        logger.debug(f"Upload session created successfully, upload URL: {short_url}")

        # Upload the file in chunks
        chunk_size = 3276800  # 3.2 MB
        with open(item.ocr_file, 'rb') as file:
            for start in range(0, file_size, chunk_size):
                end = min(start + chunk_size - 1, file_size - 1)
                file.seek(start)
                chunk_data = file.read(end - start + 1)

                headers = {
                    'Authorization': 'Bearer ' + access_token,
                    'Content-Range': f"bytes {start}-{end}/{file_size}"
                }
                percentage = (end + 1) / file_size * 100
                logger.debug(f"Uploading {item.filename} chunk {start}-{end} of {file_size} bytes ({percentage:.2f}%)")
                try:
                    chunk_response = requests.put(upload_url, headers=headers, data=chunk_data)
                except requests.exceptions.RequestException as e:
                    logger.error(f"Request exception during chunk upload: {str(e)}")
                    return False

                if chunk_response.status_code not in (200, 201, 202):
                    logger.error(f"Failed to upload chunk: {chunk_response.status_code} - {chunk_response.text}")
                    return False
                if chunk_response.status_code == 201:
                    logger.debug("Upload completed successfully")
                    logger.debug(f"Response: {chunk_response.json()}")
                    webUrl = chunk_response.json().get("webUrl")
                    if webUrl:
                        logger.debug(f"File is accessible at {webUrl}")
                        update_scanneddata_database(item, {"web_url": webUrl, "remote_filepath": item.remote_file_path})

        logger.info(f"File {item.ocr_file} uploaded successfully to {item.remote_file_path}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Request exception occurred during upload: {str(e)}")
    except Exception as e:
        logger.exception(f"An unexpected error occurred during upload: {str(e)}")
    return False
