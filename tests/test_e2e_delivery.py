import importlib.util
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("renamed", [False, True])
def test_delivery_identifies_original_source_even_after_renaming(monkeypatch, mocker, renamed):
    directory = Path(__file__).parent / "e2e"
    support_spec = importlib.util.spec_from_file_location("e2e_support", directory / "conftest.py")
    support = importlib.util.module_from_spec(support_spec)
    support_spec.loader.exec_module(support)
    monkeypatch.setitem(sys.modules, "conftest", support)
    spec = importlib.util.spec_from_file_location("e2e_pipeline", directory / "test_pipeline.py")
    pipeline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pipeline)

    with sqlite3.connect(":memory:") as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("CREATE TABLE scanneddata (id INTEGER PRIMARY KEY, file_name TEXT, source_file_name TEXT)")

        def rows(query, params=()):
            return [dict(row) for row in connection.execute(query, params)]

        def upload(*args, **kwargs):
            name = "scan_deadbeef.pdf"
            connection.execute(
                "INSERT INTO scanneddata (file_name, source_file_name) VALUES (?, ?)",
                ("E2E_document.pdf" if renamed else name, name),
            )
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        mocker.patch.object(pipeline, "rows", side_effect=rows)
        mocker.patch.object(pipeline.uuid, "uuid4", return_value=SimpleNamespace(hex="deadbeef"))
        mocker.patch.object(pipeline.subprocess, "run", side_effect=upload)
        browser = mocker.Mock()
        browser.find_element.return_value.is_displayed.return_value = True
        item, source_name = pipeline.deliver(browser, Path("/synthetic.pdf"))

    assert source_name == "scan_deadbeef.pdf"
    assert item["source_file_name"] == source_name
    assert item["file_name"] == ("E2E_document.pdf" if renamed else source_name)
