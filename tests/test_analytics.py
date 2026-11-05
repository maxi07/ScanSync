from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import importlib.util
import json
import logging
import socket
import ssl
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

from scansynclib import analytics


@pytest.fixture(autouse=True)
def installation_storage(monkeypatch, tmp_path):
    path = tmp_path / "data" / "analytics-installation-id"
    monkeypatch.setattr(analytics, "_installation_id_path", path)
    monkeypatch.setattr(analytics, "_delivery_warning_logged", False)
    return path


@pytest.fixture
def sender(monkeypatch):
    monkeypatch.setenv("ANALYTICS_URL", "https://analytics.example.test")
    monkeypatch.setenv("ANALYTICS_API_KEY", "test-key")
    monkeypatch.setenv("SCANSYNC_SERVICE", "ocr_service")
    monkeypatch.setenv("APP_VERSION", "test-version")
    send = Mock()
    monkeypatch.setattr(analytics, "_send", send)

    def start_thread(*, target, args, **kwargs):
        def run():
            try:
                target(*args)
            finally:
                analytics._slots.release()
        return SimpleNamespace(start=run)

    monkeypatch.setattr(analytics.threading, "Thread", start_thread)
    return send


@pytest.mark.parametrize("missing", ["ANALYTICS_URL", "ANALYTICS_API_KEY"])
def test_missing_configuration_does_nothing(sender, monkeypatch, missing, installation_storage):
    monkeypatch.delenv(missing)
    analytics.track("ocr.completed", duration_ms=12)
    sender.assert_not_called()
    assert not installation_storage.exists()


def test_payload_allowlist_and_document_correlation(sender):
    item = SimpleNamespace(db_id=42, time_added=datetime(2026, 11, 4), filename="medical-letter.pdf")
    analytics.track("ocr.completed", item=item, duration_ms=12, filename=item.filename, ocr_text="private text", pages=2)
    payload = sender.call_args.args[0]
    assert payload["app_version"] == "test-version"
    assert payload["metadata"] == {
        "duration_ms": 12, "pages": 2, "service": "ocr_service",
        "document_id": payload["metadata"]["document_id"],
    }
    assert len(payload["metadata"]["document_id"]) == 24
    assert "medical" not in json.dumps(payload)
    assert "private" not in json.dumps(payload)
    analytics.track("document.completed", item=item)
    assert sender.call_args.args[0]["metadata"]["document_id"] == payload["metadata"]["document_id"]


def test_traceback_excludes_messages_source_and_locals(sender):
    try:
        try:
            raise ValueError("private document text /mnt/scans/medical-letter.pdf")
        except ValueError as cause:
            raise RuntimeError("token=secret") from cause
    except RuntimeError as error:
        analytics.track("ocr.failed", error=error)
    payload = sender.call_args.args[0]
    metadata = payload["metadata"]
    assert metadata["error_type"] == "RuntimeError"
    assert [entry["error_type"] for entry in metadata["traceback"]] == ["RuntimeError", "ValueError"]
    assert metadata["traceback"][0]["frames"][0]["function"] == "test_traceback_excludes_messages_source_and_locals"
    serialized = json.dumps(payload)
    for sensitive in ["private", "medical", "/mnt/", "token", "secret", "raise RuntimeError"]:
        assert sensitive not in serialized


def test_logging_handler_never_formats_message(sender):
    record = logging.LogRecord("shared_logger", logging.ERROR, __file__, 10, "private document %s", ("secret.pdf",), None)
    analytics.AnalyticsHandler().emit(record)
    assert sender.call_args.args[0]["event_name"] == "service.error"
    assert "private" not in json.dumps(sender.call_args.args[0])
    assert "secret.pdf" not in json.dumps(sender.call_args.args[0])


