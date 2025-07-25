import pytest
import sys
import os
from enum import Enum

# Add the scansynclib path to allow imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scansynclib'))

from scansynclib.settings_schema import SettingsSchema, FileNamingSettings, FileNamingMethod, OneDriveSettings


def test_default_settings_values():
    """Test that default settings have correct values."""
    settings = SettingsSchema()
    
    # Test file naming defaults
    assert settings.file_naming.method == FileNamingMethod.NONE
    assert settings.file_naming.openai_api_key == ""
    assert settings.file_naming.ollama_server_url == ""
    assert settings.file_naming.ollama_server_port == 11434
    assert settings.file_naming.ollama_model == ""
    
    # Test OneDrive defaults
    assert settings.onedrive.client_id == ""
    assert settings.onedrive.authority == "https://login.microsoftonline.com/consumers"
    assert settings.onedrive.scope == ['Files.ReadWrite', 'User.Read']


def test_file_naming_settings_openai():
    """Test FileNamingSettings with OpenAI configuration."""
    settings = FileNamingSettings(
        method=FileNamingMethod.OPENAI,
        openai_api_key="sk-test-key-123"
    )
    
    assert settings.method == FileNamingMethod.OPENAI
    assert settings.openai_api_key == "sk-test-key-123"
    assert settings.ollama_server_url == ""  # Should remain default
    assert settings.ollama_server_port == 11434  # Should remain default
    assert settings.ollama_model == ""  # Should remain default


def test_file_naming_settings_ollama():
    """Test FileNamingSettings with Ollama configuration."""
    settings = FileNamingSettings(
        method=FileNamingMethod.OLLAMA,
        ollama_server_url="http://localhost",
        ollama_server_port=8080,
        ollama_model="llama3"
    )
    
    assert settings.method == FileNamingMethod.OLLAMA
    assert settings.ollama_server_url == "http://localhost"
    assert settings.ollama_server_port == 8080
    assert settings.ollama_model == "llama3"
    assert settings.openai_api_key == ""  # Should remain default


def test_onedrive_settings_custom():
    """Test OneDriveSettings with custom values."""
    settings = OneDriveSettings(
        client_id="custom-client-id",
        authority="https://custom.authority.com",
        scope=["Files.Read", "User.Read", "Files.Write"]
    )
    
    assert settings.client_id == "custom-client-id"
    assert settings.authority == "https://custom.authority.com"
    assert settings.scope == ["Files.Read", "User.Read", "Files.Write"]


def test_settings_schema_composition():
    """Test that SettingsSchema correctly composes sub-settings."""
    settings = SettingsSchema(
        file_naming=FileNamingSettings(
            method=FileNamingMethod.OLLAMA,
            ollama_server_url="http://test-server",
            ollama_model="test-model"
        ),
        onedrive=OneDriveSettings(
            client_id="test-client-id"
        )
    )
    
    assert settings.file_naming.method == FileNamingMethod.OLLAMA
    assert settings.file_naming.ollama_server_url == "http://test-server"
    assert settings.file_naming.ollama_model == "test-model"
    assert settings.onedrive.client_id == "test-client-id"
    assert settings.onedrive.authority == "https://login.microsoftonline.com/consumers"  # Default


def test_file_naming_method_enum():
    """Test FileNamingMethod enum values."""
    assert FileNamingMethod.NONE.value == "none"
    assert FileNamingMethod.OPENAI.value == "openai"
    assert FileNamingMethod.OLLAMA.value == "ollama"
    
    # Test enum conversion from string
    assert FileNamingMethod("none") == FileNamingMethod.NONE
    assert FileNamingMethod("openai") == FileNamingMethod.OPENAI
    assert FileNamingMethod("ollama") == FileNamingMethod.OLLAMA


def test_settings_serialization():
    """Test that settings can be serialized to JSON and back."""
    original_settings = SettingsSchema(
        file_naming=FileNamingSettings(
            method=FileNamingMethod.OPENAI,
            openai_api_key="sk-test-key",
            ollama_server_port=9090
        ),
        onedrive=OneDriveSettings(
            client_id="test-client",
            scope=["Files.Read", "User.Read"]
        )
    )
    
    # Serialize to JSON
    json_data = original_settings.model_dump_json()
    assert isinstance(json_data, str)
    assert "openai" in json_data
    assert "sk-test-key" in json_data
    assert "test-client" in json_data
    
    # Deserialize from JSON
    loaded_settings = SettingsSchema.model_validate_json(json_data)
    
    # Verify all values are preserved
    assert loaded_settings.file_naming.method == FileNamingMethod.OPENAI
    assert loaded_settings.file_naming.openai_api_key == "sk-test-key"
    assert loaded_settings.file_naming.ollama_server_port == 9090
    assert loaded_settings.onedrive.client_id == "test-client"
    assert loaded_settings.onedrive.scope == ["Files.Read", "User.Read"]


def test_settings_partial_updates():
    """Test that settings can be partially updated."""
    settings = SettingsSchema()
    
    # Update only file naming method
    settings.file_naming.method = FileNamingMethod.OLLAMA
    assert settings.file_naming.method == FileNamingMethod.OLLAMA
    assert settings.file_naming.openai_api_key == ""  # Other fields unchanged
    
    # Update only OneDrive client ID
    settings.onedrive.client_id = "new-client-id"
    assert settings.onedrive.client_id == "new-client-id"
    assert settings.onedrive.authority == "https://login.microsoftonline.com/consumers"  # Unchanged


