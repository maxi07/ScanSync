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


def test_overwrite_partial_settings_resets_unset_fields():
    old = FileNamingSettings(
        method=FileNamingMethod.OPENAI,
        openai_api_key="sk-abc",
        ollama_server_url="http://host",
        ollama_server_port=12345,
        ollama_model="llama2"
    )

    # Simuliere das Verhalten beim Neuschreiben
    new = FileNamingSettings(
        method=FileNamingMethod.OLLAMA,
        ollama_server_url="http://new-host",
        ollama_server_port=54321,
        ollama_model="llama3"
    )

    # Defaultwert wird zurückgesetzt
    assert new.openai_api_key == ""


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
