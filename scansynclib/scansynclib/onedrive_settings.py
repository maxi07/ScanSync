import json
import os
from scansynclib.logging import logger

ONEDRIVE_SETTINGS_FILE = '/app/data/onedrive_settings.json'


class OneDriveSettings:
    def __init__(self, client_id=None, authority=None, scope=None):
        self.client_id = client_id
        self.authority = authority or "https://login.microsoftonline.com/consumers"
        self.scope = scope or ['Files.ReadWrite', 'User.Read']

    @classmethod
    def from_file(cls):
        try:
            if os.path.exists(ONEDRIVE_SETTINGS_FILE):
                with open(ONEDRIVE_SETTINGS_FILE, 'r') as file:
                    settings = json.load(file)
                    return cls(
                        settings.get('clientID'),
                        settings.get('authority'),
                        settings.get('scope'),
                    )
        except Exception:
            logger.exception("Error loading OneDriveSettings from file")
        return cls()

    def save(self):
        try:
            settings = {
                'clientID': self.client_id,
                'authority': self.authority,
                'scope': self.scope,
            }
            with open(ONEDRIVE_SETTINGS_FILE, 'w') as file:
                json.dump(settings, file)
            logger.info("OneDriveSettings saved successfully")
        except Exception:
            logger.exception("Error saving OneDriveSettings")


onedrive_settings = OneDriveSettings.from_file()
