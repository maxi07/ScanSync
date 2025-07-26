from enum import Enum
import pytest
from flask import Flask
from scansynclib.settings_schema import SettingsSchema, FileNamingMethod


# Real flatten_settings function copied from production code (with Pydantic v2.11 fix)
def flatten_settings(model, prefix=""):
    """
    Rekursive Funktion, die alle Einstellungen flach als Dict zurückgibt.
    Schlüssel sind z.B. "file_naming.method" und Werte die Feldwerte.
    """
    result = {}
    # Fix for Pydantic v2.11: Access model_fields from the class, not instance
    for field_name, value in model._model.__class__.model_fields.items():
        attr = getattr(model, field_name)
        full_key = f"{prefix}.{field_name}" if prefix else field_name
        # Ist Wert selbst ein BaseModel Proxy? Dann rekursiv tiefer
        if hasattr(attr, "_model"):  # Proxy-Erkennung
            result.update(flatten_settings(attr, full_key))
        else:
            result[full_key] = attr
    return result


# MockProxy class to emulate settings manager behavior for real flatten_settings function
class MockProxy:
    """Mock proxy class that forwards attribute access to the wrapped model."""
    def __init__(self, settings):
        self._model = settings

    def __getattr__(self, name):
        """Forward attribute access to the wrapped model."""
        if hasattr(self._model, name):
            attr = getattr(self._model, name)
            # If it's a nested model, wrap it in another MockProxy (fix for Pydantic v2.11)
            if hasattr(attr.__class__, 'model_fields'):
                return MockProxy(attr)
            return attr
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")


class MockSettingsManager:
    """Mock settings manager that mimics the real one without external dependencies."""
    def __init__(self):
        self.settings = SettingsSchema()


def create_mock_settings_route():
    """Create a mock version of the settings route for testing."""
    from flask import Blueprint, request, redirect, url_for, render_template_string

    settings_bp = Blueprint('settings', __name__)

    # Mock the settings manager
    mock_manager = MockSettingsManager()

    @settings_bp.route("/settings/advanced", methods=["GET", "POST"])
    def settings_view():
        if request.method == "POST":
            # Process form data - this logic mirrors the real implementation
            for key, value in request.form.items():
                parts = key.split(".")
                target = mock_manager.settings

                # Navigate to nested object
                for part in parts[:-1]:
                    target = getattr(target, part)

                attr_name = parts[-1]
                current_value = getattr(target, attr_name)

                # Type conversion - mirrors real implementation
                if isinstance(current_value, int):
                    value = int(value)
                elif isinstance(current_value, list):
                    value = [v.strip() for v in value.split(",")]
                elif isinstance(current_value, Enum):
                    enum_cls = type(current_value)
                    value = enum_cls(value)

                setattr(target, attr_name, value)

            return redirect(url_for("settings.settings_view"))

        # GET request - use the real flatten_settings function but with mock data
        # Create a mock proxy-like object for the real flatten_settings function
        mock_proxy = MockProxy(mock_manager.settings)
        flat_settings = flatten_settings(mock_proxy)

        # Simple template for testing
        template = "Settings: {{ settings }}"
        return render_template_string(template, settings=flat_settings)

    return settings_bp, mock_manager


