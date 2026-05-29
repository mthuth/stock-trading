#!/usr/bin/env python3
"""Regression tests for shared provider retry and classification behavior."""

from __future__ import annotations

import unittest
from unittest.mock import patch
from urllib.error import URLError


from stock_trading import provider_client as subject


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
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

    def test_fetch_json_classifies_provider_message_as_blocked(self) -> None:
        with patch.object(
            subject,
            "urlopen",
            return_value=FakeResponse(b'{"Note": "rate limit reached for apikey=secret"}'),
        ):
            result = subject.fetch_json_url("https://example.test/provider", retries=0)

        self.assertEqual(result.status, "blocked")
        self.assertIn("apikey=[redacted]", result.message)
        self.assertEqual(result.error_class, "provider_message")


if __name__ == "__main__":
    unittest.main()