def test_logging_inside_except_preserves_real_type(sender):
    try:
        raise FileNotFoundError("secret.pdf")
    except FileNotFoundError:
        record = logging.LogRecord("shared_logger", logging.ERROR, __file__, 10, "not found", (), None)
        analytics.AnalyticsHandler().emit(record)
    assert sender.call_args.args[0]["metadata"]["error_type"] == "FileNotFoundError"


def test_thread_start_failure_does_not_escape(sender, monkeypatch):
    monkeypatch.setattr(analytics.threading, "Thread", Mock(side_effect=RuntimeError("no threads")))
    analytics.track("ocr.started")
    sender.assert_not_called()
    assert analytics._slots.acquire(blocking=False)
    analytics._slots.release()


def test_saturation_drops_without_blocking(sender, monkeypatch):
    slots = Mock()
    slots.acquire.return_value = False
    monkeypatch.setattr(analytics, "_slots", slots)
    analytics.track("ocr.started")
    slots.acquire.assert_called_once_with(blocking=False)
    sender.assert_not_called()


def test_network_failure_does_not_escape(monkeypatch):
    monkeypatch.setattr(analytics, "urlopen", Mock(side_effect=OSError("unreachable")))
    assert analytics._slots.acquire(blocking=False)
    analytics._send({"event_name": "ocr.started"}, "https://analytics.example.test", "test-key")


@pytest.mark.parametrize("error, expected", [
    (HTTPError("https://secret-host/private?key=secret", 403, "secret response", {}, None), "HTTP 403"),
    (HTTPError("https://secret-host", 302, "secret response", {}, None), "redirects are disabled"),
    (URLError(socket.gaierror(-2, "private DNS details")), "DNS resolution failed"),
    (URLError(ssl.SSLCertVerificationError("private certificate details")), "TLS certificate verification failed"),
    (URLError(TimeoutError("private timeout details")), "request timed out"),
    (URLError(ConnectionRefusedError(111, "private connection details")), "connection refused"),
])
def test_delivery_failure_warns_once_without_secrets_or_recursion(monkeypatch, caplog, error, expected):
    post = Mock(side_effect=error)
    monkeypatch.setattr(analytics, "urlopen", post)
    track = Mock()
    monkeypatch.setattr(analytics, "track", track)
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [analytics.AnalyticsHandler(), caplog.handler])
    with caplog.at_level(logging.WARNING):
        for attempt in range(3):
            assert analytics._slots.acquire(blocking=False)
            analytics._send({"event_name": "service.started"}, "https://analytics.example.test/private?key=secret", "secret-api-key")
    warnings = [record for record in caplog.records if record.getMessage().startswith("Analytics delivery failed")]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "https://analytics.example.test" in message
    assert expected in message
    assert "process restart" in message
    assert warnings[0].analytics_handled is True
    for sensitive in ["secret", "private", "secret-api-key"]:
        assert sensitive not in message
    assert post.call_count == 3
    track.assert_not_called()


def test_concurrent_delivery_failures_warn_only_once(caplog):
    with caplog.at_level(logging.WARNING), ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda attempt: analytics._warn_delivery_once("https://analytics.example.test", status_code=403), range(32)))
    assert sum(record.getMessage().startswith("Analytics delivery failed") for record in caplog.records) == 1


def test_non_200_response_warns_once(monkeypatch, caplog):
    response = Mock(status=503)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(analytics, "urlopen", Mock(return_value=response))
    with caplog.at_level(logging.WARNING):
        for attempt in range(2):
            assert analytics._slots.acquire(blocking=False)
            analytics._send({"event_name": "service.started"}, "https://analytics.example.test", "secret-api-key")
    warnings = [record.getMessage() for record in caplog.records if record.getMessage().startswith("Analytics delivery failed")]
    assert len(warnings) == 1
    assert "HTTP 503" in warnings[0]