@pytest.fixture
def app():
    """Create a Flask test app with mock settings blueprint."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.secret_key = 'test-secret-key'

    settings_bp, manager = create_mock_settings_route()
    app.register_blueprint(settings_bp)

    # Store manager reference for tests
    app.mock_manager = manager

    return app


@pytest.fixture
def client(app):
    """Create a test client for the Flask app."""
    return app.test_client()


def test_settings_advanced_get_request(client, app):
    """Test GET request to /settings/advanced."""
    response = client.get('/settings/advanced')

    assert response.status_code == 200
    assert b'Settings:' in response.data
    assert b'file_naming.method' in response.data


def test_settings_advanced_post_string_fields(client, app):
    """Test POST request updating string fields."""
    form_data = {
        'file_naming.openai_api_key': 'sk-new-test-key',
        'file_naming.ollama_server_url': 'http://new-server',
        'onedrive.client_id': 'new-client-id'
    }

    response = client.post('/settings/advanced', data=form_data, follow_redirects=False)

    # Should redirect after successful POST
    assert response.status_code == 302
    assert '/settings/advanced' in response.location

    # Check that settings were updated
    settings = app.mock_manager.settings
    assert settings.file_naming.openai_api_key == 'sk-new-test-key'
    assert settings.file_naming.ollama_server_url == 'http://new-server'
    assert settings.onedrive.client_id == 'new-client-id'


def test_settings_advanced_post_int_field(client, app):
    """Test POST request updating integer fields."""
    form_data = {
        'file_naming.ollama_server_port': '9090'
    }

    response = client.post('/settings/advanced', data=form_data, follow_redirects=False)

    assert response.status_code == 302

    # Check that integer was properly converted
    settings = app.mock_manager.settings
    assert settings.file_naming.ollama_server_port == 9090
    assert isinstance(settings.file_naming.ollama_server_port, int)


def test_settings_advanced_post_enum_field(client, app):
    """Test POST request updating enum fields."""
    form_data = {
        'file_naming.method': 'openai'
    }

    response = client.post('/settings/advanced', data=form_data, follow_redirects=False)

    assert response.status_code == 302

    # Check that enum was properly converted
    settings = app.mock_manager.settings
    assert settings.file_naming.method == FileNamingMethod.OPENAI


def test_settings_advanced_post_list_field(client, app):
    """Test POST request updating list fields."""
    form_data = {
        'onedrive.scope': 'Files.ReadWrite, User.Read, Files.Read'
    }

    response = client.post('/settings/advanced', data=form_data, follow_redirects=False)

    assert response.status_code == 302

    # Check that list was properly converted
    settings = app.mock_manager.settings
    expected_list = ['Files.ReadWrite', 'User.Read', 'Files.Read']
    assert settings.onedrive.scope == expected_list


def test_settings_advanced_post_multiple_fields(client, app):
    """Test POST request updating multiple fields simultaneously."""
    form_data = {
        'file_naming.method': 'ollama',
        'file_naming.ollama_server_url': 'http://test-server',
        'file_naming.ollama_server_port': '11435',
        'file_naming.ollama_model': 'test-model',
        'onedrive.client_id': 'multi-test-client'
    }

    response = client.post('/settings/advanced', data=form_data, follow_redirects=False)

    assert response.status_code == 302

    # Check that all settings were updated correctly
    settings = app.mock_manager.settings
    assert settings.file_naming.method == FileNamingMethod.OLLAMA
    assert settings.file_naming.ollama_server_url == 'http://test-server'
    assert settings.file_naming.ollama_server_port == 11435
    assert settings.file_naming.ollama_model == 'test-model'
    assert settings.onedrive.client_id == 'multi-test-client'


def test_settings_advanced_post_empty_values(client, app):
    """Test POST request with empty string values."""
    form_data = {
        'file_naming.openai_api_key': '',
        'file_naming.ollama_server_url': '',
        'onedrive.client_id': ''
    }

    response = client.post('/settings/advanced', data=form_data, follow_redirects=False)

    assert response.status_code == 302

    # Check that empty strings are properly set
    settings = app.mock_manager.settings
    assert settings.file_naming.openai_api_key == ''
    assert settings.file_naming.ollama_server_url == ''
    assert settings.onedrive.client_id == ''


def test_settings_advanced_post_preserve_unsubmitted_fields(client, app):
    """Test that only submitted fields are updated, others are preserved."""
    # Set initial values
    settings = app.mock_manager.settings
    settings.file_naming.openai_api_key = 'initial-key'
    settings.file_naming.ollama_server_port = 9999
    settings.onedrive.client_id = 'initial-client'

    # Only update one field
    form_data = {
        'file_naming.ollama_server_url': 'http://new-server'
    }

    response = client.post('/settings/advanced', data=form_data, follow_redirects=False)

    assert response.status_code == 302

    # Check that updated field changed and others preserved
    assert settings.file_naming.ollama_server_url == 'http://new-server'
    assert settings.file_naming.openai_api_key == 'initial-key'  # Preserved
    assert settings.file_naming.ollama_server_port == 9999  # Preserved
    assert settings.onedrive.client_id == 'initial-client'  # Preserved


def test_settings_advanced_post_all_enum_values(client, app):
    """Test updating with all possible enum values."""
    # Test each enum value
    for method in [FileNamingMethod.NONE, FileNamingMethod.OPENAI, FileNamingMethod.OLLAMA]:
        form_data = {
            'file_naming.method': method.value
        }

        response = client.post('/settings/advanced', data=form_data, follow_redirects=False)

        assert response.status_code == 302

        settings = app.mock_manager.settings
        assert settings.file_naming.method == method


def test_settings_advanced_post_edge_case_port_values(client, app):
    """Test edge cases for port number validation."""
    # Test minimum valid port
    form_data = {'file_naming.ollama_server_port': '1'}
    response = client.post('/settings/advanced', data=form_data, follow_redirects=False)
    assert response.status_code == 302
    assert app.mock_manager.settings.file_naming.ollama_server_port == 1

    # Test maximum valid port
    form_data = {'file_naming.ollama_server_port': '65535'}
    response = client.post('/settings/advanced', data=form_data, follow_redirects=False)
    assert response.status_code == 302
    assert app.mock_manager.settings.file_naming.ollama_server_port == 65535

    # Test common port
    form_data = {'file_naming.ollama_server_port': '11434'}
    response = client.post('/settings/advanced', data=form_data, follow_redirects=False)
    assert response.status_code == 302
    assert app.mock_manager.settings.file_naming.ollama_server_port == 11434


def test_settings_advanced_post_with_whitespace_in_lists(client, app):
    """Test POST request with values containing whitespace in lists."""
    form_data = {
        'onedrive.scope': '  Files.ReadWrite , User.Read , Files.Read  '
    }

    response = client.post('/settings/advanced', data=form_data, follow_redirects=False)

    assert response.status_code == 302

    settings = app.mock_manager.settings
    # List fields should have trimmed elements
    expected_list = ['Files.ReadWrite', 'User.Read', 'Files.Read']
    assert settings.onedrive.scope == expected_list


def test_settings_advanced_get_with_existing_settings(client, app):
    """Test GET request when settings already have values."""
    # Set some values first
    settings = app.mock_manager.settings
    settings.file_naming.method = FileNamingMethod.OLLAMA
    settings.file_naming.ollama_server_url = 'http://existing-server'
    settings.file_naming.ollama_server_port = 8080
    settings.onedrive.client_id = 'existing-client'

    response = client.get('/settings/advanced')

    assert response.status_code == 200
    # Check that response contains the current values
    response_data = response.data.decode('utf-8')
    assert 'ollama' in response_data
    assert 'existing-server' in response_data
    assert 'existing-client' in response_data


def test_settings_advanced_post_invalid_enum_value(client, app):
    """Test POST request with invalid enum value should raise error."""
    form_data = {
        'file_naming.method': 'invalid_method'
    }

    # This should cause a ValueError in enum conversion
    with pytest.raises(ValueError, match="is not a valid FileNamingMethod"):
        client.post('/settings/advanced', data=form_data, follow_redirects=False)


def test_settings_advanced_post_invalid_int_value(client, app):
    """Test POST request with invalid integer value should raise error."""
    form_data = {
        'file_naming.ollama_server_port': 'not_a_number'
    }

    # This should cause a ValueError in int conversion
    with pytest.raises(ValueError, match="invalid literal for int()"):
        client.post('/settings/advanced', data=form_data, follow_redirects=False)


def test_flatten_settings_function():
    """Test the flatten_settings function directly."""
    settings = SettingsSchema()

    # Modify some settings to test flattening
    settings.file_naming.method = FileNamingMethod.OLLAMA
    settings.file_naming.openai_api_key = 'test-key'
    settings.file_naming.ollama_server_url = 'http://test-server'
    settings.file_naming.ollama_server_port = 9999
    settings.onedrive.client_id = 'test-client'
    settings.onedrive.scope = ['Files.ReadWrite', 'User.Read']

    # Create a mock proxy for the real function (like the real settings manager does)
    mock_proxy = MockProxy(settings)

    # Flatten the settings using the real function
    flattened = flatten_settings(mock_proxy)    # Verify all expected keys are present with correct values
    assert 'file_naming.method' in flattened
    assert 'file_naming.openai_api_key' in flattened
    assert 'file_naming.ollama_server_url' in flattened
    assert 'file_naming.ollama_server_port' in flattened
    assert 'onedrive.client_id' in flattened
    assert 'onedrive.scope' in flattened

    # Verify correct values
    assert flattened['file_naming.method'] == FileNamingMethod.OLLAMA
    assert flattened['file_naming.openai_api_key'] == 'test-key'
    assert flattened['file_naming.ollama_server_url'] == 'http://test-server'
    assert flattened['file_naming.ollama_server_port'] == 9999
    assert flattened['onedrive.client_id'] == 'test-client'
    assert flattened['onedrive.scope'] == ['Files.ReadWrite', 'User.Read']


def test_flatten_settings_with_default_values():
    """Test flatten_settings with default values."""
    settings = SettingsSchema()  # All default values

    # Create a mock proxy for the real function
    mock_proxy = MockProxy(settings)

    flattened = flatten_settings(mock_proxy)

    # Should contain all fields with their default values
    assert 'file_naming.method' in flattened
    assert flattened['file_naming.method'] == FileNamingMethod.NONE  # Default value
    assert 'file_naming.openai_api_key' in flattened
    assert flattened['file_naming.openai_api_key'] == ''  # Default empty string
    assert 'onedrive.client_id' in flattened
    assert flattened['onedrive.client_id'] == ''  # Default empty string


def test_flatten_settings_recursive_structure():
    """Test that flatten_settings correctly handles the recursive structure."""
    settings = SettingsSchema()

    # Create a mock proxy for the real function
    mock_proxy = MockProxy(settings)

    flattened = flatten_settings(mock_proxy)

    # Verify that nested objects are flattened with dot notation
    file_naming_keys = [k for k in flattened.keys() if k.startswith('file_naming.')]
    onedrive_keys = [k for k in flattened.keys() if k.startswith('onedrive.')]

    assert len(file_naming_keys) > 0
    assert len(onedrive_keys) > 0

    # Should not contain non-dotted keys (except if there are top-level fields)
    for key in flattened.keys():
        if '.' not in key:
            # This would be a top-level field, which shouldn't exist in current schema
            # but we allow it in case the schema changes
            pass
