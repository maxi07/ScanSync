import queue

import pytest

from web_service.src.sse import SSEBroker


def test_each_client_receives_each_update():
    broker = SSEBroker()
    first = broker.subscribe()
    second = broker.subscribe()

    broker.publish('completed')

    assert first.get_nowait() == second.get_nowait() == 'completed'
    assert len(broker) == 2


def test_slow_client_is_bounded_and_reset_without_blocking_healthy_client():
    broker = SSEBroker(max_pending=2)
    slow = broker.subscribe()
    healthy = broker.subscribe()

    for update in range(10):
        broker.publish(str(update))
        assert healthy.get_nowait() == str(update)
        assert slow.qsize() <= 2

    assert len(broker) == 1
    assert slow.get_nowait() is None
    with pytest.raises(queue.Empty):
        slow.get_nowait()


def test_disconnected_client_is_no_longer_retained():
    broker = SSEBroker(max_pending=1)
    client = broker.subscribe()
    broker.unsubscribe(client)
    broker.unsubscribe(client)

    broker.publish('update')

    assert len(broker) == 0
    assert client.empty()


def test_reset_client_can_subscribe_again():
    broker = SSEBroker(max_pending=1)
    old = broker.subscribe()
    broker.publish('one')
    broker.publish('two')
    assert old.get_nowait() is None

    new = broker.subscribe()
    broker.publish('completed')

    assert new.get_nowait() == 'completed'
    assert len(broker) == 1
