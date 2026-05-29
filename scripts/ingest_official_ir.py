#!/usr/bin/env python3
"""Ingest official company investor-relations page snapshots."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import socket
import sys
import time
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from engine_common import (  # noqa: E402
    load_env,
    read_csv,
    record_provider_payload,
    record_provider_run,
    record_research_evidence,
)


IR_SOURCES_FILE = ROOT / "config" / "official_ir_sources.csv"
REQUEST_TIMEOUT_SECONDS = 25
MAX_RESPONSE_BYTES = 600_000
DEFAULT_USER_AGENT = "StockTradingResearch/0.1 mthuth@gmail.com"
LINK_KEYWORDS = (
    "earnings",
    "results",
    "quarter",
    "annual",
    "financial",
    "release",
    "presentation",
    "transcript",
    "event",
    "guidance",
)


class InvestorPageParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.title = ""
        self.meta_description = ""
        self.headings: list[str] = []
        self.links: list[dict[str, str]] = []
        self._capture_tag = ""
        self._text_parts: list[str] = []
        self._current_link: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        tag_lower = tag.lower()
        if tag_lower == "title":
            self._capture_tag = "title"
            self._text_parts = []
        elif tag_lower in {"h1", "h2", "h3"}:
            self._capture_tag = tag_lower
            self._text_parts = []
        elif tag_lower == "meta":
            name = attrs_dict.get("name", "").lower()
            prop = attrs_dict.get("property", "").lower()
            if name == "description" or prop == "og:description":
                self.meta_description = clean_text(attrs_dict.get("content", ""))[:500]
        elif tag_lower == "a" and attrs_dict.get("href"):
            self._current_link = {
                "href": urljoin(self.base_url, attrs_dict["href"]),
                "text": "",
            }
            self._capture_tag = "a"
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._capture_tag:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if self._capture_tag == tag_lower:
            text = clean_text(" ".join(self._text_parts))
            if tag_lower == "title" and text and not self.title:
                self.title = text[:300]
            elif tag_lower in {"h1", "h2", "h3"} and text:
                if text not in self.headings:
                    self.headings.append(text[:240])
            elif tag_lower == "a" and self._current_link:
                if text:
                    self._current_link["text"] = text[:240]
                    self.links.append(self._current_link)
                self._current_link = None
            self._capture_tag = ""
            self._text_parts = []


def clean_text(value: str) -> str:
    return " ".join(html.unescape(value or "").split())


def load_ir_sources(symbol_filter: set[str] | None) -> list[dict[str, str]]:
    rows, _ = read_csv(IR_SOURCES_FILE)
    sources = []
    for row in rows:
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol or not row.get("ir_url"):
            continue
        if symbol_filter and symbol not in symbol_filter:
            continue
        sources.append(
            {
                "symbol": symbol,
                "company_name": str(row.get("company_name", "")).strip(),
                "ir_url": str(row.get("ir_url", "")).strip(),
                "source_focus": str(row.get("source_focus", "")).strip(),
            }
        )
    return sources


def fetch_page(url: str, user_agent: str) -> tuple[str, bytes, str, str]:
    request = Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": user_agent,
        },
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            content_type = response.headers.get("Content-Type", "")
            body = response.read(MAX_RESPONSE_BYTES)
            status = getattr(response, "status", 200)
            if status >= 400:
                return "blocked", b"", content_type, f"HTTP {status}"
            return "ok", body, content_type, ""
    except HTTPError as exc:
        body = exc.read().decode(errors="replace")[:280]
        status = "blocked" if exc.code in {401, 403, 404, 429} else "error"
        return status, b"", "", f"HTTP {exc.code}: {body}"
    except (URLError, TimeoutError, socket.timeout) as exc:
        return "error", b"", "", str(exc)


def relevant_links(parsed: InvestorPageParser, limit: int) -> list[dict[str, str]]:
    selected = []
    seen = set()
    for link in parsed.links:
        text = clean_text(link.get("text", ""))
        href = link.get("href", "")
        parsed_href = urlparse(href)
        path_tail = "/".join(part for part in parsed_href.path.split("/")[-2:] if part)
        haystack = f"{text} {path_tail} {parsed_href.query}".lower()
        if not text or text.lower().startswith("skip to ") or not href:
            continue
        if not any(keyword in haystack for keyword in LINK_KEYWORDS):
            continue
        key = href.split("#", 1)[0]
        if key in seen:
            continue
        seen.add(key)
        selected.append({"text": text, "href": href})
        if len(selected) >= limit:
            break
    return selected


def page_evidence(
    source: dict[str, str],
    parsed: InvestorPageParser,
    links: list[dict[str, str]],
    payload_hash: str,
) -> list[dict[str, object]]:
    symbol = source["symbol"]
    today = date.today().isoformat()
    heading_summary = "; ".join(parsed.headings[:5])
    summary_parts = [
        f"Official IR page snapshot for {source['company_name'] or symbol}.",
        f"Focus: {source['source_focus'] or 'investor relations'}.",
    ]
    if parsed.meta_description:
        summary_parts.append(f"Page description: {parsed.meta_description}")
    if heading_summary:
        summary_parts.append(f"Visible headings: {heading_summary}")
    if links:
        summary_parts.append(
            "Relevant official links: "
            + "; ".join(f"{item['text']} ({item['href']})" for item in links[:5])
        )
    rows: list[dict[str, object]] = [
        {
            "run_id": None,
            "symbol": symbol,
            "evidence_type": "official_ir_page_snapshot",
            "source_name": "Company investor relations",
            "source_type": "company release",
            "source_url": source["ir_url"],
            "provider_endpoint": "official_ir_page",
            "provider_id": f"{symbol}-{today}-{payload_hash[:12]}",
            "source_timestamp": today,
            "title": parsed.title or f"{symbol} official investor relations page",
            "summary": " ".join(summary_parts)[:1200],
            "raw_text_ref": "",
            "confidence": "high",
            "corroboration_status": "primary_source",
            "user_feedback": "",
        }
    ]
    for link in links:
        link_id = hashlib.sha256(link["href"].encode()).hexdigest()[:16]
        rows.append(
            {
                "run_id": None,
                "symbol": symbol,
                "evidence_type": "official_ir_link",
                "source_name": "Company investor relations",
                "source_type": "company release",
                "source_url": link["href"],
                "provider_endpoint": "official_ir_link_discovery",
                "provider_id": f"{symbol}-{link_id}",
                "source_timestamp": today,
                "title": link["text"],
                "summary": f"Official IR link discovered from {source['ir_url']}. Treat as a primary-source lead for future release/deck/transcript extraction.",
                "raw_text_ref": "",
                "confidence": "high",
                "corroboration_status": "primary_source",
                "user_feedback": "",
            }
        )
    return rows


def ingest_source(source: dict[str, str], user_agent: str, link_limit: int) -> tuple[int, dict[str, object]]:
    status, body, content_type, message = fetch_page(source["ir_url"], user_agent)
    payload_hash = hashlib.sha256(body).hexdigest() if body else ""
    payload_summary: dict[str, object] = {
        "url": source["ir_url"],
        "company_name": source["company_name"],
        "source_focus": source["source_focus"],
        "content_type": content_type,
        "bytes_read": len(body),
        "sha256": payload_hash,
    }
    evidence: list[dict[str, object]] = []
    if status == "ok":
        decoded = body.decode("utf-8", errors="replace")
        parsed = InvestorPageParser(source["ir_url"])
        parsed.feed(decoded)
        links = relevant_links(parsed, link_limit)
        payload_summary.update(
            {
                "title": parsed.title,
                "meta_description": parsed.meta_description,
                "headings": parsed.headings[:12],
                "relevant_links": links,
            }
        )
        evidence = page_evidence(source, parsed, links, payload_hash)
    record_provider_payload(
        "Company investor relations",
        "official_ir_page",
        source["symbol"],
        status,
        message,
        payload_json=payload_summary if status == "ok" else None,
    )
    inserted = record_research_evidence(evidence)
    status_row = {
        "symbol": source["symbol"],
        "provider": "Company investor relations",
        "field_name": "official_ir_page",
        "status": status,
        "message": message,
    }
    return inserted, status_row


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest official company IR page snapshots.")
    parser.add_argument("--symbols", help="Comma-separated symbols. Defaults to configured operating-company IR sources.")
    parser.add_argument("--delay", type=float, default=0.3, help="Delay between company IR requests.")
    parser.add_argument("--link-limit", type=int, default=6, help="Maximum relevant IR links to curate per source.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_env()
    symbol_filter = (
        {symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()}
        if args.symbols
        else None
    )
    sources = load_ir_sources(symbol_filter)
    if not sources:
        print("No official IR sources configured for requested symbols.")
        return 1
    user_agent = DEFAULT_USER_AGENT
    total_inserted = 0
    statuses: list[dict[str, object]] = []
    for index, source in enumerate(sources, start=1):
        inserted, status = ingest_source(source, user_agent, max(0, args.link_limit))
        total_inserted += inserted
        statuses.append(status)
        print(f"{source['symbol']}: official_ir_status={status['status']} inserted={inserted}", flush=True)
        if index < len(sources) and args.delay > 0:
            time.sleep(args.delay)
    gaps = sum(1 for row in statuses if row.get("status") != "ok")
    run_id = record_provider_run(
        "Company investor relations",
        "ok" if statuses else "failed",
        f"sources={len(sources)}; inserted_evidence={total_inserted}; gaps={gaps}",
        statuses,
    )
    print(f"Recorded Company investor relations provider run {run_id} with {gaps} gaps")
    return 0 if statuses else 1


if __name__ == "__main__":
    sys.exit(main())
