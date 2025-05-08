import json
import msal
from flask import Blueprint, jsonify, render_template, request, session
from scansynclib.logging import logger
from scansynclib.helpers import to_bool
from scansynclib.onedrive_settings import onedrive_settings
from scansynclib.onedrive_api import save_token, get_user_info, get_user_root_drive_id, get_user_drive_items, get_user_shared_drive_items, fetch_graph_api_data

onedrive_bp = Blueprint('onedrive', __name__)


@onedrive_bp.route('/login')
def login():
    msal_app = msal.PublicClientApplication(
        onedrive_settings.client_id,
        authority=onedrive_settings.authority,
    )

    logger.debug(f"Starting device flow for OneDrive authentication with scope {onedrive_settings.scope}")
    logger.debug(f"MSAL app: {msal_app}")
    flow = msal_app.initiate_device_flow(scopes=onedrive_settings.scope)
    logger.debug(f"Flow: {flow}")

    if "user_code" not in flow:
        return "Failed starting device authentication flow, user_code missing", 500

    # Token-Polling im Hintergrund oder durch separaten JS-Aufruf
    return render_template("device_login.html", flow=flow)


@onedrive_bp.get('initiate_device_flow')
def initiate_device_flow():
    msal_app = msal.PublicClientApplication(
        onedrive_settings.client_id,
        authority=onedrive_settings.authority,
    )

    logger.debug(f"Starting device flow for OneDrive authentication with scope {onedrive_settings.scope}")
    logger.debug(f"MSAL app: {msal_app}")
    flow = msal_app.initiate_device_flow(scopes=onedrive_settings.scope)
    logger.debug(f"Flow: {flow}")

    if "user_code" not in flow:
        return "Failed starting device authentication flow, user_code missing", 500

    return jsonify(flow)


@onedrive_bp.route('/poll_token')
def poll_token():
    device_code = request.args.get('device_code')
    msal_app = msal.PublicClientApplication(
        onedrive_settings.client_id,
        authority=onedrive_settings.authority,
    )
    try:
        result = msal_app.acquire_token_by_device_flow({
            "device_code": device_code,
            "interval": 5,
            "expires_in": 900
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

    if "access_token" in result:
        save_token(result)
        session['user'] = get_user_info()
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": result.get("error", "unknown")})


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