@pytest.mark.parametrize("app_version", ["dev", "v1.2.3"])
def test_http_contract(monkeypatch, app_version):
    response = Mock(status=200)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    post = Mock(return_value=response)
    monkeypatch.setattr(analytics, "urlopen", post)
    assert analytics._slots.acquire(blocking=False)
    payload = {"event_name": "ocr.started", "app_version": app_version}
    analytics._send(payload, "https://analytics.example.test/", "test-key")
    request = post.call_args.args[0]
    assert request.full_url == "https://analytics.example.test/event"
    assert request.get_header("X-api-key") == "test-key"
    assert request.get_header("User-agent") == f"ScanSync/{app_version}"
    assert json.loads(request.data) == {**payload, "user_id": analytics._get_installation_id()}
    assert post.call_args.kwargs["timeout"] == 1.5


def test_installation_id_survives_module_restart(installation_storage):
    identity = analytics._get_installation_id()
    assert identity.startswith("install_")
    assert len(identity) == 40
    assert installation_storage.read_text().strip() == identity
    spec = importlib.util.spec_from_file_location("analytics_restarted", analytics.__file__)
    restarted = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(restarted)
    restarted._installation_id_path = installation_storage
    assert restarted._get_installation_id() == identity


def test_concurrent_first_starts_share_one_id(installation_storage):
    with ThreadPoolExecutor(max_workers=8) as executor:
        identities = list(executor.map(lambda attempt: analytics._get_installation_id(), range(32)))
    assert len(set(identities)) == 1
    assert identities[0] is not None
    assert installation_storage.read_text().strip() == identities[0]
    assert list(installation_storage.parent.glob(".analytics-id-*")) == []


def test_invalid_persisted_id_never_exposes_hostname(installation_storage):
    installation_storage.parent.mkdir()
    installation_storage.write_text("Max-Personal-MacBook")
    assert analytics._get_installation_id() is None


def test_storage_failure_still_sends_event_without_id(monkeypatch, installation_storage):
    installation_storage.mkdir(parents=True)
    response = Mock(status=200)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    post = Mock(return_value=response)
    monkeypatch.setattr(analytics, "urlopen", post)
    assert analytics._slots.acquire(blocking=False)
    analytics._send({"event_name": "ocr.completed"}, "https://analytics.example.test", "test-key")
    assert json.loads(post.call_args.args[0].data) == {"event_name": "ocr.completed"}


def test_global_logging_and_uncaught_hooks_are_idempotent(sender, monkeypatch):
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    previous = Mock()
    previous_thread = Mock()
    monkeypatch.setattr(sys, "excepthook", previous)
    monkeypatch.setattr(analytics.threading, "excepthook", previous_thread)
    analytics.configure_logging()
    analytics.configure_logging()
    assert len(root.handlers) == 1
    logging.getLogger("third_party_client").error("private filename secret.pdf")
    assert sender.call_args.args[0]["event_name"] == "service.error"
    assert "secret.pdf" not in json.dumps(sender.call_args.args[0])
    error = ValueError("private contents")
    sys.excepthook(ValueError, error, None)
    previous.assert_called_once_with(ValueError, error, None)
    assert sender.call_args.args[0]["metadata"]["error_type"] == "ValueError"
    args = SimpleNamespace(exc_value=error)
    analytics.threading.excepthook(args)
    previous_thread.assert_called_once_with(args)


def test_opt_out_does_not_change_logging_or_exception_hooks(monkeypatch):
    monkeypatch.delenv("ANALYTICS_URL", raising=False)
    root = logging.getLogger()
    handlers = list(root.handlers)
    exception_hook = sys.excepthook
    thread_hook = analytics.threading.excepthook
    analytics.configure_logging()
    assert root.handlers == handlers
    assert sys.excepthook is exception_hook
    assert analytics.threading.excepthook is thread_hook


