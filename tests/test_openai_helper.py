from scansynclib.helpers import validate_smb_filename
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import httpx2 as httpx
from openai import APIStatusError, AuthenticationError, NotFoundError, RateLimitError
import pytest


@pytest.mark.parametrize("input_str", [
    "",  # leer
    "   ",  # nur Leerzeichen
    ".",  # nur Punkt
    "..",  # doppelte Punkte
    "valid_filename",  # bereits gültig
    "   valid_filename   ",  # Trim-Test
    "file.with.dot.",  # Punkt am Ende
    "file/with/slash",  # Slash entfernen
    "file\\with\\backslash",  # Backslash entfernen
    "file:with:colon",  # Doppelpunkt entfernen
    "file*with*asterisk",  # Stern entfernen
    "file?with?question",  # Fragezeichen entfernen
    "file\"with\"quotes",  # Anführungszeichen entfernen
    "file<with<less",  # Kleiner-als-Zeichen entfernen
    "file>with>greater",  # Größer-als-Zeichen entfernen
    "file|with|pipe",  # Pipe entfernen
    "file\x00with\x1Fcontrol",  # Steuerzeichen entfernen
    "    ..file..   ",  # Kombi: Leerzeichen und Punkte
    "🦄📁🐍",  # Emojis
    "übermäßig-länger-als-fünfzig-zeichen-und-noch-ein-bisschen-mehr",
    "1234567890" * 6,  # Viel zu lang
    "valid—filename—with—emdash",  # Unicode Bindestrich
    "dateiname mit leerzeichen",  # Leerzeichen
    "   ⛔️ Ungültig: Datei | Name * 💾  ",  # Kombi mit Symbolen
    ".....hiddenfile",  # viele Punkte vorne
    "filename.",  # Punkt am Ende
    "filename..",  # doppelte Punkte am Ende
    "filename . ",  # Punkt mit Leerzeichen
    "CON",  # Reservierter Name unter Windows
    "file.txt",  # mit Extension (wird nicht entfernt, aber evtl. relevant)
    "support300_BE_no_votelnote</imagine>",  # HTML-Tag
])
def test_validate_smb_filename(input_str):
    result = validate_smb_filename(input_str)

    # 1. Not empty
    assert result != "", f"Result was unexpectedly empty for input: {input_str}"

    # 2. No invalid chars
    assert not any(c in result for c in '<>:"/\\|?*'), f"Invalid chars still in result: {result}"

    # 3. No special chars
    assert all('\x00' > c or c > '\x1F' for c in result), f"Control chars found in result: {result}"

    # 4. Check for invalid chars at beginning or end
    assert not result.startswith(('.', ' ')), f"Starts with invalid char: {result}"
    assert not result.endswith(('.', ' ')), f"Ends with invalid char: {result}"

    # 5. Max 50 chars
    assert len(result) <= 50, f"Filename too long: {len(result)} chars"


@pytest.fixture
def openai_helper(monkeypatch):
    sqlite_stub = ModuleType("scansynclib.sqlite_wrapper")
    sqlite_stub.execute_query = Mock()
    settings_stub = ModuleType("scansynclib.settings")
    settings_stub.settings = SimpleNamespace(file_naming=SimpleNamespace(openai_api_key="test-key"))
    source = Path(__file__).resolve().parents[1] / "scansynclib/scansynclib/openai_helper.py"
    spec = importlib.util.spec_from_file_location("scansynclib._openai_helper_under_test", source)
    module = importlib.util.module_from_spec(spec)
    with monkeypatch.context() as context:
        context.setitem(sys.modules, "scansynclib.sqlite_wrapper", sqlite_stub)
        context.setitem(sys.modules, "scansynclib.settings", settings_stub)
        spec.loader.exec_module(module)
    client = Mock()
    monkeypatch.setattr(module, "OpenAI", Mock(return_value=client))
    monkeypatch.setattr(module, "extract_text", Mock(return_value="Synthetic invoice text"))
    return module, client


@pytest.fixture
def naming_item():
    return SimpleNamespace(filename="scan.pdf", filename_without_extension="scan", ocr_file="scan_OCR.pdf", file_naming_db_id=11)


