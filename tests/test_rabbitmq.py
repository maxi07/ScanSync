import pickle

import pika.exceptions
import pytest

from scansynclib import rabbitmq
from scansynclib.rabbitmq import RabbitMQClient


class _ForwardItem:
    filename = "doc.pdf"


class FakeChannel:
    """Minimal stand-in for a pika channel used in the tests."""

    def __init__(self):
        self.is_open = True
        self.channel_number = 1
        self.queue_declare_calls = []
        self.exchange_declare_calls = []
        self.basic_publish_calls = []
        self.basic_qos_calls = []
        self.basic_consume_calls = []
        self.publish_side_effect = None
        self.start_consuming_side_effect = None

    def basic_qos(self, prefetch_count=1):
        self.basic_qos_calls.append(prefetch_count)

    def queue_declare(self, queue, durable=True):
        self.queue_declare_calls.append(queue)

    def exchange_declare(self, exchange, exchange_type="fanout"):
        self.exchange_declare_calls.append((exchange, exchange_type))

    def basic_publish(self, exchange="", routing_key="", body=None, properties=None):
        if self.publish_side_effect is not None:
            effect = self.publish_side_effect
            self.publish_side_effect = None
            raise effect
        self.basic_publish_calls.append((exchange, routing_key, body, properties))

    def basic_consume(self, queue, on_message_callback, auto_ack=False):
        self.basic_consume_calls.append((queue, on_message_callback, auto_ack))

    def start_consuming(self):
        if self.start_consuming_side_effect is not None:
            effect = self.start_consuming_side_effect.pop(0)
            raise effect


class FakeConnection:
    def __init__(self, channel):
        self.is_open = True
        self._channel = channel
        self.process_data_events_calls = []

    def channel(self):
        return self._channel

    def process_data_events(self, time_limit=1):
        self.process_data_events_calls.append(time_limit)

    def close(self):
        self.is_open = False
        self._channel.is_open = False


@pytest.fixture
def fake_broker(mocker):
    """Patch pika.BlockingConnection to hand out fresh fake connections."""
    channels = []
    connections = []

    def factory(*args, **kwargs):
        channel = FakeChannel()
        connection = FakeConnection(channel)
        channels.append(channel)
        connections.append(connection)
        return connection

    blocking = mocker.patch("scansynclib.rabbitmq.pika.BlockingConnection", side_effect=factory)
    mocker.patch("scansynclib.rabbitmq.time.sleep")
    return {"blocking": blocking, "channels": channels, "connections": connections}


def test_publish_establishes_connection_once_and_reuses(fake_broker):
    client = RabbitMQClient(name="test")

    assert client.publish(b"one", queue_name="q") is True
    assert client.publish(b"two", queue_name="q") is True

    # Connection is established a single time and then kept alive.
    assert fake_broker["blocking"].call_count == 1
    channel = fake_broker["channels"][0]
    assert len(channel.basic_publish_calls) == 2
    # The queue is declared only once thanks to the declared-queue cache.
    assert channel.queue_declare_calls == ["q"]


def test_publish_marks_messages_persistent(fake_broker):
    client = RabbitMQClient(name="test")
    client.publish(b"payload", queue_name="q", persistent=True)

    channel = fake_broker["channels"][0]
    _, routing_key, body, properties = channel.basic_publish_calls[0]
    assert routing_key == "q"
    assert body == b"payload"
    assert properties.delivery_mode == 2


def test_publish_reconnects_on_stream_lost(fake_broker):
    client = RabbitMQClient(name="test")
    assert client.publish(b"first", queue_name="q") is True

    # Make the next publish fail as if the broker dropped the connection.
    fake_broker["channels"][0].publish_side_effect = pika.exceptions.StreamLostError("boom")

    assert client.publish(b"second", queue_name="q") is True
    # A new connection was established to recover.
    assert fake_broker["blocking"].call_count == 2
    # The message was delivered on the freshly created channel.
    assert len(fake_broker["channels"][1].basic_publish_calls) == 1


def test_publish_returns_false_when_broker_unavailable(mocker):
    mocker.patch("scansynclib.rabbitmq.time.sleep")
    mocker.patch(
        "scansynclib.rabbitmq.pika.BlockingConnection",
        side_effect=pika.exceptions.AMQPConnectionError("down"),
    )
    client = RabbitMQClient(name="test")
    assert client.publish(b"data", queue_name="q") is False


def test_publish_to_exchange_declares_exchange(fake_broker):
    assert rabbitmq.publish_to_exchange("sse", b"body", exchange_type="fanout") is True
    channel = fake_broker["channels"][0]
    assert ("sse", "fanout") in channel.exchange_declare_calls
    published_exchange = channel.basic_publish_calls[0][0]
    assert published_exchange == "sse"


def test_forward_to_rabbitmq_pickles_item(mocker):
    publish = mocker.patch.object(rabbitmq._publisher, "publish", return_value=True)

    item = _ForwardItem()
    assert rabbitmq.forward_to_rabbitmq("upload_queue", item) is True
    publish.assert_called_once()
    _, kwargs = publish.call_args
    body = publish.call_args.args[0]
    assert pickle.loads(body).filename == "doc.pdf"
    assert kwargs["queue_name"] == "upload_queue"


def test_consume_reconnects_on_connection_error(fake_broker):
    client = RabbitMQClient(name="test")

    def on_message(ch, method, properties, body):
        pass

    # First start_consuming raises a connection error (triggering reconnect),
    # the second raises KeyboardInterrupt to break out of the infinite loop.
    def prime_channel(*args, **kwargs):
        channel = FakeChannel()
        connection = FakeConnection(channel)
        if len(fake_broker["channels"]) == 0:
            channel.start_consuming_side_effect = [pika.exceptions.AMQPConnectionError("lost")]
        else:
            channel.start_consuming_side_effect = [KeyboardInterrupt()]
        fake_broker["channels"].append(channel)
        return connection

    fake_broker["blocking"].side_effect = prime_channel

    with pytest.raises(KeyboardInterrupt):
        client.consume("q", on_message)

    # The consumer reconnected after the first failure.
    assert fake_broker["blocking"].call_count == 2


def test_connect_rabbitmq_returns_connection_and_channel(fake_broker):
    result = rabbitmq.connect_rabbitmq(["a", "b"])
    assert result is not None
    connection, channel = result
    assert channel.queue_declare_calls == ["a", "b"]


def test_connect_rabbitmq_returns_none_on_failure(mocker):
    mocker.patch("scansynclib.rabbitmq.time.sleep")
    mocker.patch(
        "scansynclib.rabbitmq.pika.BlockingConnection",
        side_effect=pika.exceptions.AMQPConnectionError("down"),
    )
    assert rabbitmq.connect_rabbitmq(["a"]) is None


def test_process_events_services_heartbeats(fake_broker):
    client = RabbitMQClient(name="test")
    client.ensure_connection()
    client.process_events(1)
    assert fake_broker["connections"][0].process_data_events_calls == [1]
