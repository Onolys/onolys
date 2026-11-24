"""Signed browser PUT contract: write once; no live credentials or GCS requests."""
from datetime import timedelta
from unittest.mock import Mock, patch

from onolys_eval_backend.storage import GCSBucket, InMemoryBucket


def test_gcs_signs_and_returns_write_once_headers():
    credentials = Mock(service_account_email='runtime@example.iam.gserviceaccount.com', token='local-token')
    bucket = Mock()
    bucket.blob.return_value.generate_signed_url.return_value = 'https://storage.googleapis.com/b/o?signed'
    with patch('google.auth.default', return_value=(credentials, 'project')):
        result = GCSBucket(bucket).signed_upload_url(
            'uploads/id/input.wav', 'audio/wav', expires_s=900, max_bytes=314572800,
        )
    headers = {'x-goog-content-length-range': '1,314572800', 'x-goog-if-generation-match': '0'}
    bucket.blob.assert_called_once_with('uploads/id/input.wav')
    bucket.blob.return_value.generate_signed_url.assert_called_once_with(
        version='v4', method='PUT', expiration=timedelta(seconds=900), content_type='audio/wav',
        headers=headers, service_account_email=credentials.service_account_email,
        access_token=credentials.token,
    )
    credentials.refresh.assert_called_once()
    assert result == {
        'url': 'https://storage.googleapis.com/b/o?signed', 'method': 'PUT',
        'headers': {'Content-Type': 'audio/wav', **headers},
    }


def test_memory_signed_upload_matches_production_headers():
    result = InMemoryBucket().signed_upload_url('uploads/id/input.wav', 'audio/wav', expires_s=900, max_bytes=50)
    assert result['headers'] == {
        'Content-Type': 'audio/wav', 'x-goog-content-length-range': '1,50',
        'x-goog-if-generation-match': '0',
    }
