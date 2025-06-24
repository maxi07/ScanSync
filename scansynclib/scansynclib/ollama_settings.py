import json
import os
from scansynclib.logging import logger

OLLAMA_SETTINGS_FILE = '/app/data/ollama_settings.json'


class OllamaSettings:
    def __init__(self, server_url=None, server_port=None, model=None,):
        self.server_url = server_url
        self.server_port = server_port
        self.model = model

    @classmethod
    def from_file(cls):
        try:
            if os.path.exists(OLLAMA_SETTINGS_FILE):
                with open(OLLAMA_SETTINGS_FILE, 'r') as file:
                    settings = json.load(file)
                    return cls(
                        settings.get('server_url'),
                        settings.get('server_port'),
                        settings.get('model')
                    )
            else:
                logger.warning("OllamaSettings file does not exist, probably has not been configured yet.")
        except Exception:
            logger.exception("Error loading OllamaSettings from file")
        return cls()

    def save(self):
        try:
            settings = {
                'server_url': self.server_url,
                'server_port': self.server_port,
                'model': self.model
            }
            with open(OLLAMA_SETTINGS_FILE, 'w') as file:
                json.dump(settings, file)
            logger.info("OllamaSettings saved successfully")
        except Exception:
            logger.exception("Error saving OllamaSettings")

    def delete(self) -> int:
        """
        Deletes the Ollama settings by resetting instance attributes and removing the settings file.

        Returns:
            int: Status code indicating the result of the operation.
                1  - Settings file deleted successfully.
                2  - Settings file does not exist.
               -1  - An error occurred during deletion.
        """
        try:
            self.server_url = None
            self.server_port = None
            self.model = None
            if os.path.exists(OLLAMA_SETTINGS_FILE):
                os.remove(OLLAMA_SETTINGS_FILE)
                logger.info("OllamaSettings deleted successfully")
                return 1
            else:
                logger.warning("Cannot delete OllamaSettings file: does not exist")
                return 2
        except Exception:
            logger.exception("Error deleting OllamaSettings")
            return -1


ollama_settings = OllamaSettings.from_file()
