from pydantic import ValidationError
import pytest
from scansynclib.settings import SettingsProxy
from scansynclib.settings_schema import FileNamingSettings, FileNamingMethod, SettingsSchema


def test_default_filenaming_settings():
    s = FileNamingSettings()
    assert s.method == FileNamingMethod.NONE
    assert s.openai_api_key == ""
    assert s.ollama_server_url == ""
    assert s.ollama_server_port == 11434
    assert s.ollama_model == ""


def test_set_openai_settings():
    s = FileNamingSettings(
        method=FileNamingMethod.OPENAI,
        openai_api_key="sk-test"
    )
    assert s.method == FileNamingMethod.OPENAI
    assert s.openai_api_key == "sk-test"
    assert s.ollama_server_url == ""
    assert s.ollama_server_port == 11434
    assert s.ollama_model == ""


def test_set_ollama_settings():
    s = FileNamingSettings(
        method=FileNamingMethod.OLLAMA,
        ollama_server_url="http://localhost",
        ollama_server_port=11434,
        ollama_model="llama3"
    )
    assert s.method == FileNamingMethod.OLLAMA
    assert s.ollama_server_url == "http://localhost"
    assert s.ollama_server_port == 11434
    assert s.ollama_model == "llama3"
    assert s.openai_api_key == ""


def test_schema_defaults():
    settings = SettingsSchema()
    assert isinstance(settings.file_naming, FileNamingSettings)
    assert settings.file_naming.method == FileNamingMethod.NONE


def test_settings_proxy_update_and_read():
    updated = []

    def on_change():
        updated.append(True)

    proxy = SettingsProxy(SettingsSchema(), on_change)

    # Update
    proxy.file_naming.method = FileNamingMethod.OLLAMA
    assert proxy.file_naming.method == FileNamingMethod.OLLAMA
    assert updated

    # Dict export
    d = proxy.dict()
    assert d["file_naming"]["method"] == FileNamingMethod.OLLAMA
    # JSON export
    j = proxy.json()
    assert '"ollama"' in j


def test_serialization_round_trip():
    original = FileNamingSettings(
        method=FileNamingMethod.OLLAMA,
        ollama_server_url="http://ollama",
        ollama_server_port=12345,
        ollama_model="my-model"
    )

    json_data = original.model_dump_json()
    loaded = FileNamingSettings.model_validate_json(json_data)

    assert loaded == original


def test_partial_update_preserves_defaults():
    # Only set method and ollama_server_url
    partial = FileNamingSettings(
        method=FileNamingMethod.OLLAMA,
        ollama_server_url="http://host"
    )

    assert partial.method == FileNamingMethod.OLLAMA
    assert partial.ollama_server_url == "http://host"
    # Defaults remain
    assert partial.ollama_server_port == 11434
    assert partial.ollama_model == ""
    assert partial.openai_api_key == ""


def test_settings_schema_json_roundtrip():
    settings = SettingsSchema(
        file_naming=FileNamingSettings(
            method=FileNamingMethod.OPENAI,
            openai_api_key="sk-abc"
        )
    )
    json_data = settings.model_dump_json()
    loaded = SettingsSchema.model_validate_json(json_data)

    assert loaded == settings
    assert loaded.file_naming.openai_api_key == "sk-abc"
    assert loaded.file_naming.method == FileNamingMethod.OPENAI


def test_settingsproxy_notifies_on_change():
    calls = []

    def on_change():
        calls.append(True)

    proxy = SettingsProxy(SettingsSchema(), on_change)
    assert len(calls) == 0

    # Change nested value
    proxy.file_naming.ollama_server_url = "http://new"
    assert proxy.file_naming.ollama_server_url == "http://new"
    assert len(calls) >= 1


def test_settingsproxy_update_from_json_reflects_changes():
    calls = []

    def on_change():
        calls.append(True)

    proxy = SettingsProxy(SettingsSchema(), on_change)

    new_data = SettingsSchema(
        file_naming=FileNamingSettings(
            method=FileNamingMethod.OLLAMA,
            ollama_server_url="http://updated",
            ollama_model="llama3"
        )
    )

    proxy.update_from_json(new_data.model_dump_json())
    assert proxy.file_naming.method == FileNamingMethod.OLLAMA
    assert proxy.file_naming.ollama_server_url == "http://updated"
    assert proxy.file_naming.ollama_model == "llama3"


def test_ollama_server_port_strict_int_validation():
    # Valid int value
    s = FileNamingSettings(
        method=FileNamingMethod.OLLAMA,
        ollama_server_url="http://localhost",
        ollama_server_port=12345,
        ollama_model="llama3"
    )
    assert s.ollama_server_port == 12345

    # Invalid: string instead of int
    with pytest.raises(ValidationError):
        FileNamingSettings(
            method=FileNamingMethod.OLLAMA,
            ollama_server_url="http://localhost",
            ollama_server_port="12345",
            ollama_model="llama3"
        )

    # Invalid: float instead of int
    with pytest.raises(ValidationError):
        FileNamingSettings(
            method=FileNamingMethod.OLLAMA,
            ollama_server_url="http://localhost",
            ollama_server_port=11434.0,
            ollama_model="llama3"
        )

    # Invalid: None
    with pytest.raises(ValidationError):
        FileNamingSettings(
            method=FileNamingMethod.OLLAMA,
            ollama_server_url="http://localhost",
            ollama_server_port=None,
            ollama_model="llama3"
        )

    # Invalid: negative number (out of bounds)
    with pytest.raises(ValidationError):
        FileNamingSettings(
            method=FileNamingMethod.OLLAMA,
            ollama_server_url="http://localhost",
            ollama_server_port=-1,
            ollama_model="llama3"
        )

    # Invalid: too high number
    with pytest.raises(ValidationError):
        FileNamingSettings(
            method=FileNamingMethod.OLLAMA,
            ollama_server_url="http://localhost",
            ollama_server_port=70000,
            ollama_model="llama3"
        )
