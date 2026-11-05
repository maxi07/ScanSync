import pickle
from pathlib import Path
import sys
import types
from types import SimpleNamespace

import pytest
from pika import exceptions as pika_exceptions

from scansynclib.settings_schema import FileNamingMethod
from scansynclib.analytics import AnalyticsHandler


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


import file_naming_service.main as fn_main  # noqa: E402


def _restore_scansynclib_modules():
    """Undo the sys.modules stubbing done above.

    ``file_naming_service.main`` has already bound the stubbed objects it needs,
    so the stubs can be removed from ``sys.modules`` immediately. Restoring them
    here (rather than in ``teardown_module``) prevents the fileless stub modules
    from leaking into the collection/import of other test modules, which would
    otherwise fail to import the real ``scansynclib.settings`` members.
    """
    for name, original in (
        ("scansynclib.sqlite_wrapper", _original_sqlite_wrapper),
        ("scansynclib.openai_helper", _original_openai_helper),
        ("scansynclib.ollama_helper", _original_ollama_helper),
        ("scansynclib.settings", _original_settings),
    ):
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


_restore_scansynclib_modules()

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
    track = mocker.patch.object(fn_main, "track")
    mocker.patch("scansynclib.analytics.track", track)
    mocker.patch.object(fn_main.logger, "handlers", [AnalyticsHandler()])

    ch = mocker.Mock()
    method = mocker.Mock()
    method.delivery_tag = 123
    body = pickle.dumps({"not": "a process item"})

    fn_main.callback(ch, method, None, body)

    ch.basic_ack.assert_called_once_with(delivery_tag=123)
    execute_query.assert_not_called()
    forward.assert_not_called()
    assert [call.args[0] for call in track.call_args_list] == ["queue.message_rejected"]


def test_callback_skips_followup_when_ack_fails(item, mocker):
    mocker.patch.object(fn_main.settings.file_naming, "method", FileNamingMethod.OPENAI)
    mocker.patch.object(fn_main.settings.file_naming, "openai_api_key", "test-key")
    mocker.patch.object(fn_main, "generate_filename_openai", return_value="renamed")
    mocker.patch.object(fn_main, "execute_query", return_value=item.file_naming_db_id)
    mocker.patch.object(fn_main, "get_latest_file_naming_status", return_value=FileNamingStatus.COMPLETED)
    update = mocker.patch.object(fn_main, "update_scanneddata_database")
    forward = mocker.patch.object(fn_main, "forward_to_rabbitmq")

    ch = mocker.Mock()
    ch.basic_ack.side_effect = pika_exceptions.AMQPError("lost connection")
    method = mocker.Mock()
    method.delivery_tag = 456

    fn_main.callback(ch, method, None, pickle.dumps(item))

    ch.basic_ack.assert_called_once_with(delivery_tag=456)
    update.assert_not_called()
    forward.assert_not_called()


@pytest.mark.parametrize("naming_method, generator", [
    (FileNamingMethod.OPENAI, "generate_filename_openai"),
    (FileNamingMethod.OLLAMA, "generate_filename_ollama"),
])
def test_colliding_filenames_keep_separate_working_files(item, tmp_path, mocker, naming_method, generator):
    second_source = tmp_path / "second.pdf"
    second_source.write_bytes(b"second original document")
    second_item = ProcessItem(str(second_source), ItemType.PDF)
    second_item.db_id = 8
    Path(second_item.ocr_file).write_bytes(b"second OCR document")
    first_contents = Path(item.ocr_file).read_bytes()
    truncated_name = "Rechnung_Beispiel_GmbH_2026-001"[:30]
    assert truncated_name == "Rechnung_Beispiel_GmbH_2026-002"[:30]
    existing_destination = tmp_path / (truncated_name + "_OCR.pdf")
    existing_destination.write_bytes(b"another pending document")
    mocker.patch.object(fn_main.settings.file_naming, "method", naming_method)
    mocker.patch.object(fn_main, generator, return_value=truncated_name)
    mocker.patch.object(fn_main, "execute_query", return_value=11)
    mocker.patch.object(fn_main, "get_latest_file_naming_status", return_value=FileNamingStatus.COMPLETED)
    mocker.patch.object(fn_main, "update_scanneddata_database")
    forward = mocker.patch.object(fn_main, "forward_to_rabbitmq")
    channel = mocker.Mock()
    method = SimpleNamespace(delivery_tag=123)

    fn_main.callback(channel, method, None, pickle.dumps(item))
    fn_main.callback(channel, method, None, pickle.dumps(second_item))

    assert forward.call_count == 2
    first_result = forward.call_args_list[0].args[1]
    second_result = forward.call_args_list[1].args[1]
    assert first_result.status == second_result.status == ProcessStatus.SYNC_PENDING
    assert first_result.filename == second_result.filename == truncated_name + ".pdf"
    assert len(first_result.filename_without_extension) <= 30
    assert first_result.ocr_file != second_result.ocr_file
    assert first_result.ocr_file == item.ocr_file
    assert second_result.ocr_file == second_item.ocr_file
    assert Path(first_result.ocr_file).parent == tmp_path
    assert Path(second_result.ocr_file).parent == tmp_path
    assert Path(first_result.ocr_file).read_bytes() == first_contents
    assert Path(second_result.ocr_file).read_bytes() == b"second OCR document"
    assert existing_destination.read_bytes() == b"another pending document"

    Path(first_result.ocr_file).unlink()
    Path(first_result.local_file_path).unlink()

    assert Path(second_result.ocr_file).read_bytes() == b"second OCR document"
    assert Path(second_result.local_file_path).read_bytes() == b"second original document"
    assert existing_destination.read_bytes() == b"another pending document"


