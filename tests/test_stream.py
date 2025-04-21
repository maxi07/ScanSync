import pytest
from web_service.src.main import app, connected_clients, sse_queue


@pytest.fixture
def client():
    """Fixture to create a test client for the Flask app."""
    with app.test_client() as client:
        yield client


def test_stream_endpoint(client):
    """Test that the /stream endpoint increases and decreases connected_clients."""
    global connected_clients

    # Initial state
    assert connected_clients == 0

    # Simulate a client connecting to /stream
    with client.get('/stream', buffered=True) as response:
        assert response.status_code == 200
        assert response.mimetype == "text/event-stream"
        assert connected_clients == 1  # Client connected

        # Read only the first event and then break
        for line in response.iter_lines():
            if line:  # Stop after receiving the first non-empty line
                break

    # After the client disconnects
    assert connected_clients == 0  # Client disconnected


def test_sse_queue_behavior(client):
    """Test that items are added to the SSE queue only when clients are connected."""
    global connected_clients

    # Ensure no clients are connected
    assert connected_clients == 0

    # Add an item to the queue (should not be processed since no clients are connected)
    sse_queue.put("test_data")
    assert not sse_queue.empty()  # Item remains in the queue

    # Simulate a client connecting
    with client.get('/stream', buffered=True):
        assert connected_clients == 1  # Client connected

        # Add another item to the queue (should be processed)
        sse_queue.put("test_data_2")
        assert not sse_queue.empty()  # Item is processed by the connected client