def test_analytics_preserves_default_local_error_and_warning_output(sender, monkeypatch):
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", [])
    fallback = Mock(level=logging.WARNING)
    monkeypatch.setattr(logging, "lastResort", fallback)
    monkeypatch.setattr(sys, "excepthook", Mock())
    monkeypatch.setattr(analytics.threading, "excepthook", Mock())
    analytics.configure_logging()
    logger = logging.getLogger("unconfigured_library")
    logger.warning("local warning remains visible")
    sender.assert_not_called()
    logger.error("local error remains visible")
    assert fallback.handle.call_count == 2
    assert sender.call_args.args[0]["event_name"] == "service.error"


def test_http_events_use_endpoint_not_private_url(sender):
    from flask import Flask

    app = Flask(__name__)
    analytics.configure_flask(app)

    @app.route("/documents/<name>")
    def document(name):
        return "", 403

    response = app.test_client().get("/documents/medical-letter.pdf?token=secret")
    assert response.status_code == 403
    payload = sender.call_args.args[0]
    assert payload["event_name"] == "http.request_failed"
    assert payload["metadata"]["route"] == "document"
    assert payload["metadata"]["status_code"] == 403
    assert "medical" not in json.dumps(payload)
    assert "secret" not in json.dumps(payload)


def test_one_page_load_emits_only_one_success_event(sender):
    from flask import Flask, Response, jsonify, redirect

    app = Flask(__name__, static_folder=None)
    analytics.configure_flask(app)

    @app.get("/")
    def index():
        return "<html>Dashboard</html>"

    @app.get("/assets/<name>", endpoint="static")
    def asset(name):
        return Response("synthetic asset", mimetype="text/css")

    @app.get("/cached", endpoint="cached_asset")
    def cached():
        return "", 304

    @app.get("/favicon.ico")
    def favicon():
        return Response(b"synthetic", mimetype="image/x-icon")

    @app.get("/stream")
    def stream():
        return Response("data: synthetic\n\n", mimetype="text/event-stream")

    @app.get("/api/status")
    def status():
        return jsonify({"documents": 1})

    @app.get("/redirect")
    def redirected():
        return redirect("/")

    client = app.test_client()
    assert client.get("/", headers={"Sec-Fetch-Dest": "document"}).status_code == 200
    for path in ["/assets/base.css", "/assets/dashboard.js", "/cached", "/favicon.ico", "/stream", "/api/status", "/redirect"]:
        assert client.get(path).status_code < 400
    sender.assert_called_once()
    payload = sender.call_args.args[0]
    assert payload["event_name"] == "http.request_completed"
    assert payload["metadata"]["route"] == "index"


@pytest.mark.parametrize("method, headers, status, mimetype", [
    ("GET", {"Sec-Fetch-Dest": "empty"}, 200, "text/html"),
    ("GET", {"Sec-Fetch-Dest": "iframe"}, 200, "text/html"),
    ("GET", {"X-Requested-With": "XMLHttpRequest"}, 200, "text/html"),
    ("GET", {}, 200, "application/json"),
    ("GET", {}, 302, "text/html"),
    ("GET", {}, 304, "text/html"),
    ("HEAD", {}, 200, "text/html"),
    ("POST", {}, 200, "text/html"),
])
def test_successful_background_requests_do_not_count_as_page_views(sender, method, headers, status, mimetype):
    from flask import Flask, Response

    app = Flask(__name__)
    analytics.configure_flask(app)

    @app.route("/", methods=["GET", "POST"])
    def index():
        return Response("synthetic", status=status, mimetype=mimetype)

    assert app.test_client().open("/", method=method, headers=headers).status_code == status
    sender.assert_not_called()


@pytest.mark.parametrize("status", [400, 403, 404, 429, 500])
def test_failed_asset_requests_are_still_reported(sender, status):
    from flask import Flask, Response

    app = Flask(__name__, static_folder=None)
    analytics.configure_flask(app)

    @app.get("/assets/<name>", endpoint="static")
    def asset(name):
        return Response("private filename", status=status, mimetype="text/css")

    assert app.test_client().get("/assets/private.css?token=secret", headers={"Sec-Fetch-Dest": "style"}).status_code == status
    sender.assert_called_once()
    payload = sender.call_args.args[0]
    assert payload["event_name"] == "http.request_failed"
    assert payload["metadata"]["status_code"] == status
    assert "private" not in json.dumps(payload)
    assert "secret" not in json.dumps(payload)