@pytest.mark.parametrize("raw, expected", [
    ("Rechnung_Beispiel_GmbH_2026-001", "Rechnung_Beispiel_GmbH_2026-00"),
    ("Short_invoice", "Short_invoice"),
    ("A" * 30, "A" * 30),
    ("A" * 80, "A" * 30),
    ("A" * 29 + "_extra", "A" * 29),
    ("A" * 29 + ".extra_text", "A" * 29),
    ("  Invoice:/Example.pdf  ", "InvoiceExample"),
    ("<>:/", "default_filename"),
])
def test_generate_filename_enforces_length_after_sanitizing(openai_helper, naming_item, raw, expected):
    helper, client = openai_helper
    client.responses.create.return_value.output_text = raw

    result = helper.generate_filename_openai(naming_item)

    assert result == expected
    assert 0 < len(result) <= 30
    request = client.responses.create.call_args.kwargs
    assert request["model"] == "gpt-6-luna"
    assert request["reasoning"] == {"effort": "none"}
    assert helper.execute_query.call_args_list[0].args[1] == ("PROCESSING", "gpt-6-luna", "openai", 11)
    assert helper.execute_query.call_args.args[1] == ("COMPLETED", True, 11)
    client.close.assert_called_once()


def api_error(error_type=NotFoundError, status=404, body=None):
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.openai.com/v1/responses"))
    return error_type("Request failed", response=response, body=body)


@pytest.mark.parametrize("body, summary, message", [
    ({"message": "The model has been deprecated. See https://platform.openai.com/docs/deprecations", "code": "model_not_found"},
     "OpenAI model is deprecated", "The model has been deprecated. See https://platform.openai.com/docs/deprecations"),
    ({"error": {"message": "You do not have access to this model", "code": "model_not_found"}},
     "OpenAI model not found or inaccessible", "You do not have access to this model"),
    (None, "OpenAI model not found or inaccessible", ""),
    ({"error": "Unexpected body"}, "OpenAI model not found or inaccessible", ""),
    ({"message": ["Unexpected message"]}, "OpenAI model not found or inaccessible", ""),
])
def test_model_errors_preserve_cause_and_fallback(openai_helper, naming_item, body, summary, message):
    helper, client = openai_helper
    client.responses.create.side_effect = api_error(body=body)

    assert helper.generate_filename_openai(naming_item) == "scan"

    stored_status, description, job_id = helper.execute_query.call_args.args[1]
    assert stored_status == "MODEL_NOT_FOUND"
    assert description.startswith(summary)
    assert "HTTP 404" in description
    assert "gpt-6-luna" in description
    assert message in description
    assert "{'" not in description
    assert job_id == 11
    client.responses.create.assert_called_once()
    client.close.assert_called_once()


def test_key_preserves_model_error(openai_helper):
    helper, client = openai_helper
    client.responses.create.side_effect = api_error(body={"message": "Model has been deprecated", "code": "model_not_found"})

    status, message = helper.test_key("test-key")

    assert status == 404
    assert "Model has been deprecated" in message
    assert "model_not_found" in message
    assert "HTTP 404" in message
    client.close.assert_called_once()


def test_key_uses_same_model_and_disables_reasoning(openai_helper):
    helper, client = openai_helper
    client.responses.create.return_value.output_text = "it works"

    assert helper.test_key("test-key")[0] == 200
    assert client.responses.create.call_args.kwargs["model"] == "gpt-6-luna"
    assert client.responses.create.call_args.kwargs["reasoning"] == {"effort": "none"}
    client.close.assert_called_once()


@pytest.mark.parametrize("error_type, status", [(AuthenticationError, 401), (RateLimitError, 429)])
def test_key_preserves_authentication_and_rate_limit_status(openai_helper, error_type, status):
    helper, client = openai_helper
    client.responses.create.side_effect = api_error(error_type, status)

    assert helper.test_key("test-key")[0] == status
    client.close.assert_called_once()


def test_other_api_errors_preserve_message(openai_helper, naming_item):
    helper, client = openai_helper
    client.responses.create.side_effect = api_error(APIStatusError, 500, {"message": "Temporary service problem"})

    assert helper.generate_filename_openai(naming_item) == "scan"
    stored_status, message, _ = helper.execute_query.call_args.args[1]
    assert stored_status == "FAILED"
    assert "HTTP 500" in message
    assert "Temporary service problem" in message


def test_empty_response_keeps_original_filename(openai_helper, naming_item):
    helper, client = openai_helper
    client.responses.create.return_value.output_text = "   "

    assert helper.generate_filename_openai(naming_item) == "scan"
    assert helper.execute_query.call_args.args[1][0] == "FAILED"
