import json
import os
from scansynclib.logging import logger

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
            else:
                logger.warning("OpenAISettings file does not exist, probably hasnt been configured yet.")
        except Exception:
            logger.exception("Error loading OpenAISettings from file")
        return cls()

    def save(self):
        try:
            settings = {
                'api_key': self.api_key
            }
            with open(OPENAI_SETTINGS_FILE, 'w') as file:
                json.dump(settings, file)
            logger.info("OpenAISettings saved successfully")
        except Exception:
            logger.exception("Error saving OpenAISettings")

    def delete(self) -> int:
        """
        Deletes the OpenAI settings file and clears the API key.

        Returns:
            int: Status code indicating the result of the operation.
                1  - Settings file deleted successfully.
                2  - Settings file does not exist.
               -1  - An error occurred during deletion.
        """
        try:
            self.api_key = None
            if os.path.exists(OPENAI_SETTINGS_FILE):
                os.remove(OPENAI_SETTINGS_FILE)
                logger.info("OpenAISettings deleted successfully")
                return 1
            else:
                logger.warning("OpenAISettings file does not exist")
                return 2
        except Exception:
            logger.exception("Error deleting OpenAISettings")
            return -1


openai_settings = OpenAISettings.from_file()
