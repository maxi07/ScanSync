import sys
import types

import pytest
from scansynclib.analytics import AnalyticsHandler


# ocrmypdf is a heavy native dependency that is not installed in the test
# environment. Provide a lightweight stub so the OCR service module can be
# imported and its job-tracking logic exercised in isolation.
_ocrmypdf_stub = types.ModuleType("ocrmypdf")


class _UnsupportedImageFormatError(Exception):
    pass


class _DpiError(Exception):
    pass


class _InputFileError(Exception):
    pass


class _OutputFileAccessError(Exception):
    pass


class _MissingDependencyError(Exception):
    pass


_ocrmypdf_stub.UnsupportedImageFormatError = _UnsupportedImageFormatError
_ocrmypdf_stub.DpiError = _DpiError
_ocrmypdf_stub.InputFileError = _InputFileError
_ocrmypdf_stub.OutputFileAccessError = _OutputFileAccessError
_ocrmypdf_stub.MissingDependencyError = _MissingDependencyError
_ocrmypdf_stub.ocr = lambda *args, **kwargs: 0

# Importing the service pulls in scansynclib.sqlite_wrapper, which initializes a
# real SQLite database at import time. That database is not available in the unit
# test environment, so replace the module with a stub. The query helpers are
# mocked per-test anyway.
_sqlite_stub = types.ModuleType("scansynclib.sqlite_wrapper")
_sqlite_stub.execute_query = lambda *args, **kwargs: None
_sqlite_stub.update_scanneddata_database = lambda *args, **kwargs: None

_original_modules = {
    "ocrmypdf": sys.modules.get("ocrmypdf"),
    "scansynclib.sqlite_wrapper": sys.modules.get("scansynclib.sqlite_wrapper"),
}
sys.modules["ocrmypdf"] = _ocrmypdf_stub
sys.modules["scansynclib.sqlite_wrapper"] = _sqlite_stub


def teardown_module(module):
    for name, original in _original_modules.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


import ocr_service.main as ocr_main  # noqa: E402
from scansynclib.ProcessItem import ProcessItem, ItemType, OCRStatus, ProcessStatus  # noqa: E402


@pytest.fixture
def item(tmp_path):
    file_path = tmp_path / "scan.pdf"
    file_path.write_bytes(b"%PDF-1.4 test")
    process_item = ProcessItem(str(file_path), ItemType.PDF)
    process_item.db_id = 42
    return process_item


@pytest.fixture
def patched(mocker):
    """Mock external collaborators of the OCR service.

    execute_query returns the same fake row id (99) for the INSERT, which the
    service stores as ocr_db_id and reuses for the UPDATE. File naming is
    disabled by default so processed items are forwarded to the upload queue.
    """
    execute_query = mocker.patch.object(ocr_main, "execute_query", return_value=99)
    update_db = mocker.patch.object(ocr_main, "update_scanneddata_database")
    forward = mocker.patch.object(ocr_main, "forward_to_rabbitmq")
    track = mocker.patch.object(ocr_main, "track")
    mocker.patch("scansynclib.analytics.track", track)
    mocker.patch.object(ocr_main.logger, "handlers", [AnalyticsHandler()])
    move = mocker.patch.object(ocr_main, "move_to_failed")
    fake_settings = types.SimpleNamespace(
        file_naming=types.SimpleNamespace(
            ollama_server_url="",
            ollama_server_port="",
            ollama_model="",
            openai_api_key="",
        )
    )
    mocker.patch.object(ocr_main, "settings", fake_settings)
    return {
        "execute_query": execute_query,
        "update_db": update_db,
        "forward": forward,
        "settings": fake_settings,
        "track": track,
        "move": move,
    }


def _ocr_job_update_args(execute_query):
    update_calls = [c for c in execute_query.call_args_list if "UPDATE ocr_jobs" in c.args[0]]
    assert len(update_calls) == 1, "Expected exactly one ocr_jobs status update"
    return update_calls[0].args[1]


