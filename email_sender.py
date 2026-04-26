"""Build and send the daily digest HTML email via Gmail SMTP."""
from __future__ import annotations

import base64
import os
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

PAGES_URL = "https://ilan316.github.io/wrestling-digest/"

_AEW_SVG = (
    '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="#e65100">'
    '<path d="M0 6.925v10.086h3.674v-.51H.53V7.435h4.526v-.51zm18.944 0v.511h4.526V16.5h-3.144v.511H24V6.925z'
    "m-7.727-.891v1.453h1.537v-.383H11.71V6.91h.86v-.336h-.86v-.157h1.044v-.383H11.71zm1.765 0v1.453h1.39V7.06"
    "h-.897V6.034zm1.551 0v1.453h.493V6.034zm.648 0v.427h.557v1.026h.493V6.461h.558v-.427h-1.051zm1.765 0v1.453"
    "h1.537v-.383H17.44V6.91h.86v-.336h-.86v-.157h1.044v-.383H17.44zM11.45 8.225l-3.785.006.015 3.466 1.57 4.01"
    "h5.144l-.707-1.77H9.84V10h2.32zm-1.288 2.862v1.77h3.107l-.712-1.77zM6.265 6.034l-.748 1.453h.538l.122-.278"
    "h.699l.135.278h.536l-.753-1.453zm1.363 0v1.453h1.39V7.06h-.897V6.034zm1.55 0v1.453h1.39V7.06h-.896V6.034z"
    "m-2.65.444l.187.391h-.377zm16.29 1.73l-2.148.003-1.368 3.47-.938-3.467-2.142.003-.92 3.443-1.355-3.44"
    "-2.177.004 2.966 7.483h1.633l.938-3.462.934 3.462h1.653zm-16.844.025l-1.845.003-2.946 7.472H3.37l.342-.9"
    "h2.333l-.686-1.747h-.955l.635-1.673 1.706 4.32h2.17zm13.091 8.195c-.398.002-.663.14-.805.316a.76.76 0 00"
    ".005.91c.603.625 1.574.134 1.632.008v-.622h-.892v.344h.405v.086c-.114.152-.598.143-.722-.053-.124-.225"
    "-.038-.374.008-.444.277-.3.753-.062.784.004l.365-.293a1.332 1.332 0 00-.78-.256zm-7.877.01a2.177 2.177 0"
    " 00-.269.02c-.293.06-.476.207-.517.346-.128.491.571.567.571.567.623.03.571.098.572.123-.065.136-.42.087"
    "-.529.07-.221-.042-.43-.186-.43-.186l-.271.3c.76.482 1.38.226 1.48.17.3-.171.29-.484.192-.621-.076-.093"
    "-.307-.207-.535-.232-.204-.048-.604-.011-.558-.141.06-.12.682-.04.845.095l.24-.295c-.233-.168-.517-.22"
    "-.791-.216zm-7.085.047l.504 1.397h.505l.278-.854.266.854h.506l.502-1.397h-.497l-.258.866-.297-.866h-.444"
    "l-.294.874-.265-.874zm2.693 0v1.397h.502v-.392h.31l.324.392h.591l-.384-.448c.6-.234.334-.927-.234-.95h-.06"
    "zm1.89 0v1.397h1.537v-.328H9.18v-.195h.86v-.335h-.86v-.158h1.044v-.381zm3.427 0v.413h.557v.984h.494v-.984"
    "h.557v-.413zm1.758 0v1.397h1.39V17.5h-.897v-1.016zm1.562 0v1.397h.493V16.485zm.766 0v1.397h.493v-.804"
    'l.772.804h.466v-1.396h-.493v.761l-.716-.761zm-8.904.372h.531c.19-.003.189.286 0 .292h-.53z"/>'
    "</svg>"
)

_WWE_SVG = (
    '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="#c62828">'
    '<path d="M24 1.047L15.67 18.08l-3.474-8.53-3.474 8.53L.393 1.048l3.228 8.977 3.286 8.5C3.874 19.334'
    " 1.332 20.46 0 21.75c.443-.168 3.47-1.24 7.409-1.927l1.21 3.129 1.552-3.518a36.769 36.769 0 0 1 3.96"
    "-.204l1.644 3.722 1.4-3.62c2.132.145 3.861.426 4.675.692 0 0 .92-1.962 1.338-2.866a54.838 54.838 0 0"
    " 0-5.138-.092l2.722-7.042zm-21.84.026L8.64 13.86l3.568-9.155 3.567 9.155 6.481-12.788-6.433 8.452"
    'l-3.615-8.22-3.615 8.22zm10.036 13.776l1.115 2.523a42.482 42.482 0 0 0-2.363.306Z"/>'
    "</svg>"
)

