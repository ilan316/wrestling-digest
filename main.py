#!/usr/bin/env python3
"""Feedly Daily Digest Agent — entry point."""
from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta

import config
import feedly_client
import clusterer
import summarizer
import email_sender

BLACKOUT_PATH = os.path.join(os.path.dirname(__file__), "blackout.json")

PROMOTIONS = [
    {"key": "AEW",   "label": "AEW Digest",       "emoji": "🔶"},
    {"key": "WWE",   "label": "WWE Digest",        "emoji": "🔴"},
    {"key": "Other", "label": "Wrestling Digest",  "emoji": "🤼"},
]


def _load_events() -> list[dict]:
    if not os.path.exists(BLACKOUT_PATH):
        return []
    try:
        with open(BLACKOUT_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _blackout_window(event: dict) -> tuple[datetime, datetime]:
    """Return (blackout_start, blackout_end) in Israel local time (naive).

    Blackout starts at 20:00 Israel time on the event date — the same hour
    the daily email job runs.  This means the 20:00 email on the event date
    is NOT blocked (strict < check), but every 20:00 run inside the window is.
    """
    event_date = datetime.strptime(event["date"], "%Y-%m-%d").date()
    blackout_hours = event.get("blackout_hours", 48)
    blackout_start = datetime(event_date.year, event_date.month, event_date.day, 20, 0)
    blackout_end   = blackout_start + timedelta(hours=blackout_hours)
    return blackout_start, blackout_end


def check_blackout(promotion: str, events: list[dict]) -> tuple[bool, str]:
    """Return (True, event_name) if now is strictly inside the blackout window."""
    if promotion == "Other":
        return False, ""

    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Jerusalem")).replace(tzinfo=None)

    for event in events:
        if event.get("promotion", "") != promotion:
            continue
        try:
            blackout_start, blackout_end = _blackout_window(event)
        except ValueError:
            continue
        # Strict on both sides: the 20:00 run at blackout_start goes through,
        # and the 20:00 run at blackout_end goes through.
        if blackout_start < now < blackout_end:
            return True, event["name"]

    return False, ""


def compute_lookback_hours(promotion: str, events: list[dict], default: int) -> int:
    """Return lookback hours for this promotion's next email.

    If a blackout just ended (within the last `default` hours), return the
    number of hours since the blackout started so the post-blackout email
    covers the entire blackout period.
    """
    if promotion == "Other":
        return default

    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Jerusalem")).replace(tzinfo=None)

    for event in events:
        if event.get("promotion", "") != promotion:
            continue
        try:
            blackout_start, blackout_end = _blackout_window(event)
        except ValueError:
            continue
        # Just came out of blackout: blackout_end <= now < blackout_end + default
        if blackout_end <= now < blackout_end + timedelta(hours=default):
            hours = int((now - blackout_start).total_seconds() / 3600) + 1
            return max(hours, default)

    return default


def run() -> None:
    print("=" * 50)
    print("Feedly Daily Digest Agent")
    print("=" * 50)

    events = _load_events()

    # Compute per-promotion lookback (extended after blackout)
    promo_lookbacks = {
        p["key"]: compute_lookback_hours(p["key"], events, config.LOOKBACK_HOURS)
        for p in PROMOTIONS
    }
    global_lookback = max(promo_lookbacks.values())
    if global_lookback > config.LOOKBACK_HOURS:
        print(f"[main] Extended lookback: {global_lookback}h (post-blackout)")

    # 1. Fetch all articles using the widest lookback needed
    articles = feedly_client.fetch_all(
        opml_path=config.OPML_PATH,
        categories_filter=config.CATEGORIES_FILTER,
        lookback_hours=global_lookback,
    )
    if not articles:
        print("[main] No articles found. Exiting.")
        return

    # 2. Cluster ALL articles at once (Claude classifies each by promotion)
    print(f"\n[main] Clustering {len(articles)} articles...")
    all_clusters = clusterer.group_by_story(
        articles=articles,
        api_key=config.CLAUDE_API_KEY,
        model=config.CLAUDE_MODEL,
    )

    # 3. Split clusters by promotion
    by_promo: dict[str, list] = defaultdict(list)
    for cluster in all_clusters:
        promo = cluster[0].get("promotion", "Other")
        by_promo[promo].append(cluster)

    print(f"[main] AEW={len(by_promo['AEW'])}  WWE={len(by_promo['WWE'])}  Other={len(by_promo['Other'])} clusters")

    # 4. For each promotion: filter lookback → blackout check → summarize → send
    date_str = datetime.now().strftime("%d/%m")

    for promo in PROMOTIONS:
        key = promo["key"]
        print(f"\n{'─' * 40}")

        # Filter articles to this promotion's lookback window
        promo_newer_than_ms = (time.time() - promo_lookbacks[key] * 3600) * 1000
        raw_clusters = by_promo.get(key, [])
        clusters = [
            [a for a in cluster if a.get("published", 0) >= promo_newer_than_ms]
            for cluster in raw_clusters
        ]
        clusters = [c for c in clusters if c]

        if not clusters:
            print(f"[{key}] No stories.")
            continue

        blocked, event_name = check_blackout(key, events)
        if blocked:
            print(f"[{key}] BLACKOUT — '{event_name}'. Skipping.")
            continue

        digest = summarizer.summarize_all(
            clusters=clusters,
            api_key=config.CLAUDE_API_KEY,
            model=config.CLAUDE_MODEL,
            min_cluster_size=config.MIN_CLUSTER_SIZE_FOR_SUMMARY,
        )

        # Date range across all clusters
        all_pub = [
            a["published"]
            for cluster in clusters
            for a in cluster
            if a.get("published")
        ]
        if all_pub:
            date_from = datetime.fromtimestamp(min(all_pub) / 1000).strftime("%d/%m")
            date_to   = datetime.fromtimestamp(max(all_pub) / 1000).strftime("%d/%m")
            date_range = date_from if date_from == date_to else f"{date_from} – {date_to}"
        else:
            date_range = date_str

        docs_dir = os.path.join(os.path.dirname(__file__), "docs")
        page_url = email_sender.save_page(
            digest=digest,
            promo_key=key,
            label=promo["label"],
            emoji=promo["emoji"],
            date_str=date_range,
            docs_dir=docs_dir,
        )

        email_sender.send(
            digest=digest,
            gmail_user=config.GMAIL_USER,
            gmail_app_password=config.GMAIL_APP_PASSWORD,
            recipient=config.RECIPIENT_EMAIL,
            title=promo["label"],
            emoji=promo["emoji"],
            date_range=date_range,
            pages_url=page_url,
        )

    print("\n[main] Done.")


if __name__ == "__main__":
    run()