def test_flatten_settings_function():
    """Test the flatten_settings function logic without Flask dependencies."""
    # Simulate the flatten_settings function logic
    def flatten_settings_logic(settings_obj):
        """Simulate the core logic of flatten_settings."""
        result = {}
        
        # File naming fields
        result['file_naming.method'] = settings_obj.file_naming.method
        result['file_naming.openai_api_key'] = settings_obj.file_naming.openai_api_key
        result['file_naming.ollama_server_url'] = settings_obj.file_naming.ollama_server_url
        result['file_naming.ollama_server_port'] = settings_obj.file_naming.ollama_server_port
        result['file_naming.ollama_model'] = settings_obj.file_naming.ollama_model
        
        # OneDrive fields
        result['onedrive.client_id'] = settings_obj.onedrive.client_id
        result['onedrive.authority'] = settings_obj.onedrive.authority
        result['onedrive.scope'] = settings_obj.onedrive.scope
        
        return result
    
    settings = SettingsSchema(
        file_naming=FileNamingSettings(
            method=FileNamingMethod.OPENAI,
            openai_api_key="test-key"
        ),
        onedrive=OneDriveSettings(
            client_id="test-client"
        )
    )
    
    flat = flatten_settings_logic(settings)
    
    assert flat['file_naming.method'] == FileNamingMethod.OPENAI
    assert flat['file_naming.openai_api_key'] == "test-key"
    assert flat['file_naming.ollama_server_url'] == ""
    assert flat['file_naming.ollama_server_port'] == 11434
    assert flat['onedrive.client_id'] == "test-client"
    assert flat['onedrive.authority'] == "https://login.microsoftonline.com/consumers"


def test_settings_field_type_conversion():
    """Test that different field types are handled correctly."""
    # Test integer field
    settings = FileNamingSettings(ollama_server_port=8080)
    assert isinstance(settings.ollama_server_port, int)
    assert settings.ollama_server_port == 8080
    
    # Test enum field
    settings.method = FileNamingMethod.OLLAMA
    assert isinstance(settings.method, FileNamingMethod)
    assert settings.method == FileNamingMethod.OLLAMA
    
    # Test string field
    settings.openai_api_key = "test-key"
    assert isinstance(settings.openai_api_key, str)
    assert settings.openai_api_key == "test-key"
    
    # Test list field
    onedrive_settings = OneDriveSettings(scope=["Files.Read", "User.Read"])
    assert isinstance(onedrive_settings.scope, list)
    assert onedrive_settings.scope == ["Files.Read", "User.Read"]


def test_settings_advanced_form_processing_logic():
    """Test the logic that would be used in POST request processing."""
    def simulate_form_processing(settings_obj, form_data):
        """Simulate the form processing logic from settings_view."""
        for key, value in form_data.items():
            parts = key.split(".")
            target = settings_obj
            
            # Navigate to the nested object
            for part in parts[:-1]:
                target = getattr(target, part)
            
            attr_name = parts[-1]
            current_value = getattr(target, attr_name)
            
            # Type conversion based on current value type
            if isinstance(current_value, int):
                value = int(value)
            elif isinstance(current_value, list):
                value = [v.strip() for v in value.split(",")]
            elif isinstance(current_value, Enum):
                enum_cls = type(current_value)
                value = enum_cls(value)
            
            setattr(target, attr_name, value)
    
    # Test with various form data
    settings = SettingsSchema()
    
    form_data = {
        'file_naming.method': 'openai',
        'file_naming.openai_api_key': 'sk-new-key',
        'file_naming.ollama_server_port': '8080',
        'onedrive.client_id': 'new-client-id',
        'onedrive.scope': 'Files.Read, User.Read, Files.Write'
    }
    
    simulate_form_processing(settings, form_data)
    
    # Verify the updates
    assert settings.file_naming.method == FileNamingMethod.OPENAI
    assert settings.file_naming.openai_api_key == 'sk-new-key'
    assert settings.file_naming.ollama_server_port == 8080
    assert settings.onedrive.client_id == 'new-client-id'
    assert settings.onedrive.scope == ['Files.Read', 'User.Read', 'Files.Write']


def test_enum_value_error_handling():
    """Test that invalid enum values raise appropriate errors."""
    with pytest.raises(ValueError):
        FileNamingMethod("invalid_method")


def test_port_validation():
    """Test port number validation."""
    # Valid ports
    settings = FileNamingSettings(ollama_server_port=1)
    assert settings.ollama_server_port == 1
    
    settings = FileNamingSettings(ollama_server_port=65535)
    assert settings.ollama_server_port == 65535
    
    # The validation is handled by Pydantic, so invalid values should raise ValidationError
    from pydantic import ValidationError
    
    with pytest.raises(ValidationError):
        FileNamingSettings(ollama_server_port=0)
    
    with pytest.raises(ValidationError):
        FileNamingSettings(ollama_server_port=65536)
    
    with pytest.raises(ValidationError):
        FileNamingSettings(ollama_server_port="not_a_number")


def test_settings_immutability_and_updates():
    """Test that settings can be safely updated without affecting defaults."""
    # Create two settings instances
    settings1 = SettingsSchema()
    settings2 = SettingsSchema()
    
    # Modify one instance
    settings1.file_naming.openai_api_key = "key-for-settings1"
    settings1.onedrive.client_id = "client-for-settings1"
    
    # Verify the other instance is unaffected
    assert settings2.file_naming.openai_api_key == ""
    assert settings2.onedrive.client_id == ""
    
    # Verify the first instance has the changes
    assert settings1.file_naming.openai_api_key == "key-for-settings1"
    assert settings1.onedrive.client_id == "client-for-settings1"
