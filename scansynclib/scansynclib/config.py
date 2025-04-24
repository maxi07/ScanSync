import json
from pathlib import Path
from typing import Any
from os.path import expanduser, join
from scansynclib.logging import logger
import fcntl
import os


class Config:
    def __init__(self, config_file):
        self._config_file = config_file
        try:
            with open(config_file) as f:
                self._config = json.load(f)
                logger.debug("Reading config")
        except json.JSONDecodeError as ex:
            logger.exception(f"JSON decode error in config file '{config_file}': {ex}")
            quit(-2)
        except Exception as ex:
            logger.exception(f"Failed reading config: {ex}")
            quit(-2)

    def __iter__(self):
        return iter(self._config.items())

    def __len__(self):
        return len(self._config)

    def get(self, key: str, default=None):
        try:
            keys = key.split('.')
            value = self._config
            for k in keys:
                value = value.get(k, None)
                if value is None:
                    logger.warning(f"Key {key} not found in config")
                    return default
            return value
        except Exception as ex:
            logger.exception(f"Failed reading config: {ex}")
            return default

    def get_filepath(self, key: str, default=None):
        try:
            keys = key.split('.')
            value = self._config
            for k in keys:
                value = value.get(k, None)
                if value is None:
                    return default
            return join(expanduser('~'), value) if isinstance(value, str) else default
        except Exception as ex:
            logger.exception(f"Failed reading config: {ex}")
            return default

    def set(self, key, value):
        try:
            keys = key.split('.')
            curr_dict = self._config
            for k in keys[:-1]:
                curr_dict = curr_dict.setdefault(k, {})
            curr_dict[keys[-1]] = value

            # Locking mechanism
            with open(self._config_file, 'r+') as f:
                fcntl.flock(f, fcntl.LOCK_EX)  # Lock the file exclusively
                # Save the updated config to the file
                with open(self._config_file, 'w') as f_write:
                    json.dump(self._config, f_write, indent=4)
                fcntl.flock(f, fcntl.LOCK_UN)  # Unlock the file after writing

            logger.debug(f"Set config key '{key}' with value '{value}'")
        except Exception as ex:
            logger.exception(f"Failed saving {key} setting to config: {ex}")

    def __getattr__(self, name: str) -> Any:
        if name in self._config:
            return self.get(name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")


CONFIG_PATH = Path(os.environ.get('CONFIG_PATH', '/app/scansynclib/scansynclib/config.json'))
config = Config(str(CONFIG_PATH))
logger.debug(f"Loaded {__name__} module")
