import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from scansynclib import analytics

from scansynclib.ProcessItem import ItemType, OneDriveDestination, ProcessItem, ProcessStatus


@pytest.fixture
def upload_service(monkeypatch):
    sqlite = ModuleType("scansynclib.sqlite_wrapper")
    sqlite.execute_query = Mock(return_value=1)
    sqlite.update_scanneddata_database = Mock()
    helpers = ModuleType("scansynclib.helpers")
    helpers.consume = Mock()
    helpers.move_to_failed = Mock()
    api = ModuleType("scansynclib.onedrive_api")
    api.upload_small = Mock(return_value=True)
    source = Path(__file__).resolve().parents[1] / "upload_service/main.py"
    spec = importlib.util.spec_from_file_location("upload_under_test", source)
    module = importlib.util.module_from_spec(spec)
    with monkeypatch.context() as context:
        context.setitem(sys.modules, "scansynclib.sqlite_wrapper", sqlite)
        context.setitem(sys.modules, "scansynclib.helpers", helpers)
        context.setitem(sys.modules, "scansynclib.onedrive_api", api)
        spec.loader.exec_module(module)
    monkeypatch.setattr(module, "track", Mock())
    monkeypatch.setattr(analytics, "track", module.track)
    monkeypatch.setattr(module.logger, "handlers", [analytics.AnalyticsHandler()])
    return module


@pytest.fixture
def upload_item(tmp_path):
    source = tmp_path / "private.pdf"
    source.write_bytes(b"synthetic")
    item = ProcessItem(str(source), ItemType.PDF)
    Path(item.ocr_file).write_bytes(b"synthetic OCR")
    item.db_id = 42
    item.OneDriveDestinations = [OneDriveDestination("private folder", "private folder id", "private drive id")]
    return item


@pytest.mark.parametrize("success", [True, False])
def test_upload_outcomes_and_total_duration(upload_service, upload_item, success):
    upload_service.upload_small.return_value = success
    upload_service.start_processing(upload_item)
    calls = upload_service.track.call_args_list
    events = [call.args[0] for call in calls]
    assert events[:2] == ["upload.started", "upload.target_started"]
    assert ("upload.target_completed" if success else "upload.target_failed") in events
    assert events[-1] == ("document.completed" if success else "document.failed")
    if success:
        assert calls[-1].kwargs["total_duration_ms"] >= 0
        assert upload_item.status == ProcessStatus.COMPLETED
    else:
        assert upload_item.status == ProcessStatus.SYNC_FAILED
        assert "document.completed" not in events


def test_no_targets_never_count_as_synced(upload_service, upload_item):
    upload_item.OneDriveDestinations = []
    upload_service.start_processing(upload_item)
    assert upload_item.status == ProcessStatus.SYNC_FAILED
    assert Path(upload_item.ocr_file).exists()
    assert upload_service.track.call_args.kwargs["reason"] == "no_targets"


def test_partial_upload_does_not_count_document_as_completed(upload_service, upload_item):
    upload_item.OneDriveDestinations *= 2
    upload_service.upload_small.side_effect = [True, False]
    upload_service.start_processing(upload_item)
    calls = upload_service.track.call_args_list
    failed = next(call for call in calls if call.args[0] == "upload.failed")
    assert failed.kwargs["successful_targets"] == 1
    assert failed.kwargs["failed_targets"] == 1
    assert "document.completed" not in [call.args[0] for call in calls]


@pytest.fixture
def onedrive(monkeypatch):
    sqlite = ModuleType("scansynclib.sqlite_wrapper")
    sqlite.update_scanneddata_database = Mock()
    settings = ModuleType("scansynclib.settings")
    settings.settings = SimpleNamespace()
    source = Path(__file__).resolve().parents[1] / "scansynclib/scansynclib/onedrive_api.py"
    spec = importlib.util.spec_from_file_location("onedrive_upload_under_test", source)
    module = importlib.util.module_from_spec(spec)
    with monkeypatch.context() as context:
        context.setitem(sys.modules, "scansynclib.sqlite_wrapper", sqlite)
        context.setitem(sys.modules, "scansynclib.settings", settings)
        spec.loader.exec_module(module)
    monkeypatch.setattr(module, "track", Mock())
    monkeypatch.setattr(analytics, "track", module.track)
    monkeypatch.setattr(module.logger, "handlers", [analytics.AnalyticsHandler()])
    monkeypatch.setattr(module, "get_access_token", Mock(return_value="secret-token"))
    return module


