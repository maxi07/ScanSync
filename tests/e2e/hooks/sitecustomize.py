"""Route Microsoft HTTP traffic to the isolated E2E API simulator."""

import os
from urllib.parse import urlsplit, urlunsplit

if os.environ.get('SCANSYNC_SERVICE') == 'web_service':
    from gevent import monkey
    monkey.patch_all()

import requests


_send = requests.Session.send
_origins = {
    "graph.microsoft.com": "graph",
    "login.microsoftonline.com": "identity",
}


def _send_local(self, request, **kwargs):
    parsed = urlsplit(request.url)
    if parsed.hostname in _origins:
        origin = urlsplit(os.environ["E2E_API_URL"])
        request.url = urlunsplit((
            origin.scheme,
            origin.netloc,
            f"/{_origins[parsed.hostname]}{parsed.path}",
            parsed.query,
            "",
        ))
        kwargs["proxies"] = {}
    elif parsed.scheme == "https":
        raise requests.ConnectionError(f"External HTTPS is disabled in E2E: {parsed.hostname}")
    return _send(self, request, **kwargs)


requests.Session.send = _send_local