@pytest.mark.parametrize("logger_name", ["pika", "pika.adapters.utils.io_services_utils", "pika.adapters.utils.connection_workflow"])
def test_internal_pika_logs_are_not_separate_analytics_errors(sender, logger_name):
    record = logging.LogRecord(logger_name, logging.ERROR, __file__, 10, "private broker details", (), None)
    analytics.AnalyticsHandler().emit(record)
    sender.assert_not_called()


def test_structured_errors_are_not_sent_twice(sender):
    record = logging.LogRecord("shared_logger", logging.ERROR, __file__, 10, "already tracked", (), None)
    record.analytics_handled = True
    analytics.AnalyticsHandler().emit(record)
    sender.assert_not_called()


@pytest.mark.parametrize("mapping", [False, True])
def test_exception_arguments_supply_type_and_numeric_code_without_message(sender, mapping):
    error = ConnectionRefusedError(111, "private broker URL")
    record = logging.LogRecord("network.client", logging.ERROR, __file__, 10, "Request failed: %s", (error,), None)
    if mapping:
        record.args = {"error": error}
    analytics.AnalyticsHandler().emit(record)
    payload = sender.call_args.args[0]
    assert payload["metadata"]["logger"] == "network.client"
    assert payload["metadata"]["error_type"] == "ConnectionRefusedError"
    assert payload["metadata"]["error_code"] == 111
    assert "private broker URL" not in json.dumps(payload)


def test_wrapped_connection_errors_keep_the_underlying_numeric_reason(sender):
    error = ConnectionError(ConnectionRefusedError(111, "private broker URL"))
    analytics.track("queue.connection_failed", error=error, reason="broker_unavailable")
    metadata = sender.call_args.args[0]["metadata"]
    assert metadata["error_type"] == "ConnectionError"
    assert metadata["error_code"] == 111
    assert [entry["error_type"] for entry in metadata["traceback"]] == ["ConnectionError", "ConnectionRefusedError"]
    assert "private broker URL" not in json.dumps(metadata)


@pytest.mark.parametrize("url", ["", "  ", "not-a-url", "ftp://example.test", "https://user:password@example.test"])
def test_invalid_urls_disable_analytics(sender, monkeypatch, url):
    monkeypatch.setenv("ANALYTICS_URL", url)
    analytics.track("ocr.started")
    sender.assert_not_called()


def test_real_transport_posts_json_without_following_redirects(monkeypatch):
    received = []
    arrived = threading.Event()
    finished = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append((self.path, self.headers["X-API-KEY"], payload))
            self.send_response(302)
            self.send_header("Location", "/must-not-receive-key")
            self.end_headers()
            arrived.set()

        def do_GET(self):
            received.append((self.path, self.headers.get("X-API-KEY"), None))
            self.send_response(200)
            self.end_headers()

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    monkeypatch.setenv("ANALYTICS_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("ANALYTICS_API_KEY", "synthetic-key")
    original_send = analytics._send

    def observed_send(*args):
        try:
            original_send(*args)
        finally:
            finished.set()

    monkeypatch.setattr(analytics, "_send", observed_send)
    try:
        analytics.track("ocr.completed", pages=2)
        assert arrived.wait(3)
        assert finished.wait(3)
        assert len(received) == 1
        path, key, payload = received[0]
        assert path == "/event"
        assert key == "synthetic-key"
        assert payload["event_name"] == "ocr.completed"
        assert payload["user_id"] == analytics._get_installation_id()
        assert payload["metadata"]["pages"] == 2
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=3)
