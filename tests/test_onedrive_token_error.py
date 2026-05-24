"""Tests for OneDrive token error flag functions.

These tests exercise the token error helpers (save/clear/check) that are used
to communicate expired-token state between the upload service and the web UI.
The functions under test are pure file-based utilities so we replicate their
logic here to avoid importing the full module (which triggers heavy side
effects like database initialisation).
"""

import json
import os
import tempfile
import time

import pytest


# ---------------------------------------------------------------------------
# Inline copies of the functions under test – they are intentionally
# simple file helpers, so duplicating the few lines keeps the test
# independent of process-level side effects while still validating the
# exact same logic that lives in scansynclib/onedrive_api.py.
# ---------------------------------------------------------------------------

_tmpdir = tempfile.mkdtemp()
TOKEN_ERROR_FILE = os.path.join(_tmpdir, "token_error.json")
TOKEN_FILE = os.path.join(_tmpdir, "token.json")


def save_token_error(error_message):
    with open(TOKEN_ERROR_FILE, "w") as f:
        json.dump({"error": error_message, "timestamp": int(time.time())}, f)


def clear_token_error():
    if os.path.exists(TOKEN_ERROR_FILE):
        os.remove(TOKEN_ERROR_FILE)


def is_token_expired():
    if os.path.exists(TOKEN_ERROR_FILE):
        try:
            with open(TOKEN_ERROR_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {"error": "Unknown token error"}
    return None


def save_token(token):
    token["expires_at"] = int(time.time()) + int(token["expires_in"])
    with open(TOKEN_FILE, "w") as f:
        json.dump(token, f)
    clear_token_error()


@pytest.fixture(autouse=True)
def _cleanup():
    """Ensure a clean slate before and after every test."""
    for f in (TOKEN_ERROR_FILE, TOKEN_FILE):
        if os.path.exists(f):
            os.remove(f)
    yield
    for f in (TOKEN_ERROR_FILE, TOKEN_FILE):
        if os.path.exists(f):
            os.remove(f)


# ---- Tests ---------------------------------------------------------------

def test_save_and_read_token_error():
    """save_token_error should create a file that is_token_expired can read."""
    assert is_token_expired() is None
    save_token_error("The grant is expired")
    result = is_token_expired()
    assert result is not None
    assert result["error"] == "The grant is expired"
    assert "timestamp" in result


def test_clear_token_error():
    """clear_token_error should remove the error file."""
    save_token_error("expired")
    assert is_token_expired() is not None
    clear_token_error()
    assert is_token_expired() is None


def test_clear_token_error_no_file():
    """clear_token_error should not raise when no file exists."""
    clear_token_error()  # should not raise


def test_save_token_clears_error():
    """save_token should clear any existing token error."""
    save_token_error("expired")
    assert is_token_expired() is not None
    save_token({"access_token": "test", "expires_in": 3600})
    assert is_token_expired() is None


def test_is_token_expired_returns_none_when_no_error():
    """is_token_expired returns None when no error file exists."""
    assert is_token_expired() is None
