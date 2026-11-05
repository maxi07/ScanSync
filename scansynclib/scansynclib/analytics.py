import hashlib
import logging
import os
from pathlib import Path
import re
import socket
import ssl
import sys
import tempfile
import threading
import time
import uuid
from urllib.parse import urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


_logger = logging.getLogger("scansync.analytics")
_slots = threading.BoundedSemaphore(16)
_fields = {
    "duration_ms", "total_duration_ms", "pages", "size_bytes", "extension",
    "provider", "model", "fallback_used", "language", "skipped_text_layer",
    "status", "status_code", "retries", "attempt", "queue_name",
    "reason", "targets", "successful_targets", "failed_targets", "method",
    "operation", "level", "location", "route", "error_code",
    "document_id", "logger",
}
_identifier = re.compile(r"^[A-Za-z0-9_.<>:/@+\-]+$")
_installation_id_path = Path("/app/data/analytics-installation-id")
_delivery_warning_lock = threading.Lock()
_delivery_warning_logged = False


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


urlopen = build_opener(_NoRedirect()).open


def elapsed_ms(started):
    return max(0, round((time.monotonic() - started) * 1000))


def file_metadata(path):
    try:
        extension = os.path.splitext(path)[1].lower().lstrip(".")
        if extension not in {"pdf", "png", "jpg", "jpeg", "tif", "tiff", "bmp", "gif", "webp"}:
            extension = "other"
        return {"size_bytes": os.path.getsize(path), "extension": extension}
    except OSError:
        return {}


def enabled():
    try:
        url = os.environ.get("ANALYTICS_URL", "").strip()
        parsed = urlsplit(url)
        return bool(
            parsed.scheme in {"http", "https"} and parsed.netloc
            and not parsed.username and not parsed.password
            and os.environ.get("ANALYTICS_API_KEY", "").strip()
        )
    except Exception:
        return False


def exception_metadata(error):
    result = {"error_type": type(error).__name__, "traceback": []}
    seen = set()
    current = error
    while current is not None and id(current) not in seen and len(seen) < 5:
        seen.add(id(current))
        error_code = getattr(current, "errno", None)
        if isinstance(error_code, int) and "error_code" not in result:
            result["error_code"] = error_code
        frames = []
        traceback = current.__traceback__
        while traceback is not None:
            frame = traceback.tb_frame
            module = str(frame.f_globals.get("__name__", "unknown"))
            function = frame.f_code.co_name
            frames.append({
                "module": module if _identifier.fullmatch(module) else "unknown",
                "function": function if _identifier.fullmatch(function) else "unknown",
                "line": traceback.tb_lineno,
            })
            traceback = traceback.tb_next
        result["traceback"].append({"error_type": type(current).__name__, "frames": frames[-24:]})
        cause = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
        if cause is None:
            cause = next((value for value in current.args if isinstance(value, BaseException)), None)
        current = cause
    return result


def _get_installation_id():
    temporary = None
    try:
        if not _installation_id_path.exists():
            _installation_id_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=_installation_id_path.parent, prefix=".analytics-id-", delete=False) as file:
                temporary = Path(file.name)
                file.write(f"install_{uuid.uuid4().hex}\n".encode("ascii"))
                os.fchmod(file.fileno(), 0o644)
            try:
                os.link(temporary, _installation_id_path)
            except FileExistsError:
                pass
        with _installation_id_path.open(encoding="ascii") as file:
            value = file.read(64).strip()
        if re.fullmatch(r"install_[a-f0-9]{32}", value):
            return value
    except Exception:
        _logger.debug("Analytics installation ID unavailable")
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                _logger.debug("Analytics temporary ID cleanup failed")
    return None


def _warn_delivery_once(url, *, error=None, status_code=None):
    global _delivery_warning_logged
    with _delivery_warning_lock:
        if _delivery_warning_logged:
            return
        _delivery_warning_logged = True
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or "invalid-host"
        if ":" in host:
            host = f"[{host}]"
        origin = f"{parsed.scheme}://{host}"
        if parsed.port is not None:
            origin += f":{parsed.port}"
        if isinstance(error, HTTPError):
            status_code = error.code
        if status_code is not None:
            reason = f"HTTP {status_code}"
            if 300 <= status_code < 400:
                reason += "; redirects are disabled, configure the final endpoint URL"
            elif status_code == 401:
                reason += "; check the analytics API key"
            elif status_code == 403:
                reason += "; access denied, check reverse-proxy and firewall rules"
        else:
            cause = error.reason if isinstance(error, URLError) else error
            if isinstance(cause, ssl.SSLCertVerificationError):
                reason = "TLS certificate verification failed"
            elif isinstance(cause, ssl.SSLError):
                reason = "TLS negotiation failed"
            elif isinstance(cause, socket.gaierror):
                reason = "DNS resolution failed"
            elif isinstance(cause, TimeoutError):
                reason = "request timed out"
            elif isinstance(cause, ConnectionRefusedError):
                reason = "connection refused"
            else:
                reason = type(cause).__name__
            code = getattr(cause, "verify_code", None) or getattr(cause, "errno", None)
            if isinstance(code, int):
                reason += f"; code={code}"
        logging.getLogger("shared_logger").warning(
            "Analytics delivery failed for %s (%s). Further delivery failures are suppressed "
            "until process restart; document processing continues.",
            origin, reason, extra={"analytics_handled": True},
        )
    except Exception:
        _logger.debug("Analytics delivery warning could not be logged")


