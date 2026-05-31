#!/usr/bin/env python3
"""Controlled provider-gap status normalization."""

from __future__ import annotations

import re


OK = "ok"
EXPECTED = "expected"
INFORMATIONAL = "informational"
NON_OPERATING_COMPANY = "non_operating_company"
MISSING = "missing"
STALE = "stale"
BLOCKED = "blocked"
RATE_LIMITED = "rate_limited"
PARSER_GAP = "parser_gap"
NOT_IMPLEMENTED = "not_implemented"
ERROR = "error"

PROVIDER_STATUSES = {
    OK,
    EXPECTED,
    INFORMATIONAL,
    NON_OPERATING_COMPANY,
    MISSING,
    STALE,
    BLOCKED,
    RATE_LIMITED,
    PARSER_GAP,
    NOT_IMPLEMENTED,
    ERROR,
}

SUCCESS_ALIASES = {"success", "passed", "healthy", "implemented"}
EXPECTED_ALIASES = {"not_applicable", "not applicable", "non-operating-company", "non operating company"}

STATUS_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        RATE_LIMITED,
        (
            r"\b429\b",
            r"\bquota\b",
            r"rate[-_ ]?limit",
            r"rate_limited",
            r"too many requests",
            r"call frequency",
            r"throttl",
        ),
    ),
    (
        BLOCKED,
        (
            r"\b401\b",
            r"\b403\b",
            r"\bauth(?:orization|entication)?\b",
            r"unauthori[sz]ed",
            r"forbidden",
            r"credential",
            r"invalid api[-_ ]?key",
            r"api[-_ ]?key",
            r"access denied",
            r"blocked",
        ),
    ),
    (
        NOT_IMPLEMENTED,
        (
            r"not implemented",
            r"not configured",
            r"not built",
            r"not run",
            r"no implementation",
            r"implementation pending",
        ),
    ),
    (
        PARSER_GAP,
        (
            r"parse failure",
            r"parser",
            r"parseable",
            r"no parseable items",
            r"could not parse",
            r"failed to parse",
            r"json decode",
            r"malformed",
        ),
    ),
    (
        STALE,
        (
            r"\bstale\b",
            r"old timestamp",
            r"too old",
            r"out of date",
            r"outdated",
            r"expired",
        ),
    ),
    (
        MISSING,
        (
            r"no data",
            r"\b404\b",
            r"not found",
            r"missing field",
            r"\bmissing\b",
            r"empty response",
            r"no records",
            r"no rows",
            r"no target",
            r"no price",
        ),
    ),
)


def normalize_provider_status(status: object = "", message: object = "") -> str:
    """Map provider status/message text onto the controlled vocabulary."""
    value = str(status or "").strip().lower().replace("-", "_").replace(" ", "_")
    detail = str(message or "").strip().lower()
    haystack = f"{value} {detail}".strip()

    if value in PROVIDER_STATUSES:
        if detail:
            for normalized, patterns in STATUS_PATTERNS:
                if any(re.search(pattern, detail) for pattern in patterns):
                    return normalized
        return value
    if value in SUCCESS_ALIASES:
        return OK
    if value in EXPECTED_ALIASES:
        return EXPECTED

    for normalized, patterns in STATUS_PATTERNS:
        if any(re.search(pattern, haystack) for pattern in patterns):
            return normalized
    return ERROR


def is_provider_gap(status: object, message: object = "") -> bool:
    return normalize_provider_status(status, message) != OK
