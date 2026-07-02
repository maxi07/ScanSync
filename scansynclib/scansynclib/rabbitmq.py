"""Unified RabbitMQ connection handling for all ScanSync services.

This module centralises every RabbitMQ interaction so that services no longer
each build and tear down their own connections. A single, long-lived
connection per process is established lazily and kept alive. Publishing and
consuming both transparently reconnect when the broker drops the connection,
which prevents the "missed heartbeats from client" churn where a new
connection was opened for every message.

Two building blocks are provided:

* :class:`RabbitMQClient` – a resilient wrapper around a single pika
  ``BlockingConnection``. It reconnects automatically and re-declares queues
  and exchanges after a reconnect.
* Module level helpers (:func:`publish`, :func:`forward_to_rabbitmq`,
  :func:`consume`, ...) that operate on a shared, process-wide publisher
  client so callers can keep the previous simple function based API.
"""

import pickle
import socket
import threading
import time

import pika
import pika.exceptions

from scansynclib.logging import logger

# Host of the RabbitMQ broker. All services run in the same docker network and
# reach the broker through the ``rabbitmq`` service name.
RABBITMQ_HOST = "rabbitmq"

# A generous heartbeat keeps the connection alive across the long, blocking
# operations (OCR, uploads, AI file naming) that happen between two AMQP
# interactions. The previous default of 30/60 seconds caused the broker to
# close idle-looking connections while a service was busy.
DEFAULT_HEARTBEAT = 600

# Number of connection attempts (and delay between them) before giving up on
# the initial connect.
CONNECTION_ATTEMPTS = 10
CONNECTION_RETRY_DELAY = 2

# Delay before a consumer loop retries after the connection was lost.
RECONNECT_DELAY = 5

# Exceptions that indicate the underlying connection/channel is gone and a
# reconnect should be attempted.
_CONNECTION_ERRORS = (
    pika.exceptions.AMQPConnectionError,
    pika.exceptions.ConnectionClosed,
    pika.exceptions.StreamLostError,
    pika.exceptions.ChannelClosed,
    pika.exceptions.ChannelWrongStateError,
    socket.gaierror,
)


