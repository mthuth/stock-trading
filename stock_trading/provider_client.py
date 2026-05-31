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

from stock_trading.provider_gap_status import normalize_provider_status


TRANSIENT_HTTP_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


@dataclass
class ProviderFetchResult:
    status: str
    payload: object
    message: str
    attempts: int
    error_class: str


@dataclass
class ProviderTextResult:
    status: str
    text: str
    message: str
    attempts: int
    error_class: str
    content_type: str = ""


def sanitize_provider_message(message: object) -> str:
    text = str(message or "")
    text = re.sub(r"API key as [A-Z0-9]+", "API key as [redacted]", text, flags=re.IGNORECASE)
    text = re.sub(r"apikey[=/][A-Za-z0-9]+", "apikey=[redacted]", text, flags=re.IGNORECASE)
    text = re.sub(r"token[=/][A-Za-z0-9._-]+", "token=[redacted]", text, flags=re.IGNORECASE)
    return text[:300]


def classify_exception(exc: BaseException) -> tuple[str, str, bool]:
    if isinstance(exc, HTTPError):
        status = normalize_provider_status("error", f"HTTP {exc.code}")
        if exc.code in TRANSIENT_HTTP_CODES:
            return "http_transient", status, True
        return "http_blocked", status, False
    if isinstance(exc, (URLError, TimeoutError, socket.timeout)):
        return "network_transient", "error", True
    if isinstance(exc, json.JSONDecodeError):
        return "json_decode", normalize_provider_status("error", "json decode"), False
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
                status = normalize_provider_status("error", provider_message)
                return ProviderFetchResult(
                    status,
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


def fetch_text_url(
    url: str,
    headers: Mapping[str, str] | None = None,
    timeout: int = 30,
    retries: int = 2,
    backoff_seconds: float = 0.25,
    max_bytes: int | None = None,
) -> ProviderTextResult:
    request_headers = {"Accept": "*/*", **dict(headers or {})}
    last_result = ProviderTextResult("error", "", "No request attempted", 0, "not_attempted")
    for attempt in range(retries + 1):
        attempts = attempt + 1
        request = Request(url, headers=request_headers)
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read(max_bytes) if max_bytes else response.read()
                content_type = response.headers.get("Content-Type", "")
                status_code = getattr(response, "status", 200)
            if status_code >= 400:
                status = normalize_provider_status("error", f"HTTP {status_code}")
                return ProviderTextResult(status, "", f"HTTP {status_code}", attempts, "http_status", content_type)
            return ProviderTextResult(
                "ok",
                raw.decode("utf-8", errors="replace"),
                "",
                attempts,
                "",
                content_type,
            )
        except HTTPError as exc:
            body = exc.read().decode(errors="replace")[:300]
            error_class, status, retryable = classify_exception(exc)
            message = sanitize_provider_message(f"HTTP {exc.code}: {body}")
            content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
        except Exception as exc:  # noqa: BLE001 - provider errors are captured as run status.
            error_class, status, retryable = classify_exception(exc)
            message = sanitize_provider_message(exc)
            content_type = ""
        last_result = ProviderTextResult(status, "", message, attempts, error_class, content_type)
        if not retryable or attempt >= retries:
            break
        time.sleep(backoff_seconds * (2**attempt))
    return last_result
