
from unittest.mock import patch
from requests import Response
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.apis.image_library_client import create_retry_session


def test_retry_configuration():
    """Verify that the retry session has the expected settings."""

    with create_retry_session() as session:
        adapter = session.get_adapter("https://")
        retry = adapter.max_retries

        assert isinstance(adapter, HTTPAdapter)
        assert isinstance(retry, Retry)
        assert retry.total == 3
        assert 503 in retry.status_forcelist
        assert "GET" in retry.allowed_methods
