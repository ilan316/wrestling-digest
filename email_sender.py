"""Build and send the daily digest HTML email via Gmail SMTP."""
from __future__ import annotations

import os
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

PAGES_URL = "https://ilan316.github.io/wrestling-digest/"


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html dir="ltr" lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
    background: #f5f5f5;
    margin: 0;
    padding: 0;
    direction: ltr;
  }}
  .wrapper {{
    max-width: 680px;
    margin: 24px auto;
    background: #fff;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0,0,0,.08);
  }}
  .header {{
    background: #1a1a2e;
    color: #fff;
    padding: 28px 32px 20px;
  }}
  .header h1 {{
    margin: 0 0 4px;
    font-size: 22px;
    font-weight: 700;
  }}
  .header .date {{
    font-size: 13px;
    opacity: .7;
  }}
  .content {{
    padding: 24px 32px;
  }}
  .story {{
    border-bottom: 1px solid #eee;
    padding: 20px 0;
  }}
  .story:last-child {{
    border-bottom: none;
  }}
  .story-title {{
    font-size: 17px;
    font-weight: 700;
    color: #1a1a2e;
    margin: 0 0 10px;
  }}
  .badge {{
    display: inline-block;
    background: #e8f0fe;
    color: #1a73e8;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 12px;
    margin-right: 8px;
    vertical-align: middle;
  }}
  .summary {{
    font-size: 14px;
    line-height: 1.7;
    color: #333;
    margin: 10px 0 14px;
  }}
  .sources {{
    font-size: 12px;
    color: #888;
  }}
  .sources a {{
    color: #1a73e8;
    text-decoration: none;
    margin-left: 10px;
  }}
  .sources a:hover {{
    text-decoration: underline;
  }}
  .read-btn {{
    display: inline-block;
    margin-top: 10px;
    padding: 7px 18px;
    background: #1a73e8;
    color: #fff !important;
    font-size: 13px;
    font-weight: 600;
    border-radius: 20px;
    text-decoration: none;
  }}
  .read-all-btn {{
    display: inline-block;
    margin-top: 14px;
    padding: 9px 22px;
    background: #fff;
    color: #1a1a2e !important;
    font-size: 13px;
    font-weight: 700;
    border-radius: 20px;
    text-decoration: none;
    letter-spacing: .3px;
  }}
  .executive {{
    background: #f0f4ff;
    border-left: 4px solid #4a6cf7;
    padding: 14px 16px;
    margin-bottom: 24px;
    border-radius: 4px;
    font-size: 14px;
    line-height: 1.7;
    color: #333;
  }}
  .executive strong {{
    display: block;
    margin-bottom: 6px;
    color: #1a1a2e;
    font-size: 13px;
  }}
  .tldr {{
    font-size: 13px;
    font-style: italic;
    color: #555;
    border-left: 3px solid #ccc;
    padding-left: 10px;
    margin: 8px 0 10px;
  }}
  .hot-badge {{
    display: inline-block;
    background: #fff3e0;
    color: #e65100;
    font-size: 11px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 12px;
    margin-right: 6px;
    vertical-align: middle;
  }}
  .footer {{
    background: #f9f9f9;
    text-align: center;
    padding: 16px;
    font-size: 12px;
    color: #aaa;
    border-top: 1px solid #eee;
  }}
</style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <h1>{header_title}</h1>
    <div class="date">{date} &nbsp;·&nbsp; {story_count} stories &nbsp;·&nbsp; {article_count} articles</div>
    <a class="read-all-btn" href="{pages_url}" target="_blank">📖 קרא באפליקציה</a>
  </div>
  <div class="content">
    {executive_html}
    {stories_html}
  </div>
  <div class="footer">Generated automatically by Feedly Digest Agent</div>
</div>
</body>
</html>
"""

_STORY_TEMPLATE = """\
<div class="story">
  <div class="story-title">
    {title}
    {badge}
  </div>
  <div class="summary">{summary}</div>
  <div class="sources">Sources: {source_links}</div>
