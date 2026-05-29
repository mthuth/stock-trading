#!/usr/bin/env python3
"""Shared resilient HTTP helpers for market-data providers."""

from __future__ import annotations

import json
import re
import socket
import time
from dataclasses import dataclass
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TRANSIENT_HTTP_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


@dataclass
class ProviderFetchResult:
    status: str
    payload: object
    message: str
    attempts: int
    error_class: str


def sanitize_provider_message(message: object) -> str:
    text = str(message or "")
    text = re.sub(r"API key as [A-Z0-9]+", "API key as [redacted]", text, flags=re.IGNORECASE)
    text = re.sub(r"apikey[=/][A-Za-z0-9]+", "apikey=[redacted]", text, flags=re.IGNORECASE)
    text = re.sub(r"token[=/][A-Za-z0-9._-]+", "token=[redacted]", text, flags=re.IGNORECASE)
    return text[:300]


def classify_exception(exc: BaseException) -> tuple[str, str, bool]:
    if isinstance(exc, HTTPError):
        if exc.code in TRANSIENT_HTTP_CODES:
            return "http_transient", "error", True
        return "http_blocked", "blocked", False
    if isinstance(exc, (URLError, TimeoutError, socket.timeout)):
        return "network_transient", "error", True
    if isinstance(exc, json.JSONDecodeError):
        return "json_decode", "error", False
    return exc.__class__.__name__, "error", False


def json_provider_message(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    message = str(
        payload.get("Error Message")
        or payload.get("Information")
        or payload.get("Note")
        or payload.get("error")
        or ""
    )
    return sanitize_provider_message(message)


def fetch_json_url(
    url: str,
    headers: Mapping[str, str] | None = None,
    timeout: int = 30,
    retries: int = 2,
    backoff_seconds: float = 0.25,
) -> ProviderFetchResult:
    request_headers = {"Accept": "application/json", **dict(headers or {})}
    attempts = 0
    last_result = ProviderFetchResult("error", {}, "No request attempted", 0, "not_attempted")

    for attempt in range(retries + 1):
        attempts = attempt + 1
        request = Request(url, headers=request_headers)
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode())
            provider_message = json_provider_message(payload)
            if provider_message:
                return ProviderFetchResult(
                    "blocked",
                    payload,
                    provider_message,
                    attempts,
                    "provider_message",
                )
            return ProviderFetchResult("ok", payload, "", attempts, "")
        except HTTPError as exc:
            body = exc.read().decode(errors="replace")[:300]
            error_class, status, retryable = classify_exception(exc)
            message = sanitize_provider_message(f"HTTP {exc.code}: {body}")
        except Exception as exc:  # noqa: BLE001 - provider errors are captured as run status.
            error_class, status, retryable = classify_exception(exc)
            message = sanitize_provider_message(exc)

        last_result = ProviderFetchResult(status, {}, message, attempts, error_class)
        if not retryable or attempt >= retries:
            break
        time.sleep(backoff_seconds * (2**attempt))

    return last_result

