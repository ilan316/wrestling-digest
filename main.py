#!/usr/bin/env python3
"""Feedly Daily Digest Agent — entry point."""
from __future__ import annotations

import os
import time
from datetime import datetime

import config
import feedly_client
import clusterer
import summarizer
import email_sender

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

    by_promo: dict[str, int] = {}
    for cluster in all_clusters:
        key = cluster[0].get("promotion", "Other")
        by_promo[key] = by_promo.get(key, 0) + 1
    print(f"[main] AEW={by_promo.get('AEW', 0)}  WWE={by_promo.get('WWE', 0)}  Other={by_promo.get('Other', 0)} clusters")

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

    # 5. Save one combined GitHub Pages file
    docs_dir = os.path.join(os.path.dirname(__file__), "docs")
    pages_url = email_sender.save_combined_page(
        digest=digest,
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
