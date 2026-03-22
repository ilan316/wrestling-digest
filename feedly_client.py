"""OPML parser + RSS feed fetcher (replaces Feedly API)."""
from __future__ import annotations

import html
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import feedparser


def parse_opml(opml_path: str) -> dict[str, list[dict[str, str]]]:
    """
    Parse an OPML file and return a dict of {category_label: [{title, xmlUrl, htmlUrl}]}.
    """
    tree = ET.parse(opml_path)
    root = tree.getroot()
    body = root.find("body")
    if body is None:
        return {}

    categories: dict[str, list[dict[str, str]]] = {}
    for category_node in body.findall("outline"):
        label = category_node.get("title") or category_node.get("text", "Uncategorized")
        feeds = []
        for feed_node in category_node.findall("outline"):
            xml_url = feed_node.get("xmlUrl")
            if xml_url:
                feeds.append({
                    "title": feed_node.get("title") or feed_node.get("text", ""),
                    "xmlUrl": xml_url,
                    "htmlUrl": feed_node.get("htmlUrl", ""),
                })
        if feeds:
            categories[label] = feeds
    return categories


def _clean_html(text: str) -> str:
    clean = re.sub(r"<[^>]+>", " ", text or "")
    clean = html.unescape(clean)
    return re.sub(r"\s+", " ", clean).strip()


def _fetch_feed(feed: dict[str, str], newer_than: float) -> list[dict[str, Any]]:
    """Fetch a single RSS feed and return articles newer than the timestamp."""
    try:
        parsed = feedparser.parse(feed["xmlUrl"])
    except Exception as e:
        print(f"[rss] Error fetching {feed['xmlUrl']}: {e}")
        return []

    articles = []
    for entry in parsed.entries:
        # Get publish time
        pub_struct = entry.get("published_parsed") or entry.get("updated_parsed")
        if pub_struct:
            pub_ts = time.mktime(pub_struct)
        else:
            pub_ts = time.time()  # treat as now if no date

        if pub_ts < newer_than:
            continue

        title = html.unescape(entry.get("title", "(no title)"))
        title_upper = title.upper()
        if "SPOILER" in title_upper or "RESULTS" in title_upper or "HIGHLIGHTS" in title_upper:
            continue

        summary = _clean_html(
            entry.get("summary", "")
            or entry.get("content", [{}])[0].get("value", "")
        )

        articles.append({
            "id": entry.get("id") or entry.get("link", ""),
            "title": title,
            "url": entry.get("link", ""),
            "summary": summary,
            "published": int(pub_ts * 1000),
            "source_name": feed["title"],
            "source_url": feed["htmlUrl"],
        })
    return articles


def fetch_all(
    opml_path: str,
    categories_filter: list[str],
    lookback_hours: int,
) -> list[dict[str, Any]]:
    """
    Parse OPML, fetch all feeds (in parallel), return deduplicated articles
    from the last lookback_hours, sorted newest-first.
    """
    newer_than = time.time() - lookback_hours * 3600
    categories = parse_opml(opml_path)

    if categories_filter:
        lower_filter = {c.lower() for c in categories_filter}
        categories = {k: v for k, v in categories.items() if k.lower() in lower_filter}

    if not categories:
        print("[rss] No matching categories in OPML.")
        return []

    # Collect all feeds with their category label
    all_feeds: list[tuple[str, dict[str, str]]] = []
    for label, feeds in categories.items():
        for feed in feeds:
            all_feeds.append((label, feed))

    print(f"[rss] Fetching {len(all_feeds)} feeds across {len(categories)} categories...")

    all_articles: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(_fetch_feed, feed, newer_than): (label, feed)
            for label, feed in all_feeds
        }
        for future in as_completed(futures):
            label, feed = futures[future]
            articles = future.result()
            new = 0
            for a in articles:
                if a["id"] not in seen_ids:
                    seen_ids.add(a["id"])
                    a["category"] = label
                    all_articles.append(a)
                    new += 1
            print(f"[rss]   {feed['title']}: {new} new articles")

    all_articles.sort(key=lambda a: a["published"], reverse=True)
    print(f"[rss] Total unique articles: {len(all_articles)}")
    return all_articles
