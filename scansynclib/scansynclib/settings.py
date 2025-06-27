# shared/settings.py
import os
import threading
from pydantic import BaseModel
import redis
from scansynclib.settings_schema import SettingsSchema
from typing import cast
from scansynclib.logging import logger

REDIS_KEY = "app:settings"
REDIS_CHANNEL = "__settings_updated__"


class SettingsProxy:
    """
    A proxy class for a Pydantic settings model that intercepts attribute access and modification,
    allowing for change notifications and nested proxying.

    Args:
        model (SettingsSchema): The Pydantic model instance to proxy.
        on_change (Callable): A callback function to be called whenever a setting is changed.

    Attributes:
        _model (SettingsSchema): The proxied Pydantic model.
        _on_change (Callable): The callback to invoke on changes.

    Methods:
        __getattr__(item):
            Returns the attribute from the proxied model. If the attribute is a BaseModel,
            returns a nested SettingsProxy for that attribute.
        __setattr__(key, value):
            Sets the attribute on the proxied model and triggers the on_change callback,
            except for internal attributes.
        dict():
            Returns the dictionary representation of the proxied model.
        json():
            Returns the JSON representation of the proxied model.
        update_from_json(json_str):
            Updates the proxied model from a JSON string and triggers the on_change callback.
    """
    def __init__(self, model: SettingsSchema, on_change):
        self._model = model
        self._on_change = on_change

    def __getattr__(self, item):
        attr = getattr(self._model, item)
        if isinstance(attr, BaseModel):
            return SettingsProxy(attr, lambda *args, **kwargs: self._on_change())
        return attr

    def __setattr__(self, key, value):
        if key in ("_model", "_on_change"):
            object.__setattr__(self, key, value)
            return
        setattr(self._model, key, value)
        logger.debug(f"Setting attribute '{key}' to value: {value}")
        self._on_change()

    def dict(self):
        return self._model.model_dump()

    def json(self):
        return self._model.model_dump_json()

    def update_from_json(self, json_str: str):
        new_model = SettingsSchema.model_validate_json(json_str)
        logger.debug(f"Updating SettingsProxy: {new_model}")
        self._model = new_model


class SettingsManager:
    """
    SettingsManager handles application settings storage, synchronization, and updates using Redis as a backend.

    Attributes:
        _redis (redis.Redis): Redis client instance for settings storage and pub/sub.
        _pubsub (redis.client.PubSub): Redis pub/sub object for listening to settings updates.
        _lock (threading.Lock): Thread lock to ensure thread-safe operations.
        settings (SettingsProxy): Proxy object for accessing and modifying settings.

    Args:
        redis_url (str, optional): Redis connection URL. Defaults to "redis://redis:6379".

    Methods:
        _on_change():
            Callback invoked when settings are changed. Saves the updated settings to Redis and notifies other services via pub/sub.

        _listen_pubsub():
            Listens for settings update messages on the Redis pub/sub channel and reloads settings when updates are detected.

    Usage:
        manager = SettingsManager()
        manager.settings.some_option = "new_value"
    """
    def __init__(self, redis_url=None):
        if not redis_url:
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)
        self._pubsub = self._redis.pubsub()
        self._pubsub.subscribe(REDIS_CHANNEL)
        self._lock = threading.Lock()

        raw = self._redis.get(REDIS_KEY)
        if raw:
            model = SettingsSchema.model_validate_json(raw)
        else:
            model = SettingsSchema()  # Set defaults
            self._redis.set(REDIS_KEY, model.model_dump_json())

        # Proxy for Autoupdate
        self.settings = SettingsProxy(model, self._on_change)

        logger.debug("SettingsManager initialized with settings proxy.")

        # Pub/Sub Listener
        threading.Thread(target=self._listen_pubsub, daemon=True).start()

    def _on_change(self):
        with self._lock:
            # Safe changes to redis
            self._redis.set(REDIS_KEY, self.settings.json())
            # Notify services
            self._redis.publish(REDIS_CHANNEL, "update")
        logger.debug("Settings updated and published to Redis.")

    def _listen_pubsub(self):
        for message in self._pubsub.listen():
            if message["type"] == "message":
                # Get updates and reload
                with self._lock:
                    raw = self._redis.get(REDIS_KEY)
                    if raw:
                        self.settings.update_from_json(raw)


settings_manager = SettingsManager()
settings = settings_manager.settings
settings: SettingsSchema = cast(SettingsSchema, settings_manager.settings)
