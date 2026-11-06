import sys
import types

import pytest


# Importing scansynclib.cleanup pulls in scansynclib.sqlite_wrapper, which
# initializes a real SQLite database at import time. That database is not
# available in the unit test environment, so replace the module with a stub.
# The query helper is mocked per-test anyway.
_sqlite_stub = types.ModuleType("scansynclib.sqlite_wrapper")
_sqlite_stub.execute_query = lambda *args, **kwargs: None
_sqlite_stub.update_scanneddata_database = lambda *args, **kwargs: None

_original_modules = {
    "scansynclib.sqlite_wrapper": sys.modules.get("scansynclib.sqlite_wrapper"),
}
sys.modules["scansynclib.sqlite_wrapper"] = _sqlite_stub


def teardown_module(module):
    for name, original in _original_modules.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


import scansynclib.cleanup as cleanup  # noqa: E402
from scansynclib.ProcessItem import ProcessStatus, StatusProgressBar  # noqa: E402


@pytest.fixture
def smb(tmp_path, mocker):
    """Point the cleanup module at a temporary SMB directory."""
    smb_path = tmp_path / "scans"
    (smb_path / "ShareA").mkdir(parents=True)

    def fake_get(key, default=None):
        return {
            "smb.path": str(smb_path),
            "failedDir": "failed-documents",
        }.get(key, default)

    mocker.patch.object(cleanup.config, "get", side_effect=fake_get)
    return smb_path


def test_cleanup_marks_pending_documents_as_failed(smb, mocker):
    scan = smb / "ShareA" / "scan.pdf"
    scan.write_bytes(b"%PDF-1.4 test")

    execute_query = mocker.patch.object(
        cleanup,
        "execute_query",
        return_value=[{"id": 7, "file_name": "scan.pdf", "local_filepath": "ShareA"}],
    )

    cleanup.cleanup_dangling_documents()

    # The pending document is moved out of the share and into the failed dir.
    assert not scan.exists()
    assert (smb / "failed-documents" / "scan.pdf").is_file()

    update_calls = [c for c in execute_query.call_args_list if "UPDATE scanneddata" in c.args[0]]
    assert len(update_calls) == 1
    status_value, status_code, file_name, doc_id = update_calls[0].args[1]
    assert status_value == ProcessStatus.FAILED.value
    assert status_code == StatusProgressBar.get_progress(ProcessStatus.FAILED)
    assert status_code < 0
    assert file_name == "scan.pdf"
    assert doc_id == 7


def test_cleanup_removes_leftover_ocr_file(smb, mocker):
    scan = smb / "ShareA" / "scan.pdf"
    scan.write_bytes(b"%PDF-1.4 test")
    ocr_file = smb / "ShareA" / "scan_OCR.pdf"
    ocr_file.write_bytes(b"%PDF-1.4 ocr")

    mocker.patch.object(
        cleanup,
        "execute_query",
        return_value=[{"id": 1, "file_name": "scan.pdf", "local_filepath": "ShareA"}],
    )

    cleanup.cleanup_dangling_documents()

    # The original file is preserved in the failed dir, the OCR file is dropped.
    assert (smb / "failed-documents" / "scan.pdf").is_file()
    assert not ocr_file.exists()
    assert not (smb / "failed-documents" / "scan_OCR.pdf").exists()


def test_cleanup_marks_failed_even_when_file_missing(smb, mocker):
    execute_query = mocker.patch.object(
        cleanup,
        "execute_query",
        return_value=[{"id": 3, "file_name": "gone.pdf", "local_filepath": "ShareA"}],
    )

    cleanup.cleanup_dangling_documents()

    update_calls = [c for c in execute_query.call_args_list if "UPDATE scanneddata" in c.args[0]]
    assert len(update_calls) == 1
    assert update_calls[0].args[1][3] == 3


def test_cleanup_noop_when_no_pending_documents(smb, mocker):
    execute_query = mocker.patch.object(cleanup, "execute_query", return_value=[])

    cleanup.cleanup_dangling_documents()

    update_calls = [c for c in execute_query.call_args_list if "UPDATE scanneddata" in c.args[0]]
    assert update_calls == []


@pytest.mark.parametrize("collision", [False, True])
def test_cleanup_after_naming_uses_original_source_and_downloadable_name(smb, mocker, collision):
    source = smb / "ShareA" / "scanner_original.pdf"
    source.write_bytes(b"original scan")
    ocr = smb / "ShareA" / "scanner_original_OCR.pdf"
    ocr.write_bytes(b"OCR output")
    failed = smb / "failed-documents"
    failed.mkdir()
    if collision:
        (failed / "Invoice.pdf").write_bytes(b"another failed scan")
    execute_query = mocker.patch.object(cleanup, "execute_query", return_value=[{
        "id": 9, "file_name": "Invoice.pdf", "source_file_name": source.name, "local_filepath": "ShareA",
    }])

    cleanup.cleanup_dangling_documents()

    update = [call for call in execute_query.call_args_list if "UPDATE scanneddata" in call.args[0]][0]
    stored_name = update.args[1][2]
    assert (failed / stored_name).read_bytes() == b"original scan"
    assert stored_name == ("Invoice_ShareA_1.pdf" if collision else "Invoice.pdf")
    assert not source.exists()
    assert not ocr.exists()
    if collision:
        assert (failed / "Invoice.pdf").read_bytes() == b"another failed scan"
