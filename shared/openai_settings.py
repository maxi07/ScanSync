import json
import os
from shared.logging import logger

OPENAI_SETTINGS_FILE = '/app/data/openai_settings.json'


class OpenAISettings:
    def __init__(self, api_key=None):
        self.api_key = api_key

    @classmethod
    def from_file(cls):
        try:
            if os.path.exists(OPENAI_SETTINGS_FILE):
                with open(OPENAI_SETTINGS_FILE, 'r') as file:
                    settings = json.load(file)
                    return cls(
                        settings.get('api_key')
                    )
        except Exception:
            logger.exception("Error loading OneDriveSettings from file")
        return cls()

    def save(self):
        try:
            settings = {
                'api_key': self.api_key
            }
            with open(OPENAI_SETTINGS_FILE, 'w') as file:
                json.dump(settings, file)
            logger.info("OneDriveSettings saved successfully")
        except Exception:
            logger.exception("Error saving OneDriveSettings")


openai_settings = OpenAISettings.from_file()