</div>
"""


def _build_html(digest: list[dict[str, Any]], title: str = "Feedly Digest", date_str: str = "", pages_url: str = "") -> str:
    date_str = date_str or datetime.now().strftime("%d/%m")
    total_articles = sum(s["count"] for s in digest)

    # Bullet list of TL;DRs at the top
    bullets = "".join(
        f'<li>{_esc(s["tldr"])}</li>' for s in digest if s.get("tldr")
    )
    executive_html = f'<div class="executive"><strong>TL;DR</strong><ul>{bullets}</ul></div>' if bullets else ""

    stories_parts = []
    for story in digest:
        badges = ""
        if story["count"] >= 3:
            badges += '<span class="hot-badge">🔥 HOT</span>'
        if story["count"] >= 2:
            badges += f'<span class="badge">{story["count"]} sources</span>'

        source_links = " · ".join(
            f'<a href="{s["url"]}" target="_blank">{s["source_name"] or s["title"][:40]}</a>'
            for s in story["sources"]
        )

        stories_parts.append(
            _STORY_TEMPLATE.format(
                title=_esc(story["story_title"]),
                badge=badges,
                summary=_esc(story["summary"]).replace("\n", "<br>"),
                source_links=source_links,
            )
        )

    return _HTML_TEMPLATE.format(
        header_title=_esc(title),
        date=date_str,
        story_count=len(digest),
        article_count=total_articles,
        executive_html=executive_html,
        stories_html="\n".join(stories_parts),
        pages_url=pages_url or PAGES_URL,
    )


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def send(
    digest: list[dict[str, Any]],
    gmail_user: str,
    gmail_app_password: str,
    recipient: str,
    title: str = "Feedly Digest",
    emoji: str = "📰",
    date_range: str = "",
    pages_url: str = "",
) -> None:
    if not digest:
        print(f"[email] {title}: No stories — skipping.")
        return

    date_str = date_range or datetime.now().strftime("%d/%m")
    html_body = _build_html(digest, title=f"{emoji} {title}", date_str=date_str, pages_url=pages_url)
    subject = f"[feedly-digest] {emoji} {title} | {date_str} ({len(digest)} stories)"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = recipient
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(gmail_user, gmail_app_password)
        server.sendmail(gmail_user, recipient, msg.as_string())

    print(f"[email] Sent digest to {recipient} — {len(digest)} stories")


_PAGE_STYLE = """
  body { font-family: Georgia, serif; max-width: 720px; margin: 40px auto; padding: 0 20px; color: #222; line-height: 1.7; }
  h1 { font-size: 22px; border-bottom: 2px solid #eee; padding-bottom: 8px; margin-top: 32px; }
  h2 { font-size: 17px; margin-top: 24px; }
  h2 a { color: #1a1a2e; text-decoration: none; }
  h2 a:hover { text-decoration: underline; }
  p { margin: 8px 0; }
  .meta { font-size: 12px; color: #888; }
  .hdr { background: #1a1a2e; color: #fff; padding: 24px; border-radius: 8px; margin-bottom: 32px; }
  .hdr h1 { color: #fff; border: none; margin: 0; font-size: 20px; }
  .hdr p { margin: 4px 0 0; opacity: .7; font-size: 13px; }
  .executive { background: #f0f4ff; border-left: 4px solid #4a6cf7; padding: 14px 16px; margin-bottom: 28px; border-radius: 4px; font-size: 14px; }
  .executive strong { display: block; margin-bottom: 6px; color: #1a1a2e; }
  .tldr { font-size: 13px; font-style: italic; color: #555; border-left: 3px solid #ccc; padding-left: 10px; margin: 6px 0 10px; }
"""

BASE_PAGES_URL = "https://ilan316.github.io/wrestling-digest/"


def save_page(
    digest: list[dict[str, Any]],
    promo_key: str,
    label: str,
    emoji: str,
    date_str: str,
    docs_dir: str,
) -> str:
    """Save a per-promotion HTML page. Returns the public URL."""
    from datetime import timedelta

    # Bullet list of TL;DRs
    bullets = "".join(
        f'<li>{_esc(s["tldr"])}</li>' for s in digest if s.get("tldr")
    )
    executive_block = f'<div class="executive"><strong>TL;DR</strong><ul>{bullets}</ul></div>' if bullets else ""

    stories_html = []
    for story in digest:
        source_links = " · ".join(
            f'<a href="{s["url"]}" target="_blank">{_esc(s.get("source_name", "") or s.get("title", "")[:40])}</a>'
            for s in story["sources"] if s.get("url")
        )
        first_url = story["sources"][0]["url"] if story.get("sources") else "#"
        hot_label = "🔥 " if story.get("count", 0) >= 3 else ""
        stories_html.append(f"""
  <article>
    <h2><a href="{first_url}" target="_blank">{hot_label}{_esc(story['story_title'])}</a></h2>
    <p>{_esc(story['summary']).replace(chr(10), '<br>')}</p>
    <p class="meta">{source_links}</p>
  </article>""")

    page_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{emoji} {label} — {date_str}</title>
<style>{_PAGE_STYLE}</style>
</head>
<body>
<div class="hdr">
  <h1>{emoji} {_esc(label)}</h1>
  <p>{date_str} &nbsp;·&nbsp; {len(digest)} stories</p>
</div>
{executive_block}
{''.join(stories_html)}
</body>
</html>"""

    os.makedirs(docs_dir, exist_ok=True)

    # Save dated per-promotion file: 2026-03-23-aew.html
    today = datetime.now().strftime("%Y-%m-%d")
    fname = f"{today}-{promo_key.lower()}.html"
    fpath = os.path.join(docs_dir, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(page_html)

    # Delete files for this promotion older than 10 days
    cutoff = datetime.now() - timedelta(days=10)
    prefix = f"-{promo_key.lower()}.html"
    for old in os.listdir(docs_dir):
        if not old.endswith(prefix):
            continue
        try:
            file_date = datetime.strptime(old.replace(prefix, ""), "%Y-%m-%d")
            if file_date < cutoff:
                os.remove(os.path.join(docs_dir, old))
                print(f"[page] Deleted old file: {old}")
        except ValueError:
            pass

    url = f"{BASE_PAGES_URL}{fname}"
    print(f"[page] Saved → {fpath} ({url})")

    # Update index.html with links to all available pages
    _update_index(docs_dir)

    return url


def _update_index(docs_dir: str) -> None:
    """Rebuild index.html with links to all dated promotion pages."""
    files = sorted(
        [f for f in os.listdir(docs_dir) if f != "index.html" and f.endswith(".html") and f != ".nojekyll"],
        reverse=True,
    )
    links = ""
    for fname in files:
        parts = fname.replace(".html", "").rsplit("-", 1)
        if len(parts) == 2:
            date_part, promo = parts[0], parts[1].upper()
            emoji = {"AEW": "🔶", "WWE": "🔴", "OTHER": "🤼"}.get(promo, "📰")
            links += f'<li><a href="{fname}">{emoji} {promo} — {date_part}</a></li>\n'

    index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>🤼 Wrestling Digest</title>
<style>
  body {{ font-family: -apple-system, Arial, sans-serif; max-width: 600px; margin: 40px auto; padding: 0 20px; }}
  .hdr {{ background: #1a1a2e; color: #fff; padding: 24px; border-radius: 8px; margin-bottom: 24px; }}
  .hdr h1 {{ margin: 0; font-size: 22px; }}
  ul {{ list-style: none; padding: 0; }}
  li {{ margin: 10px 0; }}
  a {{ color: #1a73e8; font-size: 16px; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<div class="hdr"><h1>🤼 Wrestling Digest</h1></div>
<ul>
{links}</ul>
</body>
</html>"""

    index_path = os.path.join(docs_dir, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)
    print("[page] Updated index.html")
