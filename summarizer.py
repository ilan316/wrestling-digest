"""Summarize story clusters using Claude."""
from __future__ import annotations

from typing import Any

import anthropic


def _build_cluster_text(cluster: list[dict[str, Any]]) -> str:
    parts = []
    for a in cluster:
        parts.append(f"- Title: {a['title']}")
        parts.append(f"  Source: {a.get('source_name', 'Unknown')}")
        if a.get("summary"):
            parts.append(f"  Excerpt: {a['summary'][:1500]}")
        parts.append("")
    return "\n".join(parts)


def summarize_cluster(
    cluster: list[dict[str, Any]],
    story_title: str,
    api_key: str,
    model: str,
) -> str:
    """Generate a unified Hebrew summary for a cluster of related articles."""
    cluster_text = _build_cluster_text(cluster)

    prompt = f"""You are an experienced wrestling news editor. Below are multiple articles from different sources covering the same story: "{story_title}".

{cluster_text}

Merge these articles into one single, complete article in English.
- Preserve ALL information, details, quotes, and context from every source
- Remove only pure duplicates (exact same sentence repeated across sources)
- Add unique details from each source — do not leave anything out
- Use multiple paragraphs naturally
- Do not start with "Summary:" or "Title:" — just write the article directly
- Do not mention website/source names in the body"""

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def summarize_all(
    clusters: list[list[dict[str, Any]]],
    api_key: str,
    model: str,
    min_cluster_size: int,
) -> list[dict[str, Any]]:
    """
    For each cluster produce:
      {story_title, summary, sources: [{title, url, source_name}], count}
    """
    results = []
    for cluster in clusters:
        story_title: str = cluster[0].get("_story_title", cluster[0]["title"])
        sources = [
            {"title": a["title"], "url": a["url"], "source_name": a.get("source_name", "")}
            for a in cluster
        ]

        print(f"[summarizer] Summarizing: {story_title!r} ({len(cluster)} articles)")
        try:
            summary = summarize_cluster(cluster, story_title, api_key, model)
        except Exception as e:
            print(f"[summarizer] Error: {e}")
            summary = cluster[0].get("summary", "") or "(סיכום לא זמין)"

        results.append({
            "story_title": story_title,
            "summary": summary,
            "sources": sources,
            "count": len(cluster),
        })

    return results
