"""Bounded fanout for dashboard status updates."""

import queue


class SSEBroker:
    def __init__(self, max_pending=100):
        self.max_pending = max_pending
        self.clients = set()

    def __len__(self):
        return len(self.clients)

    def subscribe(self):
        client = queue.Queue(maxsize=self.max_pending)
        self.clients.add(client)
        return client

    def unsubscribe(self, client):
        self.clients.discard(client)

    def publish(self, data):
        for client in tuple(self.clients):
            try:
                client.put_nowait(data)
            except queue.Full:
                self.unsubscribe(client)
                while True:
                    try:
                        client.get_nowait()
                    except queue.Empty:
                        break
                client.put_nowait(None)
