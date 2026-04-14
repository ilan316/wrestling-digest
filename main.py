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

    # 3. Split clusters by promotion
    by_promo: dict[str, list] = defaultdict(list)
    for cluster in all_clusters:
        promo = cluster[0].get("promotion", "Other")
        by_promo[promo].append(cluster)

    print(f"[main] AEW={len(by_promo['AEW'])}  WWE={len(by_promo['WWE'])}  Other={len(by_promo['Other'])} clusters")

    # 4. For each promotion: filter lookback → summarize → send
    date_str = datetime.now().strftime("%d/%m")
    newer_than_ms = (time.time() - config.LOOKBACK_HOURS * 3600) * 1000

    for promo in PROMOTIONS:
        key = promo["key"]
        print(f"\n{'─' * 40}")

        raw_clusters = by_promo.get(key, [])
        clusters = [
            [a for a in cluster if a.get("published", 0) >= newer_than_ms]
            for cluster in raw_clusters
        ]
        clusters = [c for c in clusters if c]

        if not clusters:
            print(f"[{key}] No stories.")
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
