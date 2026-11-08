"""
case_logos.py
Logos for the companies on the Case studies pages that have no drawn logo in case_brands.json.

For each of those companies this fetches the icon the company publishes on its own website
(the apple-touch-icon or the largest icon its home page links to) and saves it as
data/case_logos/<key>.png, which the daily workflow commits with the rest of data/.
An icon smaller than MIN_SIZE is not used, so a card never shows a blurry favicon: it keeps the
company's initial on its brand colour instead. A company whose icon could not be fetched is tried
again after RETRY_DAYS.

case_studies.run() calls fetch_missing(); case_pages.logo() uses the saved files.
"""
import io
import json
import os
import re
from datetime import date, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_DIR = os.path.join(os.path.dirname(SRC_DIR), "data", "case_logos")
MIN_SIZE = 96       # pixels; smaller icons look blurry on the cards
SAVE_SIZE = 256
RETRY_DAYS = 30
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0 Safari/537.36 AIPapersDaily/1.0")

# The company's main website, where its icon lives (its blog is often on Medium or a subdomain)
SITES = {
    "Capital One": "https://www.capitalone.com/",
    "Myntra": "https://www.myntra.com/",
    "Meesho": "https://www.meesho.com/",
    "Mercado Libre": "https://www.mercadolibre.com/",
    "Coupang": "https://www.coupang.com/",
    "Faire": "https://www.faire.com/",
    "OLX": "https://www.olx.com/",
    "Delivery Hero": "https://www.deliveryhero.com/",
    "Agoda": "https://www.agoda.com/",
    "JioHotstar": "https://www.hotstar.com/",
    "Honeycomb": "https://www.honeycomb.io/",
}


def key(company: str) -> str:
    return re.sub(r"[^a-z0-9]", "", company.lower())


def saved_file(company: str, logo_dir: str = LOGO_DIR) -> str:
    """The saved logo's file name for this company, or '' when there is none."""
    name = f"{key(company)}.png"
    return name if os.path.isfile(os.path.join(logo_dir, name)) else ""


class _Icons(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found: list[tuple[int, str]] = []

    def handle_starttag(self, tag, attrs):
        if tag != "link":
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        rel = a.get("rel", "").lower()
        if "icon" not in rel or "mask-icon" in rel or not a.get("href"):
            return
        if a["href"].lower().split("?")[0].endswith(".svg"):
            return  # Pillow cannot read SVG; the PNG icons are enough
        sizes = [int(n) for n in re.findall(r"(\d+)x\d+", a.get("sizes", ""))]
        size = max(sizes) if sizes else (180 if "apple-touch-icon" in rel else 32)
        self.found.append((size, a["href"]))


def icon_links(page_html: str, base: str) -> list[str]:
    """Icon urls from a home page, largest first, then the usual /apple-touch-icon.png."""
    parser = _Icons()
    try:
        parser.feed(page_html or "")
    except Exception:
        pass
    urls = [urljoin(base, href) for _, href in sorted(parser.found, key=lambda x: -x[0])]
    for fallback in ("/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"):
        url = urljoin(base, fallback)
        if url not in urls:
            urls.append(url)
    return urls


def to_png(data: bytes) -> bytes | None:
    """The icon as a square SAVE_SIZE PNG, or None when it is not an image or is too small."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        if img.format == "ICO":
            img.size = max(img.ico.sizes())  # the largest picture inside the .ico
        img = img.convert("RGBA")
    except Exception:
        return None
    if min(img.size) < MIN_SIZE:
        return None
    side = max(img.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
    out = io.BytesIO()
    square.resize((SAVE_SIZE, SAVE_SIZE), Image.LANCZOS).save(out, "PNG", optimize=True)
    return out.getvalue()


def fetch_one(company: str, site: str, get) -> bytes | None:
    """The company's icon as PNG bytes, trying each icon its home page links to."""
    try:
        page = get(site)
        page_html = page.text if page is not None and page.status_code == 200 else ""
    except Exception:
        page_html = ""
    for url in icon_links(page_html, site)[:6]:
        try:
            r = get(url)
        except Exception:
            continue
        if r is None or r.status_code != 200 or len(r.content) < 400:
            continue
        png = to_png(r.content)
        if png:
            return png
    return None


def fetch_missing(companies, logo_dir: str = LOGO_DIR, today: date | None = None, get=None) -> int:
    """Fetch an icon for each company in SITES that has none saved. Returns how many were saved."""
    today = today or date.today()
    if get is None:
        import requests
        session = requests.Session()
        session.headers["User-Agent"] = USER_AGENT

        def get(url):
            return session.get(url, timeout=15, allow_redirects=True)
    os.makedirs(logo_dir, exist_ok=True)
    tried_path = os.path.join(logo_dir, "tried.json")
    try:
        with open(tried_path, encoding="utf-8") as f:
            tried = json.load(f)
    except (OSError, ValueError):
        tried = {}
    saved = 0
    for company in sorted(set(companies)):
        site = SITES.get(company)
        if not site or saved_file(company, logo_dir):
            continue
        last = tried.get(company, "")
        if last and last > (today - timedelta(days=RETRY_DAYS)).isoformat():
            continue
        png = fetch_one(company, site, get)
        if png:
            with open(os.path.join(logo_dir, f"{key(company)}.png"), "wb") as f:
                f.write(png)
            tried.pop(company, None)
            saved += 1
            print(f"  [cases] Saved the logo for {company}")
        else:
            tried[company] = today.isoformat()
            print(f"  [cases] No usable logo found for {company}; it keeps its initial for now")
    with open(tried_path, "w", encoding="utf-8") as f:
        json.dump(tried, f, indent=1, sort_keys=True)
    return saved
