"""Tests for the enhanced /api/status endpoint."""

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


class TestStatusAPI:
    """Test cases for the enhanced /api/status endpoint."""

    def test_status_returns_backward_compatible_fields(self, client):
        """Test that all original response fields are still present."""
        summary_result = {
            'processed_pdfs': 10,
            'processing_pdfs': 2,
            'latest_processing_timestamp': '2024-06-01 12:00:00',
            'latest_completed_timestamp': '2024-06-01 11:30:00',
            'latest_created_name': 'invoice.pdf',
            'latest_created_status': 2,
            'total_pdfs': 15,
            'failed_pdfs': 3,
            'avg_processing_seconds': 45.678,
        }

        with patch('routes.api.execute_query') as mock_query:
            mock_query.side_effect = [
                summary_result,   # summary query
                [],               # currently_processing query
                [],               # recent_files query
            ]
            response = client.get('/api/status')
            data = json.loads(response.data)

        assert response.status_code == 200
        assert data['processed_pdfs'] == 10
        assert data['processing_pdfs'] == 2
        assert data['latest_processing_timestamp'] == '2024-06-01 12:00:00'
        assert data['latest_completed_timestamp'] == '2024-06-01 11:30:00'
        assert data['latest_created_name'] == 'invoice.pdf'
        assert data['latest_created_status'] == 2

    def test_status_returns_new_fields(self, client):
        """Test that all new response fields are present."""
        summary_result = {
            'processed_pdfs': 10,
            'processing_pdfs': 2,
            'latest_processing_timestamp': '2024-06-01 12:00:00',
            'latest_completed_timestamp': '2024-06-01 11:30:00',
            'latest_created_name': 'invoice.pdf',
            'latest_created_status': 2,
            'total_pdfs': 15,
            'failed_pdfs': 3,
            'avg_processing_seconds': 45.678,
        }

        currently_processing = [
            {'id': 12, 'file_name': 'scan1.pdf', 'status': 'OCR Processing', 'status_code': 2, 'created': '2024-06-01 12:00:00', 'pdf_pages': 3},
            {'id': 13, 'file_name': 'scan2.pdf', 'status': 'Syncing', 'status_code': 4, 'created': '2024-06-01 11:55:00', 'pdf_pages': 1},
        ]

        recent_files = [
            {'id': 11, 'file_name': 'doc1.pdf', 'status': 'Completed', 'status_code': 5, 'created': '2024-06-01 10:00:00', 'completed': '2024-06-01 10:01:00', 'pdf_pages': 2},
            {'id': 10, 'file_name': 'doc2.pdf', 'status': 'Failed', 'status_code': -1, 'created': '2024-06-01 09:00:00', 'completed': '2024-06-01 09:00:30', 'pdf_pages': 0},
        ]

        with patch('routes.api.execute_query') as mock_query:
            mock_query.side_effect = [
                summary_result,
                currently_processing,
                recent_files,
            ]
            response = client.get('/api/status')
            data = json.loads(response.data)

        assert response.status_code == 200
        # New fields
        assert data['total_pdfs'] == 15
        assert data['failed_pdfs'] == 3
        assert data['avg_processing_seconds'] == 45.68  # rounded to 2 decimal places
        assert len(data['processing_details']) == 2
        assert data['processing_details'][0]['status'] == 'OCR Processing'
        assert data['processing_details'][0]['count'] == 1
        assert len(data['currently_processing']) == 2
        assert data['currently_processing'][0]['file_name'] == 'scan1.pdf'
        assert len(data['recent_files']) == 2
        assert data['recent_files'][0]['file_name'] == 'doc1.pdf'
        assert data['recent_files'][1]['status'] == 'Failed'

    def test_status_no_data_returns_404(self, client):
        """Test that 404 is returned when no data exists."""
        with patch('routes.api.execute_query') as mock_query:
            mock_query.return_value = None
            response = client.get('/api/status')

        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'error' in data

    def test_status_empty_processing(self, client):
        """Test response when no documents are currently processing."""
        summary_result = {
            'processed_pdfs': 5,
            'processing_pdfs': 0,
            'latest_processing_timestamp': None,
            'latest_completed_timestamp': '2024-06-01 11:30:00',
            'latest_created_name': 'doc.pdf',
            'latest_created_status': 5,
            'total_pdfs': 5,
            'failed_pdfs': 0,
            'avg_processing_seconds': 30.0,
        }

        with patch('routes.api.execute_query') as mock_query:
            mock_query.side_effect = [
                summary_result,
                [],  # no currently processing
                [{'id': 1, 'file_name': 'a.pdf', 'status': 'Completed', 'status_code': 5, 'created': '2024-06-01 10:00:00', 'completed': '2024-06-01 10:00:30', 'pdf_pages': 1}],
            ]
            response = client.get('/api/status')
            data = json.loads(response.data)

        assert response.status_code == 200
        assert data['processing_pdfs'] == 0
        assert data['processing_details'] == []
        assert data['currently_processing'] == []
        assert len(data['recent_files']) == 1

    def test_status_null_avg_processing(self, client):
        """Test response when avg_processing_seconds is None (no completed docs)."""
        summary_result = {
            'processed_pdfs': 0,
            'processing_pdfs': 1,
            'latest_processing_timestamp': '2024-06-01 12:00:00',
            'latest_completed_timestamp': None,
            'latest_created_name': 'new.pdf',
            'latest_created_status': 1,
            'total_pdfs': 1,
            'failed_pdfs': 0,
            'avg_processing_seconds': None,
        }

        with patch('routes.api.execute_query') as mock_query:
            mock_query.side_effect = [
                summary_result,
                [{'id': 1, 'file_name': 'new.pdf', 'status': 'Reading Metadata', 'status_code': 1, 'created': '2024-06-01 12:00:00', 'pdf_pages': 0}],
                [],
            ]
            response = client.get('/api/status')
            data = json.loads(response.data)

        assert response.status_code == 200
        assert data['avg_processing_seconds'] is None
        assert data['processed_pdfs'] == 0
        assert len(data['currently_processing']) == 1

    def test_status_database_error(self, client):
        """Test that database errors return 500."""
        with patch('routes.api.execute_query') as mock_query:
            mock_query.side_effect = Exception("Database connection failed")
            response = client.get('/api/status')

        assert response.status_code == 500
        data = json.loads(response.data)
        assert 'error' in data

    def test_status_recent_files_limit(self, client):
        """Test that recent_files returns at most 5 entries."""
        summary_result = {
            'processed_pdfs': 10,
            'processing_pdfs': 0,
            'latest_processing_timestamp': None,
            'latest_completed_timestamp': '2024-06-01 12:00:00',
            'latest_created_name': 'doc10.pdf',
            'latest_created_status': 5,
            'total_pdfs': 10,
            'failed_pdfs': 0,
            'avg_processing_seconds': 25.0,
        }

        # Simulate query returning exactly 5 recent files
        recent = [
            {'id': i, 'file_name': f'doc{i}.pdf', 'status': 'Completed', 'status_code': 5,
             'created': f'2024-06-01 {10+i}:00:00', 'completed': f'2024-06-01 {10+i}:01:00', 'pdf_pages': i}
            for i in range(5)
        ]

        with patch('routes.api.execute_query') as mock_query:
            mock_query.side_effect = [
                summary_result,
                [],
                recent,
            ]
            response = client.get('/api/status')
            data = json.loads(response.data)

        assert response.status_code == 200
        assert len(data['recent_files']) == 5

    def test_status_processing_details_structure(self, client):
        """Test the structure of processing_details entries."""
        summary_result = {
            'processed_pdfs': 5,
            'processing_pdfs': 3,
            'latest_processing_timestamp': '2024-06-01 12:00:00',
            'latest_completed_timestamp': '2024-06-01 11:00:00',
            'latest_created_name': 'test.pdf',
            'latest_created_status': 2,
            'total_pdfs': 8,
            'failed_pdfs': 0,
            'avg_processing_seconds': 40.0,
        }

        currently_processing = [
            {'id': 1, 'file_name': 'a.pdf', 'status': 'Reading Metadata', 'status_code': 1, 'created': '2024-06-01 12:00:00', 'pdf_pages': 1},
            {'id': 2, 'file_name': 'b.pdf', 'status': 'OCR Processing', 'status_code': 2, 'created': '2024-06-01 11:59:00', 'pdf_pages': 2},
            {'id': 3, 'file_name': 'c.pdf', 'status': 'OCR Processing', 'status_code': 2, 'created': '2024-06-01 11:58:00', 'pdf_pages': 3},
        ]

        with patch('routes.api.execute_query') as mock_query:
            mock_query.side_effect = [
                summary_result,
                currently_processing,
                [],
            ]
            response = client.get('/api/status')
            data = json.loads(response.data)

        assert response.status_code == 200
        for detail in data['processing_details']:
            assert 'status' in detail
            assert 'status_code' in detail
            assert 'count' in detail

    def test_status_includes_failed_in_recent(self, client):
        """Test that failed documents appear in recent_files."""
        summary_result = {
            'processed_pdfs': 3,
            'processing_pdfs': 0,
            'latest_processing_timestamp': None,
            'latest_completed_timestamp': '2024-06-01 12:00:00',
            'latest_created_name': 'failed.pdf',
            'latest_created_status': -1,
            'total_pdfs': 5,
            'failed_pdfs': 2,
            'avg_processing_seconds': 30.0,
        }

        recent_files = [
            {'id': 5, 'file_name': 'ok.pdf', 'status': 'Completed', 'status_code': 5,
             'created': '2024-06-01 12:00:00', 'completed': '2024-06-01 12:01:00', 'pdf_pages': 2},
            {'id': 4, 'file_name': 'failed.pdf', 'status': 'Failed', 'status_code': -1,
             'created': '2024-06-01 11:00:00', 'completed': '2024-06-01 11:00:05', 'pdf_pages': 0},
            {'id': 3, 'file_name': 'invalid.pdf', 'status': 'Invalid File', 'status_code': -1,
             'created': '2024-06-01 10:00:00', 'completed': '2024-06-01 10:00:01', 'pdf_pages': 0},
        ]

        with patch('routes.api.execute_query') as mock_query:
            mock_query.side_effect = [
                summary_result,
                [],
                recent_files,
            ]
            response = client.get('/api/status')
            data = json.loads(response.data)

        assert response.status_code == 200
        assert data['failed_pdfs'] == 2
        statuses = [f['status'] for f in data['recent_files']]
        assert 'Failed' in statuses
        assert 'Invalid File' in statuses

    def test_status_execute_query_returns_none_for_lists(self, client):
        """Test that None results from list queries are handled gracefully."""
        summary_result = {
            'processed_pdfs': 1,
            'processing_pdfs': 0,
            'latest_processing_timestamp': None,
            'latest_completed_timestamp': '2024-06-01 12:00:00',
            'latest_created_name': 'doc.pdf',
            'latest_created_status': 5,
            'total_pdfs': 1,
            'failed_pdfs': 0,
            'avg_processing_seconds': 10.0,
        }

        with patch('routes.api.execute_query') as mock_query:
            mock_query.side_effect = [
                summary_result,
                None,  # currently_processing returns None
                None,  # recent_files returns None
            ]
            response = client.get('/api/status')
            data = json.loads(response.data)

        assert response.status_code == 200
        assert data['processing_details'] == []
        assert data['currently_processing'] == []
        assert data['recent_files'] == []
