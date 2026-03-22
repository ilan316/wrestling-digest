#!/usr/bin/env python3
"""Feedly Daily Digest Agent — entry point."""
from __future__ import annotations

import json
import os
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


def check_blackout(promotion: str) -> tuple[bool, str]:
    """Return (True, event_name) if now is within the blackout window for this promotion."""
    if promotion == "Other":
        return False, ""
    if not os.path.exists(BLACKOUT_PATH):
        return False, ""
    try:
        with open(BLACKOUT_PATH, encoding="utf-8") as f:
            events = json.load(f)
    except Exception:
        return False, ""

    now = datetime.now()
    for event in events:
        if event.get("promotion", "") != promotion:
            continue
        try:
            event_date = datetime.strptime(event["date"], "%Y-%m-%d").date()
        except ValueError:
            continue
        blackout_hours = event.get("blackout_hours", 48)
        # Blackout starts at 00:00 on event_date
        blackout_start = datetime(event_date.year, event_date.month, event_date.day, 0, 0)
        # Blackout ends at 20:00 — (blackout_hours//24 - 1) days after event_date
        # 24h → same day at 20:00 (20 hours total)
        # 48h → next day at 20:00 (44 hours total)
        offset_days = blackout_hours // 24 - 1
        blackout_end = datetime(event_date.year, event_date.month, event_date.day, 20, 0) + timedelta(days=offset_days)
        if blackout_start <= now < blackout_end:
            return True, event["name"]
    return False, ""


def run() -> None:
    print("=" * 50)
    print("Feedly Daily Digest Agent")
    print("=" * 50)

    # 1. Fetch all articles
    articles = feedly_client.fetch_all(
        opml_path=config.OPML_PATH,
        categories_filter=config.CATEGORIES_FILTER,
        lookback_hours=config.LOOKBACK_HOURS,
    )
    if not articles:
        print("[main] No articles found. Exiting.")
        return

    # 2. Claude clusters ALL articles at once and classifies each by promotion
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

    # 4. For each promotion: blackout check → summarize → send
    date_str = datetime.now().strftime("%d/%m")

    for promo in PROMOTIONS:
        key = promo["key"]
        clusters = by_promo.get(key, [])
        print(f"\n{'─' * 40}")

        if not clusters:
            print(f"[{key}] No stories.")
            continue

        blocked, event_name = check_blackout(key)
        if blocked:
            print(f"[{key}] BLACKOUT — '{event_name}'. Skipping.")
            continue

        digest = summarizer.summarize_all(
            clusters=clusters,
            api_key=config.CLAUDE_API_KEY,
            model=config.CLAUDE_MODEL,
            min_cluster_size=config.MIN_CLUSTER_SIZE_FOR_SUMMARY,
        )

        # Calculate article date range across all clusters
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
