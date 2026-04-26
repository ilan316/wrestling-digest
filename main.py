#!/usr/bin/env python3
"""Feedly Daily Digest Agent — entry point."""
from __future__ import annotations

import os
import time
from collections import defaultdict
from datetime import datetime

import config
import feedly_client
import clusterer
import summarizer
import email_sender

PROMOTIONS = [
    {"key": "AEW",   "label": "AEW Digest",       "emoji": "🔶"},
    {"key": "WWE",   "label": "WWE Digest",        "emoji": "🔴"},
    {"key": "Other", "label": "Wrestling Digest",  "emoji": "🤼"},
]

PROMO_ORDER = {"AEW": 0, "WWE": 1, "Other": 2}


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

    # 2. Cluster ALL articles at once (Claude classifies each by promotion)
    print(f"\n[main] Clustering {len(articles)} articles...")
    all_clusters = clusterer.group_by_story(
        articles=articles,
        api_key=config.CLAUDE_API_KEY,
        model=config.CLAUDE_MODEL,
    )

    # 3. Filter lookback window
    newer_than_ms = (time.time() - config.LOOKBACK_HOURS * 3600) * 1000
    all_clusters = [
        [a for a in cluster if a.get("published", 0) >= newer_than_ms]
        for cluster in all_clusters
    ]
    all_clusters = [c for c in all_clusters if c]

    by_promo: dict[str, int] = defaultdict(int)
    for cluster in all_clusters:
        by_promo[cluster[0].get("promotion", "Other")] += 1
    print(f"[main] AEW={by_promo['AEW']}  WWE={by_promo['WWE']}  Other={by_promo['Other']} clusters")

    if not all_clusters:
        print("[main] No stories after filtering. Exiting.")
        return

    # 4. Summarize all clusters together
    digest = summarizer.summarize_all(
        clusters=all_clusters,
        api_key=config.CLAUDE_API_KEY,
        model=config.CLAUDE_MODEL,
        min_cluster_size=config.MIN_CLUSTER_SIZE_FOR_SUMMARY,
    )

    # Sort: AEW → WWE → Other, then by source count descending
    digest.sort(key=lambda s: (PROMO_ORDER.get(s.get("promotion", "Other"), 2), -s["count"]))

    # Date range across all articles
    date_str = datetime.now().strftime("%d/%m")
    all_pub = [
        a["published"]
        for cluster in all_clusters
        for a in cluster
        if a.get("published")
    ]
    if all_pub:
        date_from = datetime.fromtimestamp(min(all_pub) / 1000).strftime("%d/%m")
        date_to   = datetime.fromtimestamp(max(all_pub) / 1000).strftime("%d/%m")
        date_range = date_from if date_from == date_to else f"{date_from} – {date_to}"
    else:
        date_range = date_str

    # 5. Save per-promotion GitHub Pages (unchanged)
    docs_dir = os.path.join(os.path.dirname(__file__), "docs")
    by_promo_digest: dict[str, list] = defaultdict(list)
    for story in digest:
        by_promo_digest[story.get("promotion", "Other")].append(story)

    pages_url = email_sender.BASE_PAGES_URL
    for promo in PROMOTIONS:
        key = promo["key"]
        promo_digest = by_promo_digest.get(key, [])
        if promo_digest:
            pages_url = email_sender.save_page(
                digest=promo_digest,
                promo_key=key,
                label=promo["label"],
                emoji=promo["emoji"],
                date_str=date_range,
                docs_dir=docs_dir,
            )

    # 6. Send ONE combined email
    email_sender.send(
        digest=digest,
        gmail_user=config.GMAIL_USER,
        gmail_app_password=config.GMAIL_APP_PASSWORD,
        recipient=config.RECIPIENT_EMAIL,
        title="Wrestling Digest",
        emoji="🤼",
        date_range=date_range,
        pages_url=pages_url,
    )

    print("\n[main] Done.")


if __name__ == "__main__":
    run()
