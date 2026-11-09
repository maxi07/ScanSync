from unittest.mock import Mock

import pytest

from scansynclib import health


@pytest.fixture(autouse=True)
def health_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(health, "HEALTH_DIR", tmp_path)
    monkeypatch.setattr(health, "_cache", None)
    monkeypatch.setattr(health.socket, "gethostname", lambda: "replica-a")
    monkeypatch.delenv("SCANSYNC_SERVICE", raising=False)
    monkeypatch.delenv("HEALTH_WORKER_REPLICAS", raising=False)
    return tmp_path


def test_local_health_requires_a_fresh_ready_heartbeat(monkeypatch):
    monkeypatch.setenv("SCANSYNC_SERVICE", "ocr_service")
    assert health.check_worker()["ok"] is False
    health._write_worker("ocr_service", False)
    assert health.check_worker()["reason"] == "not_ready"
    health._write_worker("ocr_service", True)
    assert health.check_worker()["ok"] is True
    now = health.time.time()
    monkeypatch.setattr(health.time, "time", lambda: now + health.MAX_AGE + 1)
    assert health.check_worker()["reason"] == "stale"


@pytest.mark.parametrize("record", [
    "invalid json", "[]", '{"ok": "true", "updated_at": 1}',
    '{"ok": true, "updated_at": "yesterday"}',
    '{"ok": true, "updated_at": true}', '{"ok": true, "updated_at": NaN}',
    '{"ok": true, "updated_at": ' + '1' * 400 + '}',
])
def test_invalid_heartbeat_is_not_healthy(health_storage, record):
    path = health_storage / "invalid.json"
    path.write_text(record)
    assert health.read_worker(path)["ok"] is False
    assert health.read_worker(path)["reason"] in {"ValueError", "JSONDecodeError", "OverflowError"}


def test_missing_service_is_an_explicit_failure():
    assert health.check_worker() == {"ok": False, "reason": "Unknown or missing SCANSYNC_SERVICE"}


def test_reporter_is_opt_in_outside_service_containers(mocker):
    thread = mocker.patch.object(health.threading, "Thread")
    health.start_worker_health(lambda: True)
    thread.assert_not_called()


def test_reporter_tracks_connection_and_owner_liveness(monkeypatch, mocker):
    monkeypatch.setenv("SCANSYNC_SERVICE", "ocr_service")
    owner = Mock()
    owner.is_alive.return_value = True
    mocker.patch.object(health.threading, "current_thread", return_value=owner)
    thread = mocker.patch.object(health.threading, "Thread")
    health.start_worker_health(lambda: True)
    assert health.check_worker()["ok"] is True
    mocker.patch.object(health.time, "sleep", side_effect=lambda _: setattr(owner.is_alive, "return_value", False))
    thread.call_args.kwargs["target"]()
    assert health.check_worker()["ok"] is False


def test_heartbeat_write_failure_is_logged_locally(monkeypatch, mocker, caplog):
    monkeypatch.setenv("SCANSYNC_SERVICE", "ocr_service")
    mocker.patch.object(health.threading, "Thread")
    mocker.patch.object(health, "_write_worker", side_effect=PermissionError("read-only storage"))
    health.start_worker_health(lambda: True)
    assert "Cannot write worker health for ocr_service" in caplog.text
    assert health.check_worker()["ok"] is False


@pytest.fixture
def ready_services(mocker):
    probe = mocker.patch.object(health, "_probe", return_value={"ok": True})
    for service in health.WORKERS:
        health._write_worker(service, True)
    return probe


def test_overview_includes_every_service(ready_services):
    result = health.get_service_health()
    assert result["ok"] is True
    assert set(result["services"]) == {*health.WORKERS, "web_service", "rabbitmq", "redis", "smb_service"}
    assert result["services"]["ocr_service"]["ready"] == 1
    assert ready_services.call_count == 3


def test_all_expected_replicas_must_be_present(ready_services, monkeypatch):
    monkeypatch.setenv("HEALTH_WORKER_REPLICAS", '{"ocr_service":2}')
    result = health._collect_services()
    assert result["ok"] is False
    assert result["services"]["ocr_service"]["expected"] == 2
    monkeypatch.setattr(health.socket, "gethostname", lambda: "replica-b")
    health._write_worker("ocr_service", True)
    assert health._collect_services()["ok"] is True


