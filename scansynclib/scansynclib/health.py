"""Local worker heartbeats and a cached, replica-aware service overview."""

import json
import logging
import math
import os
from pathlib import Path
import socket
import threading
import time
from collections.abc import Callable


WORKERS = ("detection_service", "metadata_service", "ocr_service", "file_naming_service", "upload_service")
HEALTH_DIR = Path("/app/data/health")
HEARTBEAT_INTERVAL = 15
MAX_AGE = 60
CACHE_SECONDS = 30
_cache = None
_cache_lock = threading.Lock()


def _record_path(service: str) -> Path:
    return HEALTH_DIR / service / f"{socket.gethostname()}.json"


def read_worker(path: Path) -> dict:
    try:
        record = json.loads(path.read_text())
        if not isinstance(record, dict) or type(record.get("ok")) is not bool:
            raise ValueError("Invalid worker state")
        updated = record.get("updated_at")
        if type(updated) not in (int, float) or not math.isfinite(updated):
            raise ValueError("Invalid heartbeat timestamp")
        age = time.time() - updated
        fresh = 0 <= age <= MAX_AGE
        return {
            "ok": record["ok"] and fresh,
            "fresh": fresh,
            "reason": "stale" if not fresh else ("ready" if record["ok"] else "not_ready"),
        }
    except (OSError, ValueError, OverflowError) as error:
        return {"ok": False, "fresh": False, "reason": type(error).__name__}


def _write_worker(service: str, ready: bool) -> None:
    path = _record_path(service)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"ok": ready, "updated_at": time.time()}))
    temporary.replace(path)
    # Retain short-lived stale records for diagnostics, not indefinitely across deployments.
    for old in path.parent.glob("*.json"):
        try:
            if old.stat().st_mtime < time.time() - 86400:
                old.unlink()
        except FileNotFoundError:
            continue


def start_worker_health(is_ready: Callable[[], bool]) -> None:
    service = os.environ.get("SCANSYNC_SERVICE")
    if service is None:
        return
    if service not in WORKERS:
        raise ValueError(f"Unknown worker service: {service}")
    owner = threading.current_thread()

    def report():
        try:
            _write_worker(service, owner.is_alive() and is_ready())
        except OSError:
            logging.getLogger("scansync.health").warning("Cannot write worker health for %s", service, exc_info=True)

    def run():
        while owner.is_alive():
            time.sleep(HEARTBEAT_INTERVAL)
            report()

    report()
    threading.Thread(target=run, daemon=True, name="worker-health").start()


def _probe(host: str, port: int, *, redis: bool = False) -> dict:
    try:
        with socket.create_connection((host, port), timeout=1) as connection:
            if redis:
                connection.sendall(b"*1\r\n$4\r\nPING\r\n")
                with connection.makefile("rb") as response:
                    if response.readline(64) != b"+PONG\r\n":
                        return {"ok": False, "check": "ping", "reason": "unexpected_response"}
        return {"ok": True, "check": "ping" if redis else "tcp"}
    except OSError as error:
        return {"ok": False, "check": "ping" if redis else "tcp", "reason": type(error).__name__}


def _worker_counts() -> dict[str, int]:
    overrides = json.loads(os.environ.get("HEALTH_WORKER_REPLICAS", "{}"))
    if not isinstance(overrides, dict) or any(
        name not in WORKERS or type(count) is not int or count < 1
        for name, count in overrides.items()
    ):
        raise ValueError("HEALTH_WORKER_REPLICAS must map worker names to positive replica counts")
    return {name: overrides.get(name, 1) for name in WORKERS}


def _collect_services() -> dict:
    services = {"web_service": {"ok": True, "check": "http"}}
    for service, expected in _worker_counts().items():
        try:
            instances = {
                path.stem: read_worker(path)
                for path in (HEALTH_DIR / service).glob("*.json")
            }
        except OSError as error:
            services[service] = {"ok": False, "expected": expected, "reason": type(error).__name__}
            continue
        active = [state for state in instances.values() if state["fresh"]]
        services[service] = {
            "ok": len(active) >= expected and all(state["ok"] for state in active),
            "expected": expected,
            "ready": sum(state["ok"] for state in active),
            "instances": instances,
        }
    services["rabbitmq"] = _probe("rabbitmq", 5672)
    services["redis"] = _probe("redis", 6379, redis=True)
    services["smb_service"] = _probe("smb_service", 445)
    return {"ok": all(state["ok"] for state in services.values()), "services": services, "checked_at": time.time()}


def get_service_health() -> dict:
    global _cache
    with _cache_lock:
        if _cache is None or time.monotonic() - _cache[0] >= CACHE_SECONDS:
            result = _collect_services()
            _cache = (time.monotonic(), result)
        return _cache[1]


def check_worker() -> dict:
    service = os.environ.get("SCANSYNC_SERVICE")
    if service not in WORKERS:
        return {"ok": False, "reason": "Unknown or missing SCANSYNC_SERVICE"}
    return read_worker(_record_path(service))


if __name__ == "__main__":
    result = check_worker()
    print(json.dumps(result))
    raise SystemExit(0 if result["ok"] else 1)
