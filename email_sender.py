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


def _build_html(digest: list[dict[str, Any]], title: str = "Feedly Digest", date_str: str = "") -> str:
    date_str = date_str or datetime.now().strftime("%d/%m")
    total_articles = sum(s["count"] for s in digest)

    stories_parts = []
    for story in digest:
        badge = ""
        if story["count"] >= 2:
            badge = f'<span class="badge">{story["count"]} sources</span>'

        source_links = " · ".join(
            f'<a href="{s["url"]}" target="_blank">{s["source_name"] or s["title"][:40]}</a>'
            for s in story["sources"]
        )

        stories_parts.append(
            _STORY_TEMPLATE.format(
                title=_esc(story["story_title"]),
                badge=badge,
                summary=_esc(story["summary"]).replace("\n", "<br>"),
                source_links=source_links,
            )
        )

    return _HTML_TEMPLATE.format(
        header_title=_esc(title),
        date=date_str,
        story_count=len(digest),
        article_count=total_articles,
        stories_html="\n".join(stories_parts),
        pages_url=PAGES_URL,
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
) -> None:
    if not digest:
        print(f"[email] {title}: No stories — skipping.")
        return

    date_str = date_range or datetime.now().strftime("%d/%m")
    html_body = _build_html(digest, title=f"{emoji} {title}", date_str=date_str)
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


def save_page(all_digests: dict[str, tuple[list, str, str]], date_str: str, docs_dir: str) -> None:
    """Save combined digest as a clean HTML page for GitHub Pages / Eleven Reader."""
    sections = []
    total_stories = 0

    for promo_key, (digest, label, emoji) in all_digests.items():
        if not digest:
            continue
        total_stories += len(digest)
        stories_html = []
        for story in digest:
            sources_text = " · ".join(s.get("source_name", "") for s in story["sources"] if s.get("source_name"))
            first_url = story["sources"][0]["url"] if story.get("sources") else "#"
            stories_html.append(f"""
  <article>
    <h2><a href="{first_url}" target="_blank">{_esc(story['story_title'])}</a></h2>
    <p>{_esc(story['summary']).replace(chr(10), '<br>')}</p>
    <p class="meta">{_esc(sources_text)}</p>
  </article>""")
        sections.append(f"<section><h1>{emoji} {_esc(label)}</h1>{''.join(stories_html)}</section>")

    page_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wrestling Digest — {date_str}</title>
<style>
  body {{ font-family: Georgia, serif; max-width: 720px; margin: 40px auto; padding: 0 20px; color: #222; line-height: 1.7; }}
  h1 {{ font-size: 24px; border-bottom: 2px solid #eee; padding-bottom: 8px; margin-top: 40px; }}
  h2 {{ font-size: 18px; margin-top: 28px; }}
  h2 a {{ color: #1a1a2e; text-decoration: none; }}
  h2 a:hover {{ text-decoration: underline; }}
  p {{ margin: 8px 0; }}
  .meta {{ font-size: 12px; color: #888; }}
  .header {{ background: #1a1a2e; color: #fff; padding: 24px; border-radius: 8px; margin-bottom: 32px; }}
  .header h1 {{ color: #fff; border: none; margin: 0; font-size: 20px; }}
  .header p {{ margin: 4px 0 0; opacity: .7; font-size: 13px; }}
</style>
</head>
<body>
<div class="header">
  <h1>🤼 Wrestling Digest</h1>
  <p>{date_str} &nbsp;·&nbsp; {total_stories} stories</p>
</div>
{''.join(sections)}
</body>
</html>"""

    os.makedirs(docs_dir, exist_ok=True)

    # Save dated archive file
    dated_name = datetime.now().strftime("%Y-%m-%d") + ".html"
    dated_path = os.path.join(docs_dir, dated_name)
    with open(dated_path, "w", encoding="utf-8") as f:
        f.write(page_html)

    # Save as index.html (always latest)
    index_path = os.path.join(docs_dir, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(page_html)

    # Delete dated files older than 10 days
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(days=10)
    for fname in os.listdir(docs_dir):
        if fname == "index.html" or not fname.endswith(".html"):
            continue
        try:
            file_date = datetime.strptime(fname.replace(".html", ""), "%Y-%m-%d")
            if file_date < cutoff:
                os.remove(os.path.join(docs_dir, fname))
                print(f"[page] Deleted old file: {fname}")
        except ValueError:
            pass

    print(f"[page] Saved digest page → {dated_path} + index.html")