def _send(payload, url, key):
    try:
        import json

        installation_id = _get_installation_id()
        if installation_id is not None:
            payload = {**payload, "user_id": installation_id}
        request = Request(
            url.rstrip("/") + "/event",
            data=json.dumps(payload, allow_nan=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json", "X-API-KEY": key,
                "User-Agent": f"ScanSync/{payload.get('app_version', 'dev')}",
            },
            method="POST",
        )
        with urlopen(request, timeout=1.5) as response:
            if response.status != 200:
                _warn_delivery_once(url, status_code=response.status)
    except Exception as error:
        _warn_delivery_once(url, error=error)
    finally:
        _slots.release()


def track(event_name, *, item=None, error=None, **metadata):
    acquired = False
    try:
        if not enabled():
            return
        if not isinstance(event_name, str) or not re.fullmatch(r"[a-z_]+\.[a-z_]+", event_name):
            return
        safe = {}
        for key, value in metadata.items():
            if key not in _fields or value is None:
                continue
            if key == "document_id" and (not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{24,64}", value)):
                continue
            if type(value) in (bool, int, float):
                safe[key] = value
            elif isinstance(value, str) and len(value) <= 160 and _identifier.fullmatch(value):
                safe[key] = value
        safe["service"] = os.environ.get("SCANSYNC_SERVICE", "unknown")
        if item is not None:
            analytics_id = getattr(item, "analytics_id", None)
            job_id = getattr(item, "db_id", None)
            added = getattr(item, "time_added", None)
            if isinstance(analytics_id, str) and re.fullmatch(r"[a-f0-9]{24,64}", analytics_id):
                safe["document_id"] = analytics_id
            elif isinstance(job_id, int) and added is not None:
                identity = f"{job_id}:{added.isoformat()}"
                safe["document_id"] = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        if error is not None:
            safe.update(exception_metadata(error))
            response = getattr(error, "response", None)
            status_code = getattr(error, "status_code", None) or getattr(response, "status_code", None)
            if isinstance(status_code, int):
                safe["status_code"] = status_code
        payload = {
            "event_name": event_name,
            "app_version": os.environ.get("APP_VERSION", "dev"),
            "metadata": safe,
        }
        acquired = _slots.acquire(blocking=False)
        if not acquired:
            _logger.debug("Analytics event dropped: send limit reached")
            return
        thread = threading.Thread(
            target=_send,
            args=(payload, os.environ["ANALYTICS_URL"].strip(), os.environ["ANALYTICS_API_KEY"].strip()),
            daemon=True,
            name="scansync-analytics",
        )
        thread.start()
        acquired = False
    except Exception:
        if acquired:
            _slots.release()
        _logger.debug("Analytics event could not be scheduled")


class AnalyticsHandler(logging.Handler):
    def emit(self, record):
        try:
            if record.name.startswith("scansync.analytics"):
                return
            current = logging.getLogger(record.name)
            while current is not None:
                if any(handler is not self for handler in current.handlers):
                    break
                current = current.parent if current.propagate else None
            else:
                if logging.lastResort is not None and record.levelno >= logging.lastResort.level:
                    logging.lastResort.handle(record)
            if record.levelno < logging.ERROR or getattr(record, "analytics_handled", False):
                return
            if record.name == "pika" or record.name.startswith("pika."):
                return
            error = record.exc_info[1] if record.exc_info else sys.exc_info()[1]
            if error is None:
                arguments = record.args.values() if isinstance(record.args, dict) else record.args
                error = next((value for value in arguments if isinstance(value, BaseException)), None)
            track(
                "service.error", error=error, level=record.levelname, logger=record.name,
                location=f"{record.module}:{record.funcName}:{record.lineno}",
            )
        except Exception:
            pass


def configure_logging():
    if not enabled():
        return
    root = logging.getLogger()
    if any(isinstance(handler, AnalyticsHandler) for handler in root.handlers):
        return
    root.addHandler(AnalyticsHandler())
    previous_hook = sys.excepthook
    previous_thread_hook = threading.excepthook

    def exception_hook(error_type, error, traceback):
        track("service.error", error=error, operation="uncaught_exception")
        previous_hook(error_type, error, traceback)

    def thread_hook(args):
        track("service.error", error=args.exc_value, operation="uncaught_thread_exception")
        previous_thread_hook(args)

    sys.excepthook = exception_hook
    threading.excepthook = thread_hook


def configure_flask(app):
    from flask import g, request

    @app.before_request
    def analytics_request_started():
        if enabled():
            g.analytics_started = time.monotonic()

    @app.after_request
    def analytics_request_finished(response):
        started = getattr(g, "analytics_started", None)
        is_failure = response.status_code >= 400
        is_page_view = (
            request.method == "GET"
            and 200 <= response.status_code < 300
            and response.mimetype == "text/html"
            and (request.endpoint or "").split(".")[-1] != "static"
            and request.headers.get("Sec-Fetch-Dest", "document") == "document"
            and request.headers.get("X-Requested-With") != "XMLHttpRequest"
        )
        if started is not None and (is_failure or is_page_view):
            track(
                "http.request_failed" if is_failure else "http.request_completed",
                route=request.url_rule.endpoint if request.url_rule else "unmatched",
                method=request.method, status_code=response.status_code, duration_ms=elapsed_ms(started),
            )
        return response
