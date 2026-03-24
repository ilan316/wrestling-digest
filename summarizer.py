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
            parts.append(f"  Excerpt: {a['summary'][:4000]}")
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

    prompt = f"""You are an experienced wrestling news editor. Below are {'multiple articles' if len(cluster) > 1 else 'an article'} covering the story: "{story_title}".

{cluster_text}

Write a complete, well-structured news article in English based on the content above.
- Preserve ALL information, details, quotes, and context
- Remove only pure duplicate sentences
- Use multiple paragraphs naturally
- Do not start with "Summary:" or "Title:" — just write the article directly
- Do not mention website/source names in the body
- If the excerpt is incomplete, summarize what is available — do not ask for more content"""

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
        seen_sources: set[str] = set()
        sources = []
        for a in cluster:
            name = a.get("source_name", "")
            if name not in seen_sources:
                seen_sources.add(name)
                sources.append({"title": a["title"], "url": a["url"], "source_name": name})

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
