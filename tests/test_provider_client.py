#!/usr/bin/env python3
"""Regression tests for shared provider retry and classification behavior."""

from __future__ import annotations

from io import BytesIO
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError


from stock_trading import provider_client as subject


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, *_args: object) -> bytes:
        return self.payload


class ProviderClientTests(unittest.TestCase):
    def test_fetch_json_retries_transient_network_error(self) -> None:
        with patch.object(
            subject,
            "urlopen",
            side_effect=[URLError("temporary DNS failure"), FakeResponse(b'{"ok": true}')],
        ):
            result = subject.fetch_json_url("https://example.test/provider", retries=2, backoff_seconds=0)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.payload, {"ok": True})
        self.assertEqual(result.attempts, 2)

    def test_fetch_json_classifies_provider_rate_limit_message(self) -> None:
        with patch.object(
            subject,
            "urlopen",
            return_value=FakeResponse(b'{"Note": "rate limit reached for apikey=secret"}'),
        ):
            result = subject.fetch_json_url("https://example.test/provider", retries=0)

        self.assertEqual(result.status, "rate_limited")
        self.assertIn("apikey=[redacted]", result.message)
        self.assertEqual(result.error_class, "provider_message")

    def test_fetch_json_normalizes_http_blocked_and_missing(self) -> None:
        blocked_error = HTTPError("https://example.test/provider", 403, "Forbidden", {}, BytesIO(b"forbidden"))
        missing_error = HTTPError("https://example.test/provider", 404, "Not Found", {}, BytesIO(b"not found"))

        with patch.object(subject, "urlopen", side_effect=blocked_error):
            blocked = subject.fetch_json_url("https://example.test/provider", retries=0)
        with patch.object(subject, "urlopen", side_effect=missing_error):
            missing = subject.fetch_json_url("https://example.test/provider", retries=0)

        self.assertEqual(blocked.status, "blocked")
        self.assertEqual(missing.status, "missing")

    def test_fetch_json_normalizes_parse_failure(self) -> None:
        with patch.object(subject, "urlopen", return_value=FakeResponse(b"not json")):
            result = subject.fetch_json_url("https://example.test/provider", retries=0)

        self.assertEqual(result.status, "parser_gap")
        self.assertEqual(result.error_class, "json_decode")

    def test_fetch_text_normalizes_http_rate_limit(self) -> None:
        rate_limited_error = HTTPError("https://example.test/provider", 429, "Too Many Requests", {}, BytesIO(b"too many requests"))
        with patch.object(subject, "urlopen", side_effect=rate_limited_error):
            result = subject.fetch_text_url("https://example.test/provider", retries=0)

        self.assertEqual(result.status, "rate_limited")


if __name__ == "__main__":
    unittest.main()