class RabbitMQClient:
    """A resilient, reusable RabbitMQ connection wrapper.

    The client owns a single connection and channel. Both are created lazily on
    first use and automatically recreated whenever the broker drops them, so a
    connection is established once and then kept alive for the lifetime of the
    process.
    """

    def __init__(self, heartbeat: int = DEFAULT_HEARTBEAT, host: str = RABBITMQ_HOST, name: str = "rabbitmq"):
        self._heartbeat = heartbeat
        self._host = host
        self._name = name
        self._connection = None
        self._channel = None
        self._declared_queues = set()
        self._declared_exchanges = set()
        # BlockingConnection is not thread safe; serialise access so the client
        # can be shared between e.g. Flask request threads.
        self._lock = threading.RLock()

    @property
    def _parameters(self) -> pika.ConnectionParameters:
        return pika.ConnectionParameters(
            host=self._host,
            heartbeat=self._heartbeat,
            blocked_connection_timeout=300,
        )

    def _connect(self) -> bool:
        """Establish the connection, retrying a bounded number of times."""
        self._close_quietly()
        for attempt in range(1, CONNECTION_ATTEMPTS + 1):
            try:
                self._connection = pika.BlockingConnection(self._parameters)
                self._channel = self._connection.channel()
                self._channel.basic_qos(prefetch_count=1)
                # Queues/exchanges must be re-declared on the fresh channel.
                self._declared_queues.clear()
                self._declared_exchanges.clear()
                logger.info(f"Connected to RabbitMQ ({self._name}) on channel {self._channel.channel_number}.")
                return True
            except _CONNECTION_ERRORS as e:
                logger.warning(f"RabbitMQ connection attempt {attempt}/{CONNECTION_ATTEMPTS} failed: {e}")
                time.sleep(CONNECTION_RETRY_DELAY)
        logger.critical("Couldn't connect to RabbitMQ.")
        return False

    def _close_quietly(self):
        for closable in (self._channel, self._connection):
            try:
                if closable is not None and closable.is_open:
                    closable.close()
            except Exception:
                pass
        self._channel = None
        self._connection = None
        self._declared_queues.clear()
        self._declared_exchanges.clear()

    def is_open(self) -> bool:
        return (
            self._connection is not None
            and self._connection.is_open
            and self._channel is not None
            and self._channel.is_open
        )

    @property
    def channel(self):
        return self._channel

    @property
    def connection(self):
        return self._connection

    def process_events(self, time_limit: float = 1):
        """Service heartbeats and dispatch pending events on the connection.

        Useful for publisher-only services that otherwise sit in a polling loop
        and would never give pika a chance to send heartbeats.
        """
        with self._lock:
            if not self.is_open():
                return
            try:
                self._connection.process_data_events(time_limit)
            except _CONNECTION_ERRORS as e:
                logger.warning(f"RabbitMQ connection lost while processing events: {e}")
                self._close_quietly()

    def ensure_connection(self) -> bool:
        """Make sure a usable connection and channel are available."""
        with self._lock:
            if self.is_open():
                return True
            return self._connect()

    def declare_queue(self, queue_name: str, durable: bool = True) -> bool:
        with self._lock:
            if not queue_name or queue_name in self._declared_queues:
                return True
            if not self.ensure_connection():
                return False
            self._channel.queue_declare(queue=queue_name, durable=durable)
            self._declared_queues.add(queue_name)
            return True

    def declare_exchange(self, exchange: str, exchange_type: str = "fanout") -> bool:
        with self._lock:
            if not exchange or exchange in self._declared_exchanges:
                return True
            if not self.ensure_connection():
                return False
            self._channel.exchange_declare(exchange=exchange, exchange_type=exchange_type)
            self._declared_exchanges.add(exchange)
            return True

    def publish(
        self,
        body: bytes,
        queue_name: str = "",
        exchange: str = "",
        routing_key: str = None,
        persistent: bool = True,
        declare_queue: bool = True,
        exchange_type: str = None,
    ) -> bool:
        """Publish a message, transparently reconnecting on failure.

        Args:
            body: The already serialised message body.
            queue_name: Target queue for direct (default exchange) publishing.
            exchange: Exchange to publish to (defaults to the direct exchange).
            routing_key: Routing key; defaults to ``queue_name``.
            persistent: Mark the message as persistent (delivery_mode=2).
            declare_queue: Declare ``queue_name`` before publishing.
            exchange_type: If given, declare ``exchange`` with this type.

        Returns:
            ``True`` if the message was published, ``False`` otherwise.
        """
        if routing_key is None:
            routing_key = queue_name
        properties = pika.BasicProperties(delivery_mode=2) if persistent else None

        with self._lock:
            # Two attempts: the first may fail on a stale connection, the retry
            # runs on a freshly established one.
            for attempt in range(2):
                try:
                    if not self.ensure_connection():
                        return False
                    if exchange_type:
                        if not self.declare_exchange(exchange, exchange_type):
                            return False
                    if declare_queue and queue_name:
                        if not self.declare_queue(queue_name):
                            return False
                    self._channel.basic_publish(
                        exchange=exchange,
                        routing_key=routing_key,
                        body=body,
                        properties=properties,
                    )
                    return True
                except _CONNECTION_ERRORS as e:
                    logger.warning(f"RabbitMQ publish failed ({e}); reconnecting (attempt {attempt + 1}/2).")
                    self._close_quietly()
                except Exception:
                    logger.exception("Unexpected error while publishing to RabbitMQ.")
                    return False
            logger.error("Failed to publish message to RabbitMQ after reconnecting.")
            return False

    def consume(self, queue_names, on_message_callback, prefetch_count: int = 1, auto_ack: bool = False):
        """Consume messages forever, reconnecting when the connection drops.

        Args:
            queue_names: A queue name or list of queue names to declare. The
                first queue is the one that is actually consumed.
            on_message_callback: The pika message callback.
            prefetch_count: QoS prefetch count.
            auto_ack: Whether to auto-acknowledge messages.
        """
        if isinstance(queue_names, str):
            queue_names = [queue_names]
        consume_queue = queue_names[0]

        while True:
            try:
                if not self.ensure_connection():
                    time.sleep(RECONNECT_DELAY)
                    continue
                self._channel.basic_qos(prefetch_count=prefetch_count)
                for queue_name in queue_names:
                    self.declare_queue(queue_name)
                self._channel.basic_consume(
                    queue=consume_queue,
                    on_message_callback=on_message_callback,
                    auto_ack=auto_ack,
                )
                logger.info(f"Consuming from queue '{consume_queue}', waiting for messages...")
                self._channel.start_consuming()
            except _CONNECTION_ERRORS as e:
                logger.error(f"RabbitMQ connection lost: {e}. Reconnecting in {RECONNECT_DELAY} seconds...")
                self._close_quietly()
                time.sleep(RECONNECT_DELAY)
            except Exception as e:
                logger.exception(f"Unexpected error in consumer: {e}. Restarting consumer...")
                self._close_quietly()
                time.sleep(RECONNECT_DELAY)

    def close(self):
        with self._lock:
            self._close_quietly()