@pytest.mark.parametrize(
    "ocr_behavior, expected_status, expected_error",
    [
        ({"return_value": 0}, OCRStatus.COMPLETED, None),
        ({"return_value": 5}, OCRStatus.FAILED, "OCR exited with code 5"),
        (
            {"side_effect": ocr_main.ocrmypdf.UnsupportedImageFormatError()},
            OCRStatus.UNSUPPORTED,
            "Unsupported image format",
        ),
        (
            {"side_effect": ocr_main.ocrmypdf.DpiError("dpi too low")},
            OCRStatus.DPI_ERROR,
            "dpi too low",
        ),
        (
            {"side_effect": ocr_main.ocrmypdf.InputFileError("bad input")},
            OCRStatus.INPUT_ERROR,
            "bad input",
        ),
        (
            {"side_effect": ocr_main.ocrmypdf.OutputFileAccessError("no write access")},
            OCRStatus.OUTPUT_ERROR,
            "no write access",
        ),
        (
            {"side_effect": ocr_main.ocrmypdf.MissingDependencyError()},
            OCRStatus.FAILED,
            "Missing OCR dependency",
        ),
        ({"side_effect": ValueError("boom")}, OCRStatus.FAILED, "boom"),
    ],
)
def test_start_processing_persists_ocr_job_status(item, patched, mocker, ocr_behavior, expected_status, expected_error):
    mocker.patch.object(ocr_main.ocrmypdf, "ocr", **ocr_behavior)
    # On the success path the service verifies that ocrmypdf produced an output
    # file containing text. ocrmypdf is stubbed here, so provide the artifacts it
    # would normally create for the "completed" case.
    with open(item.ocr_file, "wb") as ocr_file:
        ocr_file.write(b"%PDF-1.4 ocr")
    mocker.patch.object(ocr_main, "extract_text", return_value="sample text")

    ocr_main.start_processing(item)

    assert item.ocr_status == expected_status

    status_name, error, db_id = _ocr_job_update_args(patched["execute_query"])
    assert status_name == expected_status.name
    assert error == expected_error
    assert db_id == 99
    events = [call.args[0] for call in patched["track"].call_args_list]
    assert "service.error" not in events
    assert events[0] == "ocr.started"
    assert events[1] == ("ocr.completed" if expected_status == OCRStatus.COMPLETED else
                         "ocr.skipped" if expected_status == OCRStatus.UNSUPPORTED else "ocr.failed")
    outcome = patched["track"].call_args_list[1]
    assert outcome.kwargs["duration_ms"] >= 0
    assert outcome.kwargs["status"] == expected_status.name
    if "side_effect" in ocr_behavior:
        assert outcome.kwargs["error"] is ocr_behavior["side_effect"]


def test_start_processing_inserts_ocr_job_and_forwards_to_upload(item, patched, mocker):
    mocker.patch.object(ocr_main.ocrmypdf, "ocr", return_value=0)

    ocr_main.start_processing(item)

    insert_calls = [c for c in patched["execute_query"].call_args_list if "INSERT INTO ocr_jobs" in c.args[0]]
    assert len(insert_calls) == 1
    assert insert_calls[0].args[1] == (42, OCRStatus.PROCESSING.name)
    assert insert_calls[0].kwargs.get("return_last_id") is True

    patched["forward"].assert_called_once()
    assert patched["forward"].call_args.args[0] == "upload_queue"
    assert item.status == ProcessStatus.SYNC_PENDING


def test_start_processing_forwards_to_file_naming_when_enabled(item, patched, mocker):
    patched["settings"].file_naming.openai_api_key = "secret"
    mocker.patch.object(ocr_main.ocrmypdf, "ocr", return_value=0)

    ocr_main.start_processing(item)

    patched["forward"].assert_called_once()
    assert patched["forward"].call_args.args[0] == "file_naming_queue"
    assert item.status == ProcessStatus.FILENAME_PENDING


def test_ocr_no_text_is_not_reported_as_crash(item, patched, mocker):
    mocker.patch.object(ocr_main.ocrmypdf, "ocr", return_value=0)
    mocker.patch.object(ocr_main, "extract_text", return_value="")
    with open(item.ocr_file, "wb") as output:
        output.write(b"synthetic")
    ocr_main.start_processing(item)
    events = [call.args[0] for call in patched["track"].call_args_list]
    assert "ocr.no_text" in events
    assert "ocr.failed" not in events
    assert "naming.skipped" in events


@pytest.mark.parametrize("naming_enabled", [False, True])
@pytest.mark.parametrize("failure", [False, RuntimeError("broker unavailable")])
def test_failed_handoff_marks_document_failed(item, patched, mocker, naming_enabled, failure):
    if naming_enabled:
        patched["settings"].file_naming.openai_api_key = "synthetic-key"
    if isinstance(failure, Exception):
        patched["forward"].side_effect = failure
    else:
        patched["forward"].return_value = failure
    mocker.patch.object(ocr_main.ocrmypdf, "ocr", return_value=0)
    ocr_main.start_processing(item)
    assert item.status == ProcessStatus.FAILED
    patched["move"].assert_called_once_with(item)
    failures = [call for call in patched["track"].call_args_list if call.args[0] == "document.failed"]
    assert len(failures) == 1
    assert failures[0].kwargs["reason"] == "queue_publish"
    assert patched["update_db"].call_args.args[1]["file_status"] == ProcessStatus.FAILED.value