@pytest.mark.parametrize("naming_method, new_filename", [
    (FileNamingMethod.NONE, "doc"),
    (FileNamingMethod.OPENAI, "doc"),
    (FileNamingMethod.OLLAMA, "doc"),
    (FileNamingMethod.OPENAI, "renamed"),
    (FileNamingMethod.OLLAMA, "renamed"),
])
def test_redelivery_after_ack_failure_preserves_ocr_path(item, tmp_path, mocker, naming_method, new_filename):
    original_contents = Path(item.ocr_file).read_bytes()
    mocker.patch.object(fn_main.settings.file_naming, "method", naming_method)
    mocker.patch.object(fn_main, "generate_filename_openai", return_value=new_filename)
    mocker.patch.object(fn_main, "generate_filename_ollama", return_value=new_filename)
    mocker.patch.object(fn_main, "execute_query", return_value=11)
    mocker.patch.object(fn_main, "get_latest_file_naming_status", return_value=FileNamingStatus.COMPLETED)
    mocker.patch.object(fn_main, "update_scanneddata_database")
    forward = mocker.patch.object(fn_main, "forward_to_rabbitmq")
    channel = mocker.Mock()
    channel.basic_ack.side_effect = [pika_exceptions.AMQPError("lost connection"), None]
    method = SimpleNamespace(delivery_tag=123)
    body = pickle.dumps(item)

    fn_main.callback(channel, method, None, body)

    forward.assert_not_called()
    assert Path(item.ocr_file).read_bytes() == original_contents

    fn_main.callback(channel, method, None, body)

    assert list(tmp_path.glob(".scansync-*_OCR.pdf")) == []
    assert Path(item.ocr_file).read_bytes() == original_contents
    forward.assert_called_once()
    forwarded_item = forward.call_args.args[1]
    assert forwarded_item.ocr_file == item.ocr_file
    assert forwarded_item.filename == new_filename + ".pdf"


@pytest.mark.parametrize("failure", [False, RuntimeError("broker unavailable")])
def test_callback_marks_failed_upload_handoff(item, mocker, failure):
    mocker.patch.object(fn_main.settings.file_naming, "method", FileNamingMethod.NONE)
    mocker.patch.object(fn_main, "execute_query", return_value=11)
    mocker.patch.object(fn_main, "get_latest_file_naming_status", return_value=FileNamingStatus.SKIPPED)
    update = mocker.patch.object(fn_main, "update_scanneddata_database")
    forward = mocker.patch.object(fn_main, "forward_to_rabbitmq", return_value=failure)
    if isinstance(failure, Exception):
        forward.side_effect = failure
    move = mocker.patch.object(fn_main, "move_to_failed")
    track = mocker.patch.object(fn_main, "track")
    fn_main.callback(mocker.Mock(), SimpleNamespace(delivery_tag=1), None, pickle.dumps(item))
    forwarded_item = forward.call_args.args[1]
    assert forwarded_item.status == ProcessStatus.FAILED
    assert update.call_args.args[1] == {"file_status": ProcessStatus.FAILED.value}
    move.assert_called_once_with(forwarded_item)
    assert track.call_args.args == ("document.failed",)
    assert track.call_args.kwargs["reason"] == "queue_publish"


@pytest.mark.parametrize("missing_ocr", [False, True])
def test_callback_error_is_tracked_once(item, mocker, missing_ocr):
    mocker.patch.object(fn_main.settings.file_naming, "method", FileNamingMethod.OPENAI)
    mocker.patch.object(fn_main.settings.file_naming, "openai_api_key", "synthetic-key")
    mocker.patch.object(fn_main, "execute_query", return_value=11)
    mocker.patch.object(fn_main, "get_latest_file_naming_status", return_value=FileNamingStatus.FAILED)
    mocker.patch.object(fn_main, "generate_filename_openai", side_effect=ValueError("synthetic failure"))
    if missing_ocr:
        Path(item.ocr_file).unlink()
    mocker.patch.object(fn_main, "update_scanneddata_database")
    mocker.patch.object(fn_main, "forward_to_rabbitmq", return_value=True)
    track = mocker.patch.object(fn_main, "track")
    mocker.patch("scansynclib.analytics.track", track)
    mocker.patch.object(fn_main.logger, "handlers", [AnalyticsHandler()])
    fn_main.callback(mocker.Mock(), SimpleNamespace(delivery_tag=1), None, pickle.dumps(item))
    assert [call.args[0] for call in track.call_args_list] == ["naming.failed" if missing_ocr else "service.error"]


def test_corrupt_message_is_acknowledged_and_tracked_once(mocker):
    execute_query = mocker.patch.object(fn_main, "execute_query")
    forward = mocker.patch.object(fn_main, "forward_to_rabbitmq")
    track = mocker.patch.object(fn_main, "track")
    mocker.patch("scansynclib.analytics.track", track)
    mocker.patch.object(fn_main.logger, "handlers", [AnalyticsHandler()])
    channel = mocker.Mock()
    fn_main.callback(channel, SimpleNamespace(delivery_tag=1), None, b"not a pickle")
    channel.basic_ack.assert_called_once_with(delivery_tag=1)
    execute_query.assert_not_called()
    forward.assert_not_called()
    assert [call.args[0] for call in track.call_args_list] == ["service.error"]