# ---------------------------------------------------------------------------
# Shared, process-wide publisher client and function based helpers.
# ---------------------------------------------------------------------------

_publisher = RabbitMQClient(name="publisher")
_publisher_lock = threading.Lock()


def get_publisher() -> RabbitMQClient:
    """Return the shared publisher client for the current process."""
    return _publisher


def publish(queue_name: str, body: bytes, persistent: bool = True) -> bool:
    """Publish raw ``body`` to ``queue_name`` on the shared connection."""
    return _publisher.publish(body, queue_name=queue_name, persistent=persistent)


def forward_to_rabbitmq(queue_name: str, item) -> bool:
    """Serialise ``item`` and forward it to ``queue_name``.

    Uses the shared, long-lived publisher connection instead of opening and
    closing a new connection for every message.
    """
    ok = _publisher.publish(pickle.dumps(item), queue_name=queue_name, persistent=True)
    if ok:
        logger.info(f"Item {getattr(item, 'filename', item)} forwarded to {queue_name}.")
    else:
        logger.error(f"Failed to forward item {getattr(item, 'filename', item)} to RabbitMQ queue {queue_name}.")
    return ok


def publish_to_exchange(exchange: str, body: bytes, exchange_type: str = "fanout", persistent: bool = False) -> bool:
    """Publish ``body`` to a (declared) exchange on the shared connection."""
    return _publisher.publish(
        body,
        exchange=exchange,
        routing_key="",
        persistent=persistent,
        declare_queue=False,
        exchange_type=exchange_type,
    )


def consume(queue_names, on_message_callback, prefetch_count: int = 1, auto_ack: bool = False, heartbeat: int = DEFAULT_HEARTBEAT):
    """Start a resilient consumer loop on a dedicated connection.

    A dedicated client (separate from the shared publisher) is used so that
    long running message callbacks do not interfere with publishing.
    """
    client = RabbitMQClient(heartbeat=heartbeat, name="consumer")
    client.consume(queue_names, on_message_callback, prefetch_count=prefetch_count, auto_ack=auto_ack)


def connect_rabbitmq(queue_names: list = None, heartbeat: int = DEFAULT_HEARTBEAT):
    """Backwards compatible helper returning a ``(connection, channel)`` tuple.

    New code should prefer :class:`RabbitMQClient`, :func:`publish` or
    :func:`consume`. This helper is retained for callers that need direct
    access to a pika connection/channel (e.g. exclusive fanout queues).
    """
    for _ in range(CONNECTION_ATTEMPTS):
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=RABBITMQ_HOST, heartbeat=heartbeat)
            )
            channel = connection.channel()
            if queue_names:
                for queue_name in queue_names:
                    channel.queue_declare(queue=queue_name, durable=True)
            channel.basic_qos(prefetch_count=1)
            return connection, channel
        except (socket.gaierror, pika.exceptions.AMQPConnectionError):
            time.sleep(CONNECTION_RETRY_DELAY)
    logger.critical("Couldn't connect to RabbitMQ.")
    return None