def test_disconnected_replica_makes_service_unhealthy(ready_services, monkeypatch):
    monkeypatch.setattr(health.socket, "gethostname", lambda: "replica-b")
    health._write_worker("ocr_service", False)
    assert health._collect_services()["services"]["ocr_service"]["ok"] is False


def test_stale_replicas_do_not_count_as_ready(ready_services, monkeypatch):
    now = health.time.time()
    monkeypatch.setattr(health.time, "time", lambda: now + health.MAX_AGE + 1)
    result = health._collect_services()
    assert result["ok"] is False
    assert result["services"]["ocr_service"]["ready"] == 0


def test_old_deployments_do_not_poison_a_healthy_replacement(ready_services, monkeypatch):
    now = health.time.time()
    monkeypatch.setattr(health.time, "time", lambda: now + health.MAX_AGE + 1)
    monkeypatch.setattr(health.socket, "gethostname", lambda: "replica-b")
    for service in health.WORKERS:
        health._write_worker(service, True)
    assert health._collect_services()["ok"] is True


def test_snapshot_is_cached_for_30_seconds(ready_services, mocker):
    clock = mocker.patch.object(health.time, "monotonic", return_value=0)
    first = health.get_service_health()
    clock.return_value = 29
    assert health.get_service_health() is first
    assert ready_services.call_count == 3
    clock.return_value = 30
    assert health.get_service_health() is not first
    assert ready_services.call_count == 6


@pytest.mark.parametrize("value", ['{"unknown":1}', '{"ocr_service":0}', '{"ocr_service":true}', '[]', 'invalid'])
def test_invalid_replica_configuration_is_rejected(monkeypatch, value):
    monkeypatch.setenv("HEALTH_WORKER_REPLICAS", value)
    with pytest.raises(ValueError):
        health.get_service_health()


def test_dependency_failure_is_reported(ready_services):
    ready_services.return_value = {"ok": False, "reason": "ConnectionRefusedError"}
    result = health.get_service_health()
    assert result["ok"] is False
    assert result["services"]["redis"]["reason"] == "ConnectionRefusedError"


def test_tcp_probe_closes_connection_and_uses_timeout(mocker):
    connect = mocker.patch.object(health.socket, "create_connection")
    assert health._probe("rabbitmq", 5672) == {"ok": True, "check": "tcp"}
    connect.assert_called_once_with(("rabbitmq", 5672), timeout=1)
    connect.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize("reply, expected", [(b"+PONG\r\n", True), (b"-ERR unavailable\r\n", False), (b"", False)])
def test_redis_probe_checks_protocol_response(mocker, reply, expected):
    connect = mocker.patch.object(health.socket, "create_connection")
    connection = connect.return_value.__enter__.return_value
    connection.makefile.return_value.__enter__.return_value.readline.return_value = reply
    assert health._probe("redis", 6379, redis=True)["ok"] is expected
    connection.sendall.assert_called_once_with(b"*1\r\n$4\r\nPING\r\n")


def test_probe_connection_failure_is_not_healthy(mocker):
    mocker.patch.object(health.socket, "create_connection", side_effect=TimeoutError)
    assert health._probe("smb_service", 445) == {"ok": False, "check": "tcp", "reason": "TimeoutError"}


def test_consumer_starts_health_for_its_own_connection(mocker):
    from scansynclib import rabbitmq

    client = mocker.patch.object(rabbitmq, "RabbitMQClient").return_value
    start = mocker.patch.object(rabbitmq, "start_worker_health")
    callback = Mock()
    rabbitmq.consume("queue", callback)
    start.assert_called_once_with(client.is_open)
    client.consume.assert_called_once_with("queue", callback, prefetch_count=1, auto_ack=False)


def test_detection_starts_health_before_connecting(mocker):
    from detection_service import main as detection

    mocker.patch("scansynclib.cleanup.cleanup_dangling_documents")
    mocker.patch.object(detection, "ensure_scan_directory_exists")
    client = mocker.patch.object(detection, "RabbitMQClient").return_value
    client.ensure_connection.side_effect = KeyboardInterrupt
    start = mocker.patch.object(detection, "start_worker_health")
    with pytest.raises(KeyboardInterrupt):
        detection.main()
    start.assert_called_once_with(client.is_open)
