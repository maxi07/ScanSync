import pickle
import sys
import types
from types import SimpleNamespace

import pytest
from pika import exceptions as pika_exceptions

from scansynclib.settings_schema import FileNamingMethod


# Importing the service pulls in scansynclib.sqlite_wrapper, which initializes a
# real SQLite database at import time. That database is not available in the unit
# test environment, so replace the module with a stub. The query helpers are
# mocked per-test anyway.
_sqlite_stub = types.ModuleType("scansynclib.sqlite_wrapper")
_sqlite_stub.execute_query = lambda *args, **kwargs: None
_sqlite_stub.update_scanneddata_database = lambda *args, **kwargs: None

_original_sqlite_wrapper = sys.modules.get("scansynclib.sqlite_wrapper")
sys.modules["scansynclib.sqlite_wrapper"] = _sqlite_stub

_openai_stub = types.ModuleType("scansynclib.openai_helper")
_openai_stub.generate_filename_openai = lambda item: item.filename_without_extension
_original_openai_helper = sys.modules.get("scansynclib.openai_helper")
sys.modules["scansynclib.openai_helper"] = _openai_stub

_ollama_stub = types.ModuleType("scansynclib.ollama_helper")
_ollama_stub.generate_filename_ollama = lambda item: item.filename_without_extension
_original_ollama_helper = sys.modules.get("scansynclib.ollama_helper")
sys.modules["scansynclib.ollama_helper"] = _ollama_stub

_settings_stub = types.ModuleType("scansynclib.settings")
_settings_stub.settings = SimpleNamespace(
    file_naming=SimpleNamespace(
        method=FileNamingMethod.NONE,
        openai_api_key="",
        ollama_server_url="",
        ollama_server_port=11434,
        ollama_model="",
    )
)
_original_settings = sys.modules.get("scansynclib.settings")
sys.modules["scansynclib.settings"] = _settings_stub


def teardown_module(module):
    if _original_sqlite_wrapper is None:
        sys.modules.pop("scansynclib.sqlite_wrapper", None)
    else:
        sys.modules["scansynclib.sqlite_wrapper"] = _original_sqlite_wrapper
    if _original_openai_helper is None:
        sys.modules.pop("scansynclib.openai_helper", None)
    else:
        sys.modules["scansynclib.openai_helper"] = _original_openai_helper
    if _original_ollama_helper is None:
        sys.modules.pop("scansynclib.ollama_helper", None)
    else:
        sys.modules["scansynclib.ollama_helper"] = _original_ollama_helper
    if _original_settings is None:
        sys.modules.pop("scansynclib.settings", None)
    else:
        sys.modules["scansynclib.settings"] = _original_settings


import file_naming_service.main as fn_main  # noqa: E402
from scansynclib.ProcessItem import ProcessItem, ItemType, FileNamingStatus, ProcessStatus  # noqa: E402


@pytest.fixture
def item(tmp_path):
    file_path = tmp_path / "doc.pdf"
    file_path.write_bytes(b"%PDF-1.4 test")
    ocr_file_path = tmp_path / "doc_OCR.pdf"
    ocr_file_path.write_bytes(b"%PDF-1.4 ocr")
    process_item = ProcessItem(str(file_path), ItemType.PDF)
    process_item.ocr_file = str(ocr_file_path)
    process_item.db_id = 7
    process_item.file_naming_db_id = 11
    process_item.file_naming_status = FileNamingStatus.PROCESSING
    return process_item


@pytest.mark.parametrize(
    "stored_status, expected",
    [
        ("COMPLETED", FileNamingStatus.COMPLETED),
        ("NO_SERVER_CONNECTION", FileNamingStatus.NO_SERVER_CONNECTION),
        ("AUTHENTICATION_ERROR", FileNamingStatus.AUTHENTICATION_ERROR),
    ],
)
def test_get_latest_status_returns_db_value(item, mocker, stored_status, expected):
    mocker.patch.object(fn_main, "execute_query", return_value=stored_status)

    assert fn_main.get_latest_file_naming_status(item) == expected


def test_get_latest_status_falls_back_when_db_empty(item, mocker):
    mocker.patch.object(fn_main, "execute_query", return_value=None)

    assert fn_main.get_latest_file_naming_status(item) == FileNamingStatus.PROCESSING


def test_get_latest_status_falls_back_on_unknown_value(item, mocker):
    mocker.patch.object(fn_main, "execute_query", return_value="NOT_A_REAL_STATUS")

    assert fn_main.get_latest_file_naming_status(item) == FileNamingStatus.PROCESSING


def test_callback_with_non_processitem_does_not_crash(mocker):
    """A message that does not deserialize to a ProcessItem must be acknowledged
    and skipped without touching the database or forwarding to the next queue."""
    execute_query = mocker.patch.object(fn_main, "execute_query")
    forward = mocker.patch.object(fn_main, "forward_to_rabbitmq")
    mocker.patch.object(fn_main, "update_scanneddata_database")

    ch = mocker.Mock()
    method = mocker.Mock()
    method.delivery_tag = 123
    body = pickle.dumps({"not": "a process item"})

    fn_main.callback(ch, method, None, body)

    ch.basic_ack.assert_called_once_with(delivery_tag=123)
    execute_query.assert_not_called()
    forward.assert_not_called()


def test_callback_continues_pipeline_when_ack_fails(item, mocker):
    mocker.patch.object(fn_main.settings.file_naming, "method", FileNamingMethod.OPENAI)
    mocker.patch.object(fn_main.settings.file_naming, "openai_api_key", "test-key")
    mocker.patch.object(fn_main, "generate_filename_openai", return_value="renamed")
    execute_query = mocker.patch.object(fn_main, "execute_query", return_value=item.file_naming_db_id)
    mocker.patch.object(fn_main, "get_latest_file_naming_status", return_value=FileNamingStatus.COMPLETED)
    update = mocker.patch.object(fn_main, "update_scanneddata_database")
    forward = mocker.patch.object(fn_main, "forward_to_rabbitmq")

    ch = mocker.Mock()
    ch.basic_ack.side_effect = pika_exceptions.AMQPError("lost connection")
    method = mocker.Mock()
    method.delivery_tag = 456

    fn_main.callback(ch, method, None, pickle.dumps(item))

    ch.basic_ack.assert_called_once_with(delivery_tag=456)
    execute_query.assert_called()
    update.assert_called_once()
    updated_item = update.call_args.args[0]
    assert update.call_args.args[1] == {"file_status": ProcessStatus.SYNC_PENDING.value}
    assert updated_item.filename == "renamed.pdf"
    assert updated_item.status == ProcessStatus.SYNC_PENDING
    forward.assert_called_once()
    forwarded_item = forward.call_args.args[1]
    assert forwarded_item.filename == "renamed.pdf"
    assert forwarded_item.ocr_file.endswith("renamed_OCR.pdf")
