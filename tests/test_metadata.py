import importlib.util
from pathlib import Path
import pickle
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
from scansynclib import analytics


@pytest.fixture
def validation_timeout(monkeypatch, request):
    value = getattr(request, "param", None)
    if value is None:
        monkeypatch.delenv("PDF_VALIDATION_TIMEOUT", raising=False)
    else:
        monkeypatch.setenv("PDF_VALIDATION_TIMEOUT", value)
    return 300 if value is None else int(value)


@pytest.fixture
def metadata(monkeypatch, validation_timeout):
    sqlite = ModuleType("scansynclib.sqlite_wrapper")
    sqlite.execute_query = Mock(return_value=1)
    sqlite.update_scanneddata_database = Mock()
    helpers = ModuleType("scansynclib.helpers")
    helpers.consume = Mock()
    helpers.publish = Mock()
    helpers.move_to_failed = Mock()
    pillow = ModuleType("PIL")
    pillow.Image = Mock()
    pymupdf = ModuleType("pymupdf")
    pypdf = ModuleType("pypdf")
    pypdf.PdfReader = Mock()
    source = Path(__file__).resolve().parents[1] / "metadata_service/main.py"
    spec = importlib.util.spec_from_file_location("metadata_under_test", source)
    module = importlib.util.module_from_spec(spec)
    with monkeypatch.context() as context:
        context.setitem(sys.modules, "scansynclib.sqlite_wrapper", sqlite)
        context.setitem(sys.modules, "scansynclib.helpers", helpers)
        context.setitem(sys.modules, "PIL", pillow)
        context.setitem(sys.modules, "pymupdf", pymupdf)
        context.setitem(sys.modules, "pypdf", pypdf)
        spec.loader.exec_module(module)
    monkeypatch.setattr(module, "track", Mock())
    monkeypatch.setattr(analytics, "track", module.track)
    monkeypatch.setattr(module.logger, "handlers", [analytics.AnalyticsHandler()])
    return module


def test_callback_preserves_detection_identity(metadata):
    metadata.on_created = Mock()
    properties = SimpleNamespace(message_id="a" * 32, headers={"received_at": "2026-11-04T12:00:00"})
    metadata.callback(Mock(), SimpleNamespace(delivery_tag=1), properties, b'{"file_paths":["scan.pdf"]}')
    metadata.on_created.assert_called_once_with(["scan.pdf"], analytics_id="a" * 32, received_at="2026-11-04T12:00:00")


@pytest.mark.parametrize("published", [True, False])
def test_metadata_carries_identity_and_emits_completion(metadata, monkeypatch, tmp_path, published):
    source = tmp_path / "private.pdf"
    source.write_bytes(b"synthetic")
    monkeypatch.setattr(metadata, "is_pdf", Mock(return_value=True))
    monkeypatch.setattr(metadata, "pdf_to_jpeg", Mock())
    monkeypatch.setattr(metadata.os, "mkdir", Mock())
    monkeypatch.setattr(metadata, "PdfReader", Mock(return_value=SimpleNamespace(pages=[1, 2])))
    metadata.execute_query.side_effect = lambda query, *args, **kwargs: [] if kwargs.get("fetchall") else 1
    metadata.publish.return_value = published
    metadata.on_created([str(source)], analytics_id="a" * 32, received_at="2026-11-04T12:00:00")
    events = [call.args[0] for call in metadata.track.call_args_list]
    assert events == ["document.received", "metadata.started"] + (["metadata.completed"] if published else ["metadata.failed", "document.failed"])
    item = pickle.loads(metadata.publish.call_args.args[1])
    assert item.analytics_id == "a" * 32
    assert item.time_added.isoformat() == "2026-11-04T12:00:00"
    if published:
        assert metadata.track.call_args.kwargs["pages"] == 2
        metadata.move_to_failed.assert_not_called()
    else:
        failed_item = metadata.track.call_args.kwargs["item"]
        assert failed_item.status == metadata.ProcessStatus.FAILED
        assert failed_item.analytics_id == "a" * 32
        assert metadata.update_scanneddata_database.call_args.args[1] == {"file_status": metadata.ProcessStatus.FAILED.value}
        metadata.move_to_failed.assert_called_once_with(failed_item)


def test_metadata_failure_is_structured(metadata):
    metadata.on_created = Mock(side_effect=ValueError("private contents"))
    metadata.callback(Mock(), SimpleNamespace(delivery_tag=1), SimpleNamespace(message_id="a" * 32), b'{"file_paths":["scan.pdf"]}')
    assert metadata.track.call_args.args == ("metadata.failed",)
    assert isinstance(metadata.track.call_args.kwargs["error"], ValueError)


def test_internal_failed_files_do_not_count_as_new_documents(metadata):
    metadata.on_created(["/mnt/scans/failed-documents/private.pdf"], analytics_id="a" * 32)
    metadata.track.assert_not_called()


@pytest.mark.parametrize("validation_timeout", [None, "5"], indirect=True)
def test_invalid_pdf_waits_for_configured_timeout(metadata, validation_timeout, monkeypatch, tmp_path):
    assert metadata.TIMEOUT_PDF_VALIDATION == validation_timeout
    source = tmp_path / "invalid.pdf"
    source.write_bytes(b"synthetic invalid PDF")
    monkeypatch.setattr(metadata, "is_pdf", Mock(return_value=False))
    monkeypatch.setattr(metadata, "is_image", Mock(return_value=False))
    clock = [0]
    monkeypatch.setattr(metadata.time, "time", lambda: clock[0])
    sleep = Mock(side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    monkeypatch.setattr(metadata.time, "sleep", sleep)
    metadata.execute_query.side_effect = lambda query, *args, **kwargs: [] if kwargs.get("fetchall") else 1

    metadata.on_created([str(source)])

    assert clock[0] == validation_timeout
    item = metadata.move_to_failed.call_args.args[0]
    assert item.status == metadata.ProcessStatus.INVALID_FILE
    assert metadata.update_scanneddata_database.call_args.args[1] == {"file_status": metadata.ProcessStatus.INVALID_FILE.value}
    metadata.publish.assert_not_called()
    sleep.assert_called_with(5)