def test_onedrive_http_error_has_status_without_response_body(onedrive, upload_item, monkeypatch):
    monkeypatch.setattr(onedrive.requests, "put", Mock(return_value=Mock(status_code=403, text="private data")))
    assert onedrive.upload_small(upload_item, upload_item.OneDriveDestinations[0]) is False
    assert onedrive.track.call_args.args == ("upload.request_failed",)
    assert onedrive.track.call_args.kwargs["status_code"] == 403
    assert "private data" not in str(onedrive.track.call_args)


@pytest.mark.parametrize("method", ["upload_small", "upload"])
def test_onedrive_network_error_keeps_real_exception(onedrive, upload_item, monkeypatch, method):
    error = requests.ConnectionError("private URL")
    destination = upload_item.OneDriveDestinations[0]
    destination.analytics_status_code = 201
    session = Mock(status_code=200)
    session.json.return_value = {"uploadUrl": "https://synthetic.example.test/upload"}
    monkeypatch.setattr(onedrive.requests, "post", Mock(return_value=session))
    monkeypatch.setattr(onedrive.requests, "put", Mock(side_effect=error))
    assert getattr(onedrive, method)(upload_item, destination) is False
    assert destination.analytics_status_code is None
    assert onedrive.track.call_args.kwargs["error"] is error


def test_large_file_uses_chunked_upload_without_reporting_an_error(onedrive, upload_item, monkeypatch):
    monkeypatch.setattr(onedrive.os.path, "getsize", Mock(return_value=251 * 1024 * 1024))
    chunked = Mock(return_value=True)
    monkeypatch.setattr(onedrive, "upload", chunked)
    assert onedrive.upload_small(upload_item, upload_item.OneDriveDestinations[0]) is True
    chunked.assert_called_once_with(upload_item, upload_item.OneDriveDestinations[0])
    onedrive.track.assert_not_called()


@pytest.mark.parametrize("failure", [requests.ConnectionError("private URL"), 403])
def test_later_chunk_failure_does_not_reuse_prior_success_status(onedrive, upload_service, upload_item, monkeypatch, failure):
    Path(upload_item.ocr_file).write_bytes(b"x" * (3276800 + 1))
    session = Mock(status_code=200)
    session.json.return_value = {"uploadUrl": "https://synthetic.example.test/upload"}
    monkeypatch.setattr(onedrive.requests, "post", Mock(return_value=session))
    failed_response = failure if isinstance(failure, Exception) else Mock(status_code=failure, text="private response")
    put = Mock(side_effect=[Mock(status_code=202), failed_response])
    monkeypatch.setattr(onedrive.requests, "put", put)
    upload_service.upload_small.side_effect = onedrive.upload
    upload_service.start_processing(upload_item)
    failed = next(call for call in upload_service.track.call_args_list if call.args[0] == "upload.target_failed")
    assert failed.kwargs["status_code"] == (None if isinstance(failure, Exception) else failure)
    assert put.call_count == 2
    assert upload_item.status == ProcessStatus.SYNC_FAILED


@pytest.mark.parametrize("method", ["upload_small", "upload"])
def test_missing_token_does_not_reuse_status_from_previous_upload(onedrive, upload_item, method):
    destination = upload_item.OneDriveDestinations[0]
    destination.analytics_status_code = 201
    onedrive.get_access_token.return_value = None
    assert getattr(onedrive, method)(upload_item, destination) is False
    assert destination.analytics_status_code is None
