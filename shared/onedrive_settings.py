import json
import os
from shared.logging import logger

ONEDRIVE_SETTINGS_FILE = '/app/data/onedrive_settings.json'


class OneDriveSettings:
    def __init__(self, client_id=None, client_secret=None, authority=None, scope=None, redirect_uri=None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.authority = authority or "https://login.microsoftonline.com/consumers"
        self.scope = scope or ['Files.ReadWrite', 'User.Read']
        self.redirect_uri = redirect_uri or "http://localhost:5001/getAToken"

    @classmethod
    def from_file(cls):
        try:
            if os.path.exists(ONEDRIVE_SETTINGS_FILE):
                with open(ONEDRIVE_SETTINGS_FILE, 'r') as file:
                    settings = json.load(file)
                    return cls(
                        settings.get('clientID'),
                        settings.get('clientSecret'),
                        settings.get('authority'),
                        settings.get('scope'),
                        settings.get('redirectURI')
                    )
        except Exception:
            logger.exception("Error loading OneDriveSettings from file")
        return cls()

    def save(self):
        try:
            settings = {
                'clientID': self.client_id,
                'clientSecret': self.client_secret,
                'authority': self.authority,
                'scope': self.scope,
                'redirectURI': self.redirect_uri
            }
            with open(ONEDRIVE_SETTINGS_FILE, 'w') as file:
                json.dump(settings, file)
            logger.info("OneDriveSettings saved successfully")
        except Exception:
            logger.exception("Error saving OneDriveSettings")


onedrive_settings = OneDriveSettings.from_file()
