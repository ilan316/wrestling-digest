"""Classify articles by wrestling promotion: AEW, WWE, or Other."""
from __future__ import annotations

import re
from typing import Any

AEW_TERMS = ["aew", "all elite wrestling", "all elite"]
WWE_TERMS = ["wwe", "world wrestling entertainment"]


def _has(text: str, terms: list[str]) -> bool:
    for term in terms:
        if re.search(r'\b' + re.escape(term) + r'\b', text):
            return True
    return False


def classify(article: dict[str, Any]) -> str:
    """Return 'AEW', 'WWE', or 'Other' based on AEW/WWE mentions in title+body."""
    text = f" {article.get('title', '')} {article.get('summary', '')} ".lower()

    has_aew = _has(text, AEW_TERMS)
    has_wwe = _has(text, WWE_TERMS)

    if has_aew and not has_wwe:
        return "AEW"
    if has_wwe and not has_aew:
        return "WWE"
    if has_aew and has_wwe:
        # Both mentioned — count occurrences
        aew_n = sum(len(re.findall(r'\b' + re.escape(t) + r'\b', text)) for t in AEW_TERMS)
        wwe_n = sum(len(re.findall(r'\b' + re.escape(t) + r'\b', text)) for t in WWE_TERMS)
        return "AEW" if aew_n >= wwe_n else "WWE"
    return "Other"


def classify_all(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {"AEW": 0, "WWE": 0, "Other": 0}
    for article in articles:
        promo = classify(article)
        article["promotion"] = promo
        counts[promo] += 1
    print(f"[classifier] AEW={counts['AEW']}  WWE={counts['WWE']}  Other={counts['Other']}")
    return articles
