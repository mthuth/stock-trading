#!/usr/bin/env python3
"""Ingest approved public RSS/Atom/archive research sources."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import socket
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
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


INTEGRATIONS_FILE = ROOT / "config" / "research_source_integrations.csv"
REQUEST_TIMEOUT_SECONDS = 18
MAX_FEED_BYTES = 5_000_000
DEFAULT_USER_AGENT = "StockTradingResearch/0.1 mthuth@gmail.com"
INGESTIBLE_CATEGORIES = {"podcast", "newsletter"}
RSS_CONTENT_TYPES = ("rss", "xml", "atom")
RSS_NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
}


class FeedLinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.feed_urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "link":
            return
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        rel = attrs_dict.get("rel", "").lower()
        type_value = attrs_dict.get("type", "").lower()
        href = attrs_dict.get("href", "")
        if href and "alternate" in rel and any(kind in type_value for kind in RSS_CONTENT_TYPES):
            self.feed_urls.append(urljoin(self.base_url, href))


def clean_text(value: object, limit: int = 1200) -> str:
    text = str(value or "")
    text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text, flags=re.DOTALL)
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(html.unescape(text).split())
    return text[:limit]


def fetch_text(url: str, redirects_remaining: int = 3) -> tuple[str, str, str]:
    request = Request(
        url,
        headers={
            "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml,text/html,*/*;q=0.8",
            "User-Agent": DEFAULT_USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            content_type = response.headers.get("Content-Type", "")
            body = response.read(MAX_FEED_BYTES).decode("utf-8", errors="replace")
            status = getattr(response, "status", 200)
            if status >= 400:
                return "blocked", "", f"HTTP {status}"
            return "ok", body, content_type
    except HTTPError as exc:
        if exc.code in {301, 302, 303, 307, 308} and redirects_remaining > 0:
            location = exc.headers.get("Location", "")
            if location:
                return fetch_text(urljoin(url, location), redirects_remaining - 1)
        body = exc.read().decode(errors="replace")[:280]
        status = "blocked" if exc.code in {401, 403, 404, 429} else "error"
        return status, "", f"HTTP {exc.code}: {body}"
    except (URLError, TimeoutError, socket.timeout) as exc:
        return "error", "", str(exc)


def integration_rows(symbol_filter: set[str] | None) -> list[dict[str, str]]:
    rows, _ = read_csv(INTEGRATIONS_FILE)
    selected = []
    for row in rows:
        row.pop(None, None)
        name = str(row.get("source_name", "")).strip()
        category = str(row.get("source_category", "")).strip()
        if category not in INGESTIBLE_CATEGORIES:
            continue
        if symbol_filter and name not in symbol_filter:
            continue
        selected.append(row)
    return selected


def candidate_feed_urls(home_url: str) -> list[str]:
    parsed = urlparse(home_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    candidates = [
        home_url,
        urljoin(base, "/feed"),
        urljoin(base, "/feed/"),
        urljoin(base, "/rss"),
        urljoin(base, "/rss.xml"),
        urljoin(base, "/atom.xml"),
    ]
    if parsed.netloc.endswith("substack.com"):
        candidates.insert(1, urljoin(base, "/feed"))
    return list(dict.fromkeys(candidates))


def discover_feed_url(home_url: str, explicit_feed_url: str = "") -> tuple[str, str, str, str]:
    if explicit_feed_url:
        status, body, detail = fetch_text(explicit_feed_url)
        if status == "ok" and looks_like_feed(body, detail):
            return "ok", explicit_feed_url, body, "configured_feed"
        if status != "ok":
            return status, "", "", f"Configured feed failed: {detail}"
        return "missing", explicit_feed_url, body, "Configured feed was not RSS/Atom"

    status, body, detail = fetch_text(home_url)
    if status != "ok":
        return status, "", "", detail
    if looks_like_feed(body, detail):
        return "ok", home_url, body, "direct_feed"
    parser = FeedLinkParser(home_url)
    parser.feed(body)
    for url in [*parser.feed_urls, *candidate_feed_urls(home_url)]:
        status, feed_body, feed_detail = fetch_text(url)
        if status == "ok" and looks_like_feed(feed_body, feed_detail):
            return "ok", url, feed_body, "discovered_feed"
    return "missing", "", "", "No RSS/Atom feed discovered from public page"


def extract_json_array_after_key(text: str, key: str) -> list[object]:
    key_index = text.find(f'"{key}"')
    if key_index == -1:
        return []
    start = text.find("[", key_index)
    if start == -1:
        return []
    depth = 0
    in_string = False
    escaped = False
    end = None
    for index, char in enumerate(text[start:], start):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        else:
            if char == '"':
                in_string = True
            elif char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
    if end is None:
        return []
    try:
        parsed = json.loads(text[start:end])
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def beehiiv_archive_items(home_url: str, limit: int) -> tuple[str, list[dict[str, str]], str]:
    status, body, detail = fetch_text(home_url)
    if status != "ok":
        return status, [], detail
    posts = extract_json_array_after_key(body, "posts")
    items = []
    for post in posts[:limit]:
        if not isinstance(post, dict):
            continue
        slug = str(post.get("parameterized_web_title") or post.get("slug") or "").strip()
        link = urljoin(home_url, f"/p/{slug}") if slug else home_url
        title = clean_text(
            post.get("web_title")
            or post.get("meta_default_title")
            or post.get("meta_og_title")
            or "Beehiiv post",
            300,
        )
        summary = clean_text(
            post.get("web_subtitle")
            or post.get("meta_default_description")
            or post.get("meta_og_description")
            or post.get("meta_twitter_description")
            or "",
            1000,
        )
        provider_id = str(post.get("id") or link or title)
        items.append(
            {
                "title": title,
                "link": link,
                "published": str(post.get("created_at") or post.get("updated_at") or ""),
                "summary": summary,
                "guid": provider_id,
            }
        )
    if not items:
        return "missing", [], "Beehiiv page loaded but no posts array was found"
    return "ok", items, "beehiiv_archive"


def batch_archive_items(home_url: str, limit: int) -> tuple[str, list[dict[str, str]], str]:
    status, body, detail = fetch_text(home_url)
    if status != "ok":
        return status, [], detail
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    link_pattern = re.compile(
        r'<a[^>]+href=["\']([^"\']*/the-batch/[^"\']+)["\'][^>]*>(.*?)</a>',
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in link_pattern.finditer(body):
        link = urljoin(home_url, html.unescape(match.group(1)))
        if link in seen or link.rstrip("/") == home_url.rstrip("/"):
            continue
        title = clean_text(match.group(2), 240)
        if not title or len(title) < 8:
            continue
        seen.add(link)
        items.append(
            {
                "title": title,
                "link": link,
                "published": "",
                "summary": "DeepLearning.AI The Batch public archive item.",
                "guid": link,
            }
        )
        if len(items) >= limit:
            break
    if not items:
        return "missing", [], "The Batch page loaded but no archive links were parsed"
    return "ok", items, "the_batch_archive"


def looks_like_feed(body: str, detail: str) -> bool:
    lower_detail = detail.lower()
    lower_body = body[:500].lower()
    return (
        any(kind in lower_detail for kind in RSS_CONTENT_TYPES)
        or "<rss" in lower_body
        or "<feed" in lower_body
    )


def child_text(element: ET.Element, names: Iterable[str]) -> str:
    for name in names:
        found = element.find(name, RSS_NAMESPACES)
        if found is not None and found.text:
            return clean_text(found.text)
    return ""


def child_link(element: ET.Element) -> str:
    link = child_text(element, ["link"])
    if link:
        return link
    found = element.find("atom:link", RSS_NAMESPACES)
    if found is not None:
        return str(found.attrib.get("href", ""))
    return ""


def feed_items(feed_body: str, limit: int) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(feed_body.encode("utf-8"))
    except ET.ParseError:
        return regex_feed_items(feed_body, limit)
    items: list[dict[str, str]] = []
    if root.tag.endswith("rss") or root.find("channel") is not None:
        for item in root.findall(".//item")[:limit]:
            items.append(
                {
                    "title": child_text(item, ["title"]),
                    "link": child_link(item),
                    "published": child_text(item, ["pubDate", "published", "updated"]),
                    "summary": child_text(item, ["description", "content:encoded", "itunes:summary"]),
                    "guid": child_text(item, ["guid"]),
                }
            )
    else:
        entries = root.findall("atom:entry", RSS_NAMESPACES)
        if not entries:
            entries = [element for element in root.iter() if element.tag.endswith("entry")]
        for entry in entries[:limit]:
            items.append(
                {
                    "title": child_text(entry, ["atom:title"]),
                    "link": child_link(entry),
                    "published": child_text(entry, ["atom:published", "atom:updated"]),
                    "summary": child_text(entry, ["atom:summary", "atom:content"]),
                    "guid": child_text(entry, ["atom:id"]),
                }
            )
    return [item for item in items if item.get("title") or item.get("summary")]


def regex_tag_text(block: str, tag_name: str) -> str:
    pattern = rf"<(?:[A-Za-z0-9_]+:)?{re.escape(tag_name)}\b[^>]*>(.*?)</(?:[A-Za-z0-9_]+:)?{re.escape(tag_name)}>"
    match = re.search(pattern, block, flags=re.IGNORECASE | re.DOTALL)
    return clean_text(match.group(1)) if match else ""


def regex_feed_items(feed_body: str, limit: int) -> list[dict[str, str]]:
    items = []
    for match in re.finditer(r"<item\b[^>]*>(.*?)</item>", feed_body, flags=re.IGNORECASE | re.DOTALL):
        block = match.group(1)
        items.append(
            {
                "title": regex_tag_text(block, "title"),
                "link": regex_tag_text(block, "link"),
                "published": regex_tag_text(block, "pubDate"),
                "summary": regex_tag_text(block, "description")
                or regex_tag_text(block, "summary")
                or regex_tag_text(block, "encoded"),
                "guid": regex_tag_text(block, "guid"),
            }
        )
        if len(items) >= limit:
            break
    return [item for item in items if item.get("title") or item.get("summary")]


def evidence_rows(source: dict[str, str], feed_url: str, items: list[dict[str, str]]) -> list[dict[str, object]]:
    rows = []
    source_name = source["source_name"]
    category = source["source_category"]
    today = datetime.now().date().isoformat()
    for item in items:
        link = item.get("link", "")
        provider_id = item.get("guid") or link or hashlib.sha256(
            f"{source_name}|{item.get('title')}|{item.get('published')}".encode()
        ).hexdigest()
        rows.append(
            {
                "run_id": None,
                "symbol": "MARKET",
                "evidence_type": f"{category}_public_feed",
                "source_name": source_name,
                "source_type": category,
                "source_url": link or feed_url,
                "provider_endpoint": "public_rss_or_archive",
                "provider_id": str(provider_id)[:240],
                "source_timestamp": item.get("published") or today,
                "title": item.get("title") or f"{source_name} public feed item",
                "summary": clean_text(item.get("summary"), 1000),
                "raw_text_ref": feed_url,
                "confidence": "low" if category == "podcast" else "medium",
                "corroboration_status": "opinion_context_needs_corroboration",
                "user_feedback": "",
            }
        )
    return rows


def ingest_source(source: dict[str, str], item_limit: int) -> tuple[int, dict[str, object]]:
    source_name = source["source_name"]
    home_url = source.get("official_url", "")
    if not home_url:
        return 0, {
            "symbol": "MARKET",
            "provider": source_name,
            "field_name": "public_feed",
            "status": "missing",
            "message": "No public URL configured",
        }
    feed_url = source.get("feed_url", "")
    items: list[dict[str, str]] = []
    if "beehiiv.com" in urlparse(home_url).netloc and not feed_url:
        status, items, message = beehiiv_archive_items(home_url, item_limit)
        feed_url = home_url
    elif "deeplearning.ai" in urlparse(home_url).netloc and "the-batch" in home_url and not feed_url:
        status, items, message = batch_archive_items(home_url, item_limit)
        feed_url = home_url
    else:
        status, feed_url, feed_body, message = discover_feed_url(home_url, feed_url)
        if status == "ok":
            items = feed_items(feed_body, item_limit)
            if not items:
                status = "missing"
                message = "Feed discovered but no parseable items found"
    payload = {
        "source_name": source_name,
        "source_category": source.get("source_category", ""),
        "home_url": home_url,
        "feed_url": feed_url,
        "discovery_message": message,
    }
    if status == "ok":
        payload["item_count"] = len(items)
        payload["sample_titles"] = [item.get("title", "") for item in items[:5]]
    record_provider_payload(
        source_name,
        "public_feed",
        "MARKET",
        status,
        message,
        payload_json=payload,
    )
    inserted = record_research_evidence(evidence_rows(source, feed_url, items)) if status == "ok" else 0
    return inserted, {
        "symbol": "MARKET",
        "provider": source_name,
        "field_name": "public_feed",
        "status": status,
        "message": message,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest approved public research RSS/archive sources.")
    parser.add_argument("--sources", help="Comma-separated source names. Defaults to all configured public podcast/newsletter sources.")
    parser.add_argument("--item-limit", type=int, default=5, help="Maximum feed items per source.")
    parser.add_argument("--delay", type=float, default=0.2, help="Delay between sources.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_env()
    source_filter = (
        {source.strip() for source in args.sources.split(",") if source.strip()}
        if args.sources
        else None
    )
    sources = integration_rows(source_filter)
    if not sources:
        print("No public podcast/newsletter sources configured for ingestion.")
        return 1

    statuses: list[dict[str, object]] = []
    total_inserted = 0
    for index, source in enumerate(sources, start=1):
        inserted, status = ingest_source(source, max(1, args.item_limit))
        total_inserted += inserted
        statuses.append(status)
        print(f"{source['source_name']}: public_feed_status={status['status']} inserted={inserted}", flush=True)
        if index < len(sources) and args.delay > 0:
            time.sleep(args.delay)
    gaps = sum(1 for row in statuses if row.get("status") != "ok")
    run_id = record_provider_run(
        "Public research feeds",
        "ok" if statuses else "failed",
        f"sources={len(sources)}; inserted_evidence={total_inserted}; gaps={gaps}",
        statuses,
    )
    print(f"Recorded Public research feeds provider run {run_id} with {gaps} gaps")
    return 0 if statuses else 1


if __name__ == "__main__":
    sys.exit(main())
