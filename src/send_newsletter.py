"""Send today's edition as an email through Buttondown's API (free plan).

Buttondown's RSS-to-email is a paid add-on, but its email API is free. After
the site is built, this reads today's items from site/feed.xml and creates one
email with them. A marker file in data/newsletter/ makes sure each day is sent
only once, even if the workflow is run again by hand.

Environment:
  BUTTONDOWN_API_KEY   required; without it the script does nothing.
  BUTTONDOWN_SEND      "draft" to only create a draft (default: send now).
"""
import json
import os
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEED_PATH = os.path.join(ROOT_DIR, "site", "feed.xml")
MARKER_DIR = os.path.join(ROOT_DIR, "data", "newsletter")
API_URL = "https://api.buttondown.com/v1/emails"
SITE_NAME = "AI Papers Daily"


def todays_items(feed_xml: str, day: str) -> list[dict]:
    """Return the feed items whose pubDate falls on `day` (YYYY-MM-DD, UTC)."""
    items = []
    for item in ET.fromstring(feed_xml).iter("item"):
        pub = item.findtext("pubDate") or ""
        try:
            pub_day = parsedate_to_datetime(pub).strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            continue
        if pub_day == day:
            items.append({
                "title": (item.findtext("title") or "").strip(),
                "link": (item.findtext("link") or "").strip(),
                "description": (item.findtext("description") or "").strip(),
            })
    return items


def build_email(items: list[dict], day: str) -> dict:
    """Subject and body for the day's email. The body is HTML, which Buttondown accepts."""
    nice_day = datetime.strptime(day, "%Y-%m-%d").strftime("%A, %d %B %Y")
    lead = items[0]["title"].split(": ", 1)[-1] if items else ""
    subject = f"{lead}" if lead else f"{SITE_NAME}, {nice_day}"
    parts = [f"<p><em>{SITE_NAME} · {nice_day}</em></p>"]
    for it in items:
        link = it["link"].replace("ref=rss", "ref=email")
        parts.append(f'<h2><a href="{link}">{it["title"]}</a></h2>')
        parts.append(it["description"].replace("ref=rss", "ref=email"))
    return {"subject": subject, "body": "\n".join(parts)}


def post_email(api_key: str, payload: dict) -> dict:
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Authorization": f"Token {api_key}",
            "Content-Type": "application/json",
            # Required by Buttondown the first time a key sends for real.
            "X-Buttondown-Live-Dangerously": "true",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode() or "{}")


def main(day: str | None = None) -> int:
    api_key = os.environ.get("BUTTONDOWN_API_KEY", "").strip()
    if not api_key:
        print("BUTTONDOWN_API_KEY is not set; skipping the email.")
        return 0
    day = day or datetime.now().strftime("%Y-%m-%d")
    marker = os.path.join(MARKER_DIR, f"{day}.json")
    if os.path.exists(marker):
        print(f"The email for {day} was already sent; skipping.")
        return 0
    with open(FEED_PATH, encoding="utf-8") as f:
        items = todays_items(f.read(), day)
    if not items:
        print(f"No feed items for {day}; nothing to send.")
        return 0

    email = build_email(items, day)
    mode = "draft" if os.environ.get("BUTTONDOWN_SEND", "").strip().lower() == "draft" else "about_to_send"
    try:
        result = post_email(api_key, {**email, "status": mode})
    except urllib.error.HTTPError as e:
        print(f"Buttondown refused the email ({e.code}): {e.read().decode(errors='replace')}")
        return 1
    os.makedirs(MARKER_DIR, exist_ok=True)
    with open(marker, "w", encoding="utf-8") as f:
        json.dump({"id": result.get("id"), "subject": email["subject"], "status": mode}, f, indent=2)
    print(f"Buttondown email created ({mode}): {email['subject']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
