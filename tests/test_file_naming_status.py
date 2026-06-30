import pickle
import sys
import types

import pytest


# Importing the service pulls in scansynclib.sqlite_wrapper, which initializes a
# real SQLite database at import time. That database is not available in the unit
# test environment, so replace the module with a stub. The query helpers are
# mocked per-test anyway.
_sqlite_stub = types.ModuleType("scansynclib.sqlite_wrapper")
_sqlite_stub.execute_query = lambda *args, **kwargs: None
_sqlite_stub.update_scanneddata_database = lambda *args, **kwargs: None

_original_sqlite_wrapper = sys.modules.get("scansynclib.sqlite_wrapper")
sys.modules["scansynclib.sqlite_wrapper"] = _sqlite_stub


def teardown_module(module):
    if _original_sqlite_wrapper is None:
        sys.modules.pop("scansynclib.sqlite_wrapper", None)
    else:
        sys.modules["scansynclib.sqlite_wrapper"] = _original_sqlite_wrapper


import file_naming_service.main as fn_main  # noqa: E402
from scansynclib.ProcessItem import ProcessItem, ItemType, FileNamingStatus  # noqa: E402

@pytest.fixture
def item(tmp_path):
    file_path = tmp_path / "doc.pdf"
    file_path.write_bytes(b"%PDF-1.4 test")
    process_item = ProcessItem(str(file_path), ItemType.PDF)
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
