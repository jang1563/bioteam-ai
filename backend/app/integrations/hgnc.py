"""HGNC REST API client — gene symbol validation.

Validates gene symbols against the HUGO Gene Nomenclature Committee
official nomenclature. Detects deprecated/alias symbols and provides
current approved names.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 10


class HGNCClient:
    """Client for the HGNC REST API (rest.genenames.org)."""

    BASE_URL = "https://rest.genenames.org"

    def __init__(self, timeout: int = _DEFAULT_TIMEOUT) -> None:
        self._timeout = timeout
        self._headers = {
            "Accept": "application/json",
        }

    def validate_symbol(self, symbol: str) -> dict | None:
        """Check if a gene symbol is an approved HGNC symbol.

        Returns the HGNC record dict if found, None otherwise.
        """
        try:
            with httpx.Client(timeout=self._timeout) as client:
                url = f"{self.BASE_URL}/fetch/symbol/{symbol}"
                resp = client.get(url, headers=self._headers)
                resp.raise_for_status()
                data = resp.json()
                docs = data.get("response", {}).get("docs", [])
                return docs[0] if docs else None
        except Exception as e:
            logger.debug("HGNC lookup failed for %s: %s", symbol, e)
            return None

    def search_symbol(self, query: str) -> list[dict]:
        """Search for gene symbols matching a query.

        Searches across symbol, alias_symbol, and prev_symbol fields.
        """
        try:
            with httpx.Client(timeout=self._timeout) as client:
                url = f"{self.BASE_URL}/search/{query}"
                resp = client.get(url, headers=self._headers)
                resp.raise_for_status()
                data = resp.json()
                return data.get("response", {}).get("docs", [])
        except Exception as e:
            logger.debug("HGNC search failed for %s: %s", query, e)
            return []

    def is_approved(self, symbol: str) -> bool:
        """Check if a symbol is a current approved HGNC symbol."""
        result = self.validate_symbol(symbol)
        if result is None:
            return False
        return result.get("status", "").lower() == "approved"

    def get_current_symbol(self, alias_or_prev: str) -> str | None:
        """Given an alias or previous symbol, return the current approved name.

        Searches prev_symbol and alias_symbol fields.
        """
        try:
            with httpx.Client(timeout=self._timeout) as client:
                # Check as previous symbol
                url = f"{self.BASE_URL}/fetch/prev_symbol/{alias_or_prev}"
                resp = client.get(url, headers=self._headers)
                resp.raise_for_status()
                docs = resp.json().get("response", {}).get("docs", [])
                if docs:
                    return docs[0].get("symbol")

                # Check as alias symbol
                url = f"{self.BASE_URL}/fetch/alias_symbol/{alias_or_prev}"
                resp = client.get(url, headers=self._headers)
                resp.raise_for_status()
                docs = resp.json().get("response", {}).get("docs", [])
                if docs:
                    return docs[0].get("symbol")

        except Exception as e:
            logger.debug("HGNC current symbol lookup failed for %s: %s", alias_or_prev, e)

        return None
