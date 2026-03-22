"""Group articles by news story using Claude."""
from __future__ import annotations

import json
from typing import Any

import anthropic


def group_by_story(
    articles: list[dict[str, Any]],
    api_key: str,
    model: str,
) -> list[list[dict[str, Any]]]:
    """
    Use Claude to group articles by the story they cover.
    Returns a list of clusters, each cluster is a list of article dicts.
    Articles that don't share a story with anyone else get their own cluster.
    """
    if not articles:
        return []

    # Build numbered list for the prompt
    lines = []
    for i, a in enumerate(articles):
        summary_snippet = a.get("summary", "")[:120]
        lines.append(f"{i}: {a['title']} [{a.get('source_name', '')}]")
        if summary_snippet:
            lines.append(f"   {summary_snippet}")
    article_list = "\n".join(lines)

    prompt = f"""You are a wrestling news editor. Below is a numbered list of articles (title + snippet).
Do two things:
1. Group articles by the news story they cover.
2. For each group, identify the wrestling promotion: "AEW", "WWE", or "Other" (NJPW, AAA, MLW, etc.).
   Use the full context — even if "AEW" or "WWE" is not in the title, infer from wrestlers, shows, and events mentioned.

Each article index must appear in exactly one group.

Return ONLY valid JSON (no markdown, no explanation):
[
  {{"story_title": "Short descriptive title", "promotion": "AEW", "indices": [0, 3, 7]}},
  {{"story_title": "Another story", "promotion": "WWE", "indices": [1, 2]}}
]

Articles:
{article_list}"""

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()

    # Parse JSON — Claude sometimes wraps in ```json ... ```
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        groups: list[dict[str, Any]] = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[clusterer] JSON parse error: {e}\nRaw response:\n{raw[:500]}")
        # Fallback: one article per cluster
        return [[a] for a in articles]

    clusters: list[list[dict[str, Any]]] = []
    assigned: set[int] = set()
    for group in groups:
        story_title: str = group.get("story_title", "")
        promotion: str = group.get("promotion", "Other")
        indices: list[int] = group.get("indices", [])
        cluster_articles = []
        for idx in indices:
            if 0 <= idx < len(articles) and idx not in assigned:
                article = dict(articles[idx])
                article["_story_title"] = story_title
                article["promotion"] = promotion  # Claude's classification
                cluster_articles.append(article)
                assigned.add(idx)
        if cluster_articles:
            clusters.append(cluster_articles)

    # Add any articles Claude didn't assign to any group
    for i, article in enumerate(articles):
        if i not in assigned:
            a = dict(article)
            a["_story_title"] = article["title"]
            if "_story_title" not in a or not a["_story_title"]:
                a["_story_title"] = article["title"]
            clusters.append([a])

    # Sort clusters: largest first
    clusters.sort(key=len, reverse=True)

    total = sum(len(c) for c in clusters)
    dropped = len(articles) - len(assigned)
    if dropped:
        print(f"[clusterer] WARNING: {dropped} articles were not assigned by Claude — added as solo clusters")
    print(f"[clusterer] {len(articles)} articles -> {len(clusters)} story clusters (total mapped: {total})")
    return clusters