def _logo_img(svg: str, size: int = 28) -> str:
    b64 = base64.b64encode(svg.encode()).decode()
    return (
        f'<img src="data:image/svg+xml;base64,{b64}" '
        f'width="{size}" height="{size}" '
        f'style="vertical-align:middle;margin-right:8px;" alt="">'
    )


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
  .executive ul li {{
    margin-bottom: 12px;
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
  .section-header {{
    margin: 28px 0 4px;
    padding: 10px 14px;
    border-radius: 6px;
    font-size: 15px;
    font-weight: 800;
    letter-spacing: .4px;
  }}
  .section-header:first-child {{
    margin-top: 0;
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
<div class="story" id="{anchor}">
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

    # Bullet list of TL;DRs at the top — each links to its story anchor
    bullets = "".join(
        f'<li><a href="#story-{i}" style="color:#1a1a2e;text-decoration:none;">{_esc(s["tldr"])}</a></li>'
        for i, s in enumerate(digest) if s.get("tldr")
    )
    executive_html = f'<div class="executive"><strong>TL;DR</strong><ul>{bullets}</ul></div>' if bullets else ""

    _PROMO_SECTIONS = [
        ("AEW",   f'{_logo_img(_AEW_SVG)}AEW News',            "#fff3e0", "#e65100"),
        ("WWE",   f'{_logo_img(_WWE_SVG)}WWE News',            "#fce8e8", "#c62828"),
        ("Other", "🤼 Other Wrestling News",                    "#e8f5e9", "#2e7d32"),
    ]

    stories_parts = []
    current_promo = None
    for i, story in enumerate(digest):
        story_promo = story.get("promotion", "Other")

        # Inject section header when promotion changes
        if story_promo != current_promo:
            current_promo = story_promo
            for key, label, bg, color in _PROMO_SECTIONS:
                if key == story_promo:
                    stories_parts.append(
                        f'<div class="section-header" style="background:{bg};color:{color};">{label}</div>'
                    )
                    break

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
                anchor=f'story-{i}',
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
  .executive { background: #f0f4ff; border-left: 4px solid #4a6cf7; padding: 14px 16px; margin-bottom: 28px; border-radius: 4px; font-size: 16px; }
  .executive strong { display: block; margin-bottom: 6px; color: #1a1a2e; }
  .executive ul li { margin-bottom: 12px; }
  .tldr { font-size: 13px; font-style: italic; color: #555; border-left: 3px solid #ccc; padding-left: 10px; margin: 6px 0 10px; }
  #back-to-top { position: fixed; bottom: 28px; right: 24px; background: #1a1a2e; color: #fff; border: none; border-radius: 50%; width: 44px; height: 44px; font-size: 20px; cursor: pointer; box-shadow: 0 2px 8px rgba(0,0,0,.3); display: flex; align-items: center; justify-content: center; text-decoration: none; }
  #back-to-top:hover { background: #2d2d5e; }
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

    # Bullet list of TL;DRs — each links to its story anchor
    bullets = "".join(
        f'<li><a href="#story-{i}" style="color:#1a1a2e;text-decoration:none;">{_esc(s["tldr"])}</a></li>'
        for i, s in enumerate(digest) if s.get("tldr")
    )
    executive_block = f'<div class="executive"><strong>TL;DR</strong><ul>{bullets}</ul></div>' if bullets else ""

    stories_html = []
    for i, story in enumerate(digest):
        source_links = " · ".join(
            f'<a href="{s["url"]}" target="_blank">{_esc(s.get("source_name", "") or s.get("title", "")[:40])}</a>'
            for s in story["sources"] if s.get("url")
        )
        first_url = story["sources"][0]["url"] if story.get("sources") else "#"
        hot_label = "🔥 " if story.get("count", 0) >= 3 else ""
        stories_html.append(f"""
  <article id="story-{i}">
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
<a id="top"></a>
<a id="back-to-top" href="#top" title="Back to top">↑</a>
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
