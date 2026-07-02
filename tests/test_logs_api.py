"""Tests for the OCR and sync logging API endpoints."""

import json
import pytest
import sys
import os
from unittest.mock import patch, MagicMock

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../scansynclib'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../web_service/src'))

# Ensure the data directory exists for sqlite_wrapper module-level initialization
os.makedirs(os.path.join(os.path.dirname(__file__), '../data'), exist_ok=True)

# Mock Redis before any scansynclib imports, since settings.py connects at module level
import redis as _real_redis
_orig_from_url = _real_redis.Redis.from_url


def _mock_from_url(*args, **kwargs):
    mock_client = MagicMock()
    mock_client.get.return_value = None  # No existing settings in Redis
    mock_client.set.return_value = True
    mock_client.publish.return_value = 0
    mock_pubsub = MagicMock()
    mock_pubsub.subscribe.return_value = None
    mock_pubsub.listen.return_value = iter([])  # Empty iterator
    mock_client.pubsub.return_value = mock_pubsub
    return mock_client


_real_redis.Redis.from_url = _mock_from_url


@pytest.fixture
def app():
    """Create a Flask test app with the api blueprint."""
    from flask import Flask
    from routes.api import api_bp

    app = Flask(__name__)
    app.register_blueprint(api_bp)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Create a Flask test client."""
    return app.test_client()


class TestOcrLogsAPI:
    """Test cases for the /api/ocr-logs endpoint."""

    def test_ocr_logs_returns_paginated_data(self, client):
        logs = [
            {
                'id': 2,
                'scanneddata_id': 5,
                'started': '2024-06-01 12:00:00',
                'finished': '2024-06-01 12:01:00',
                'ocr_status': 'COMPLETED',
                'ocr_error': None,
                'file_name': 'invoice.pdf',
            }
        ]
        with patch('routes.api.execute_query') as mock_query:
            mock_query.side_effect = [1, logs]  # count, logs
            response = client.get('/api/ocr-logs?page=1&per_page=20')
            data = json.loads(response.data)

        assert response.status_code == 200
        assert data['total_count'] == 1
        assert data['total_pages'] == 1
        assert data['page'] == 1
        assert data['logs'][0]['ocr_status'] == 'COMPLETED'

    def test_ocr_logs_success_filter(self, client):
        with patch('routes.api.execute_query') as mock_query:
            mock_query.side_effect = [0, []]
            client.get('/api/ocr-logs?filter=success')

        count_query = mock_query.call_args_list[0].args[0]
        assert "ocr_status = 'COMPLETED'" in count_query

    def test_ocr_logs_failed_filter(self, client):
        with patch('routes.api.execute_query') as mock_query:
            mock_query.side_effect = [0, []]
            client.get('/api/ocr-logs?filter=failed')

        count_query = mock_query.call_args_list[0].args[0]
        assert "NOT IN ('COMPLETED', 'PROCESSING')" in count_query

    def test_ocr_logs_handles_none_count(self, client):
        with patch('routes.api.execute_query') as mock_query:
            mock_query.side_effect = [None, []]
            response = client.get('/api/ocr-logs')
            data = json.loads(response.data)

        assert response.status_code == 200
        assert data['total_count'] == 0
        assert data['total_pages'] == 0

    def test_ocr_logs_database_error_returns_500(self, client):
        with patch('routes.api.execute_query') as mock_query:
            mock_query.side_effect = Exception("boom")
            response = client.get('/api/ocr-logs')

        assert response.status_code == 500


class TestSyncLogsAPI:
    """Test cases for the /api/sync-logs endpoint."""

    def test_sync_logs_returns_paginated_data(self, client):
        logs = [
            {
                'id': 7,
                'scanneddata_id': 9,
                'started': '2024-06-01 12:00:00',
                'finished': '2024-06-01 12:02:00',
                'sync_status': 'COMPLETED',
                'success': 1,
                'error_description': None,
                'file_name': 'doc.pdf',
            }
        ]
        with patch('routes.api.execute_query') as mock_query:
            mock_query.side_effect = [1, logs]
            response = client.get('/api/sync-logs')
            data = json.loads(response.data)

        assert response.status_code == 200
        assert data['total_count'] == 1
        assert data['logs'][0]['sync_status'] == 'COMPLETED'

    def test_sync_logs_success_filter(self, client):
        with patch('routes.api.execute_query') as mock_query:
            mock_query.side_effect = [0, []]
            client.get('/api/sync-logs?filter=success')

        count_query = mock_query.call_args_list[0].args[0]
        assert "sync_jobs.success = 1" in count_query

    def test_sync_logs_failed_filter(self, client):
        with patch('routes.api.execute_query') as mock_query:
            mock_query.side_effect = [0, []]
            client.get('/api/sync-logs?filter=failed')

        count_query = mock_query.call_args_list[0].args[0]
        assert "sync_jobs.success = 0" in count_query

    def test_sync_logs_pagination_math(self, client):
        with patch('routes.api.execute_query') as mock_query:
            mock_query.side_effect = [12, []]
            response = client.get('/api/sync-logs?per_page=5')
            data = json.loads(response.data)

        assert data['total_count'] == 12
        assert data['total_pages'] == 3
