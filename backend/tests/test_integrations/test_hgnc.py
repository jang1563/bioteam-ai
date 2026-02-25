"""Tests for HGNC API client — uses mocked HTTP responses."""

from unittest.mock import MagicMock, patch

import pytest

from app.integrations.hgnc import HGNCClient


@pytest.fixture
def client():
    return HGNCClient()


class TestHGNCClient:
    """Tests with mocked HTTP responses."""

    def test_validate_approved_symbol(self, client):
        """Approved symbol returns record."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = lambda: None
        mock_response.json.return_value = {
            "response": {
                "docs": [{"symbol": "TP53", "status": "Approved", "hgnc_id": "HGNC:11998"}]
            }
        }

        with patch("httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_client.return_value = mock_instance

            result = client.validate_symbol("TP53")

        assert result is not None
        assert result["symbol"] == "TP53"

    def test_validate_unknown_symbol(self, client):
        """Unknown symbol returns None."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = lambda: None
        mock_response.json.return_value = {"response": {"docs": []}}

        with patch("httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_client.return_value = mock_instance

            result = client.validate_symbol("NOTAREALGENE")

        assert result is None

    def test_is_approved(self, client):
        """is_approved returns True for approved symbols."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = lambda: None
        mock_response.json.return_value = {
            "response": {"docs": [{"symbol": "BRCA1", "status": "Approved"}]}
        }

        with patch("httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_client.return_value = mock_instance

            assert client.is_approved("BRCA1") is True

    def test_get_current_symbol(self, client):
        """Deprecated symbol maps to current approved name."""
        mock_response_prev = MagicMock()
        mock_response_prev.status_code = 200
        mock_response_prev.raise_for_status = lambda: None
        mock_response_prev.json.return_value = {
            "response": {"docs": [{"symbol": "MARCHF1"}]}
        }

        with patch("httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_instance.get.return_value = mock_response_prev
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_client.return_value = mock_instance

            result = client.get_current_symbol("MARCH1")

        assert result == "MARCHF1"

    def test_search_symbol(self, client):
        """Search returns matching gene records."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = lambda: None
        mock_response.json.return_value = {
            "response": {
                "docs": [
                    {"symbol": "TP53", "status": "Approved"},
                    {"symbol": "TP53BP1", "status": "Approved"},
                ]
            }
        }

        with patch("httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_client.return_value = mock_instance

            results = client.search_symbol("TP53")

        assert len(results) == 2
