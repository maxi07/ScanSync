import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from tenacity import RetryError, wait_fixed


@pytest.fixture
def ollama_helper(monkeypatch):
    sqlite_stub = ModuleType("scansynclib.sqlite_wrapper")
    sqlite_stub.execute_query = Mock()
    settings_stub = ModuleType("scansynclib.settings")
    settings_stub.settings = SimpleNamespace(file_naming=SimpleNamespace(
        ollama_server_url="http://host.docker.internal",
        ollama_server_port=11434,
        ollama_model="qwen3.5:2b",
    ))
    source = Path(__file__).resolve().parents[1] / "scansynclib/scansynclib/ollama_helper.py"
    spec = importlib.util.spec_from_file_location("scansynclib._ollama_helper_under_test", source)
    module = importlib.util.module_from_spec(spec)
    with monkeypatch.context() as context:
        context.setitem(sys.modules, "scansynclib.sqlite_wrapper", sqlite_stub)
        context.setitem(sys.modules, "scansynclib.settings", settings_stub)
        spec.loader.exec_module(module)
    monkeypatch.setattr(module, "logger", Mock())
    monkeypatch.setattr(module, "track", Mock())
    return module


def test_post_logs_request_and_response_without_document_text(ollama_helper, monkeypatch):
    response = Mock(status_code=200)
    post = Mock(return_value=response)
    monkeypatch.setattr(ollama_helper.requests, "post", post)
    payload = {"model": "qwen3.5:2b", "prompt": "private document text"}

    assert ollama_helper.post_to_ollama(payload, {}) is response

    post.assert_called_once_with(
        "http://host.docker.internal:11434/api/generate", json=payload, headers={}, timeout=120,
    )
    assert ollama_helper.logger.info.call_count == 2
    assert "private document text" not in str(ollama_helper.logger.mock_calls)
    ollama_helper.logger.warning.assert_not_called()


def test_timeouts_log_each_retry_then_succeed(ollama_helper, monkeypatch):
    response = Mock(status_code=200)
    post = Mock(side_effect=[requests.ReadTimeout("test timeout"), requests.ConnectionError("test connection"), response])
    monkeypatch.setattr(ollama_helper.requests, "post", post)
    request = ollama_helper.post_to_ollama.retry_with(wait=wait_fixed(2), sleep=Mock())

    assert request({"model": "qwen3.5:2b"}, {}) is response

    assert post.call_count == 3
    warnings = ollama_helper.logger.warning.call_args_list
    assert len(warnings) == 2
    assert warnings[0].args[1] == 1
    assert "test timeout" in str(warnings[0].args[2])
    assert warnings[0].args[3] == 2
    assert warnings[1].args[1] == 2
    assert "test connection" in str(warnings[1].args[2])


def test_retries_stop_after_three_attempts(ollama_helper, monkeypatch):
    post = Mock(side_effect=requests.ReadTimeout("test timeout"))
    monkeypatch.setattr(ollama_helper.requests, "post", post)
    request = ollama_helper.post_to_ollama.retry_with(wait=wait_fixed(0), sleep=Mock())

    with pytest.raises(RetryError) as error:
        request({"model": "qwen3.5:2b"}, {})

    assert error.value.last_attempt.attempt_number == 3
    assert post.call_count == 3
    assert ollama_helper.logger.warning.call_count == 2
    assert [call.args[0] for call in ollama_helper.track.call_args_list] == ["naming.retried", "naming.retried"]


def test_non_retryable_errors_are_not_repeated(ollama_helper, monkeypatch):
    post = Mock(side_effect=ValueError("invalid payload"))
    monkeypatch.setattr(ollama_helper.requests, "post", post)

    with pytest.raises(ValueError, match="invalid payload"):
        ollama_helper.post_to_ollama({}, {})

    post.assert_called_once()
    ollama_helper.logger.warning.assert_not_called()


def test_filename_generation_disables_thinking_and_limits_output(ollama_helper, monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = {"response": "A" * 29 + "_extra_filename"}
    post = Mock(return_value=response)
    monkeypatch.setattr(ollama_helper.requests, "post", post)
    monkeypatch.setattr(ollama_helper, "extract_text", Mock(return_value="Synthetic invoice"))
    item = SimpleNamespace(filename="scan.pdf", filename_without_extension="scan", ocr_file="scan_OCR.pdf", file_naming_db_id=11)

    assert ollama_helper.generate_filename_ollama(item) == "A" * 29

    payload = post.call_args.kwargs["json"]
    assert payload["think"] is False
    assert payload["options"]["num_predict"] == 128
    assert payload["stream"] is False
    assert ollama_helper.execute_query.call_args.args[1] == ("COMPLETED", True, 11)
    assert ollama_helper.track.call_args.args == ("naming.completed",)
    assert ollama_helper.track.call_args.kwargs["model"] == "qwen3.5:2b"
    assert ollama_helper.track.call_args.kwargs["fallback_used"] is False


def test_empty_filename_finishes_failed_job(ollama_helper, monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = {"response": "", "thinking": "No filename available"}
    monkeypatch.setattr(ollama_helper.requests, "post", Mock(return_value=response))
    monkeypatch.setattr(ollama_helper, "extract_text", Mock(return_value="Synthetic invoice"))
    item = SimpleNamespace(filename="scan.pdf", filename_without_extension="scan", ocr_file="scan_OCR.pdf", file_naming_db_id=11)

    assert ollama_helper.generate_filename_ollama(item) == "scan"
    assert ollama_helper.execute_query.call_args.args[1] == ("FAILED", "Ollama returned an empty filename.", 11)
    assert ollama_helper.track.call_args.args == ("naming.failed",)
    assert ollama_helper.track.call_args.kwargs["reason"] == "empty_response"


def test_server_check_disables_thinking_and_sets_timeouts(ollama_helper, monkeypatch):
    get = Mock(return_value=Mock(status_code=200, text="Ollama is running"))
    post = Mock(return_value=Mock(status_code=200))
    monkeypatch.setattr(ollama_helper.requests, "get", get)
    monkeypatch.setattr(ollama_helper.requests, "post", post)

    assert ollama_helper.test_ollama_server("http://localhost", 11434, "qwen3.5:2b")[0] is True

    get.assert_called_once_with("http://localhost:11434", timeout=10)
    assert post.call_args.kwargs["timeout"] == 120
    assert post.call_args.kwargs["json"]["think"] is False
    assert post.call_args.kwargs["json"]["options"]["num_predict"] == 128
