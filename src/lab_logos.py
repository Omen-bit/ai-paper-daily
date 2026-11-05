"""
lab_logos.py
Each lab's own logo, in its own colours, saved once as a small square PNG in data/logos/.

Where a logo comes from, best first:
  1. the avatar the lab uploaded to its Hugging Face organization page
  2. Wikidata: its icon (P2910), logo (P154) or, for universities, seal (P158), whichever is closest
     to square, as a 128 px rendering from Wikimedia Commons. The Wikidata entry is found through
     ROR, the open registry of research organizations (exact for universities and institutes),
     else by an exact name or alias match on an organization
  3. the avatar of the lab's GitHub organization, when the paper's code lives there and the
     organization's name is the lab's name
  4. the app icon on the lab's official website (apple-touch-icon or a large icon), the site
     coming from ROR or Wikidata
  5. optional: Logo.dev, when LOGO_DEV_TOKEN is set (its free plan asks for a credit link)
A lab with none keeps the mark the site draws itself (Simple Icons outline or initials).
Every source is free to use without a key except Logo.dev; ROR and Wikidata are CC0.
Logos are trademarks of their owners and are shown only to say who wrote a paper.

paper_links.py calls refresh() once a day; the site builder reads index() and copies the files.
To fetch logos on their own:  python src/lab_logos.py
"""
import io
import json
import os
import re
from datetime import date

import requests

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SRC_DIR), "data")
LOGO_DIR = os.path.join(DATA_DIR, "logos")
INDEX_FILE = os.path.join(LOGO_DIR, "index.json")

USER_AGENT = "ai-paper-daily/1.0 (+https://github.com/Omen-bit/ai-paper-daily)"
TIMEOUT = 15
SIZE = 96            # pixels per side: sharp at the largest mark (40 px) on most phone screens
MAX_BYTES = 2_000_000
RETRY_DAYS = 30      # look again for labs where nothing was found
MAX_LOOKUPS = int(os.environ.get("LOGO_MAX_LOOKUPS", "60"))
# Wikidata properties, in order of preference when two images are equally square
PROPS = ("P2910", "P154", "P158")  # icon, logo image, seal image
# Bump to look every lab up again after a change in how logos are chosen
VERSION = 4  # 4: labs missed because the network failed are tried again


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s[:60] or "lab"


def load_index(path: str = INDEX_FILE) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_index(index: dict, path: str = INDEX_FILE) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1, sort_keys=True)


def index(path: str = INDEX_FILE) -> dict[str, str]:
    """{lab name: logo file name} for every lab with a saved logo."""
    out = {}
    for name, entry in load_index(path).items():
        file = (entry or {}).get("file")
        if file and os.path.exists(os.path.join(os.path.dirname(path), file)):
            out[name] = file
    return out


def _get_json(url: str, params: dict | None = None):
    r = requests.get(url, params=params, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def _download(url: str) -> bytes:
    r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    if not r.headers.get("Content-Type", "").startswith("image/") or len(r.content) > MAX_BYTES:
        raise ValueError(f"not a usable image: {r.headers.get('Content-Type')} {len(r.content)} bytes")
    return r.content


def to_square_png(raw: bytes, size: int = SIZE) -> bytes:
    """Fit the image inside a transparent square without cropping, as a small PNG."""
    from PIL import Image
    img = Image.open(io.BytesIO(raw))
    img.load()
    img = img.convert("RGBA")
    # Trim empty transparent edges so the logo fills its tile
    box = img.getchannel("A").getbbox()
    if box:
        img = img.crop(box)
    img.thumbnail((size, size), Image.LANCZOS)
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    tile.paste(img, ((size - img.width) // 2, (size - img.height) // 2), img)
    out = io.BytesIO()
    # A 256-colour palette keeps the logo's colours and makes the file a few KB
    tile.quantize(colors=256, method=Image.Quantize.FASTOCTREE).save(out, "PNG", optimize=True)
    return out.getvalue()


# --- Hugging Face ---------------------------------------------------------

def hf_avatar_url(avatar: str) -> str:
    """Hugging Face avatars are sometimes given as a path on huggingface.co."""
    if not avatar:
        return ""
    return avatar if avatar.startswith("http") else "https://huggingface.co" + ("" if avatar.startswith("/") else "/") + avatar


def is_uploaded_avatar(avatar: str) -> bool:
    """
    True for a logo the organization uploaded itself. An organization that never uploaded one gets a
    generated pattern from huggingface.co/avatars/..., which is not its logo, so it is skipped.
    """
    url = hf_avatar_url(avatar)
    return bool(url) and "/avatars/" not in url.split("?")[0].replace("cdn-avatars", "")


# --- Wikidata -------------------------------------------------------------

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"


ORG_WORDS = re.compile(r"\b(company|corporation|conglomerate|multinational|enterprise|manufacturer|developer|business|firm|"
                       r"subsidiary|startup|start-up|university|college|institute|institution|school|academy|laborator(y|ies)|"
                       r"lab|research|organi[sz]ation|foundation|agency|centre|center|group|platform|nonprofit|non-profit)\b")


def wikidata_entity(names: list[str]) -> str:
    """The Wikidata id whose label or alias is exactly one of the names, or ''. Exact matches only."""
    wanted = {n.strip().lower() for n in names if n and len(n.strip()) >= 3}
    for name in names:
        if not name or len(name.strip()) < 3:
            continue
        data = _get_json(WIKIDATA_API, {"action": "wbsearchentities", "search": name, "language": "en",
                                        "type": "item", "limit": 7, "format": "json"}) or {}
        for hit in data.get("search") or []:
            texts = [hit.get("label") or "", (hit.get("match") or {}).get("text") or ""] + (hit.get("aliases") or [])
            desc = (hit.get("description") or "").lower()
            # The description has to say it's an organization, so "Apple" never finds the fruit
            if any(t.strip().lower() in wanted for t in texts) and ORG_WORDS.search(desc):
                return hit["id"]
    return ""


def wikidata_images(qid: str) -> list[tuple[str, str]]:
    """(property, Commons file name) for the entity's icon, logo and seal, in that order."""
    data = _get_json(WIKIDATA_API, {"action": "wbgetentities", "ids": qid, "props": "claims", "format": "json"}) or {}
    claims = ((data.get("entities") or {}).get(qid) or {}).get("claims") or {}
    out = []
    for prop in PROPS:
        for claim in claims.get(prop) or []:
            if claim.get("rank") == "deprecated":
                continue
            value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
            if isinstance(value, str):
                out.append((prop, value))
                break
    return out


def commons_thumb(file_name: str, width: int = 128) -> tuple[str, float]:
    """A PNG rendering of a Commons file and its width/height ratio."""
    data = _get_json(COMMONS_API, {"action": "query", "titles": "File:" + file_name, "prop": "imageinfo",
                                   "iiprop": "size|mime", "iiurlwidth": width, "format": "json"}) or {}
    for page in ((data.get("query") or {}).get("pages") or {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        if info.get("thumburl") and info.get("width") and info.get("height"):
            return info["thumburl"], info["width"] / info["height"]
    return "", 0.0


def pick_wikidata(images: list[tuple[str, str]]) -> tuple[str, str]:
    """The (thumb URL, property) closest to square; a wide wordmark only when nothing else exists."""
    best, best_score = ("", ""), None
    for order, (prop, file_name) in enumerate(images):
        url, ratio = commons_thumb(file_name)
        if not url:
            continue
        # How far from square, with a small nudge towards the preferred property
        score = abs((ratio if ratio >= 1 else 1 / ratio) - 1) + order * 0.15
        if best_score is None or score < best_score:
            best, best_score = (url, prop), score
    return best


# --- Refresh --------------------------------------------------------------

def due(entry: dict | None, today: date) -> bool:
    if not entry:
        return True
    if entry.get("file") and entry.get("v", 0) >= 3:  # chosen by the current rules
        return False
    if entry.get("v") != VERSION:
        return True
    if entry.get("file"):
        return False
    try:
        return (today - date.fromisoformat(entry.get("checked") or "")).days >= RETRY_DAYS
    except ValueError:
        return True


# --- ROR (ror.org, CC0) ------------------------------------------------------

def ror_lookup(names: list[str]) -> tuple[str, str]:
    """(Wikidata id, website) of the ROR organization whose name, alias or acronym is exactly one of the names."""
    wanted = {n.strip().lower() for n in names if n and len(n.strip()) >= 3}
    for name in names:
        if not name or len(name.strip()) < 3:
            continue
        data = _get_json("https://api.ror.org/v2/organizations", {"query": name}) or {}
        for org in (data.get("items") or [])[:10]:
            texts = [n.get("value") or "" for n in org.get("names") or []]
            if not any(t.strip().lower() in wanted for t in texts):
                continue
            qid = ""
            for ext in org.get("external_ids") or []:
                if ext.get("type") == "wikidata":
                    qid = ext.get("preferred") or (ext.get("all") or [""])[0]
            site = next((l.get("value") for l in org.get("links") or [] if l.get("type") == "website"), "")
            return qid or "", site or ""
    return "", ""


def wikidata_website(qid: str) -> str:
    data = _get_json(WIKIDATA_API, {"action": "wbgetentities", "ids": qid, "props": "claims", "format": "json"}) or {}
    claims = ((data.get("entities") or {}).get(qid) or {}).get("claims") or {}
    for claim in claims.get("P856") or []:
        value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(value, str) and value.startswith("http"):
            return value
    return ""


# --- GitHub organization ---------------------------------------------------

def github_avatar(owners: list[str], names: list[str]) -> str:
    """The avatar of a GitHub organization among the paper's code owners whose name is the lab's name."""
    wanted = {re.sub(r"[^a-z0-9]", "", n.lower()) for n in names if n}
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    for owner in owners[:5]:
        r = requests.get(f"https://api.github.com/users/{owner}", timeout=TIMEOUT, headers=headers)
        if r.status_code != 200:
            continue
        data = r.json()
        names_here = {re.sub(r"[^a-z0-9]", "", (data.get(k) or "").lower()) for k in ("login", "name")}
        if data.get("type") == "Organization" and names_here & wanted and data.get("avatar_url"):
            return data["avatar_url"] + ("&" if "?" in data["avatar_url"] else "?") + "s=128"
    return ""


# --- The lab's own website ------------------------------------------------

_LINK_TAG = re.compile(r"<link\b[^>]*>", re.I)
_ATTR = re.compile(r'([a-zA-Z-]+)\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)')


def site_icon_urls(page_url: str, html: str) -> list[str]:
    """Icon links in a page, best first: apple-touch-icon, then the largest declared icon. SVG is skipped."""
    from urllib.parse import urljoin
    found = []
    for tag in _LINK_TAG.findall(html[:200_000]):
        attrs = {k.lower(): v.strip("\"'") for k, v in _ATTR.findall(tag)}
        rel, href = attrs.get("rel", "").lower(), attrs.get("href", "")
        if "icon" not in rel or not href or href.lower().split("?")[0].endswith(".svg"):
            continue
        sizes = [int(n) for n in re.findall(r"(\d+)x\d+", attrs.get("sizes", ""))] or [0]
        rank = (1 if "apple-touch-icon" in rel else 0, max(sizes))
        found.append((rank, urljoin(page_url, href)))
    found.sort(key=lambda x: x[0], reverse=True)
    urls = [u for _, u in found]
    for path in ("/apple-touch-icon.png", "/favicon.ico"):
        urls.append(urljoin(page_url, path))
    return urls


def website_icon(site: str) -> bytes:
    """The website's own app icon as a square PNG, when one at least 48 px wide exists."""
    from PIL import Image
    r = requests.get(site, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    for url in site_icon_urls(r.url, r.text)[:6]:
        try:
            raw = _download(url)
            img = Image.open(io.BytesIO(raw))
            if hasattr(img, "ico"):  # an .ico holds several sizes; use the largest
                img.size = max(img.ico.sizes())
            if min(img.size) >= 48:
                out = io.BytesIO()
                img.convert("RGBA").save(out, "PNG")
                return to_square_png(out.getvalue())
        except Exception:
            continue
    return b""


def logo_dev(site: str) -> bytes:
    """Logo.dev, only when LOGO_DEV_TOKEN is set."""
    token = os.environ.get("LOGO_DEV_TOKEN")
    if not token or not site:
        return b""
    from urllib.parse import urlparse
    domain = urlparse(site).netloc.removeprefix("www.")
    return to_square_png(_download(f"https://img.logo.dev/{domain}?token={token}&size=128&format=png"))


def find_logo(lab: str, aliases: list[str], avatar: str = "", owners: list[str] = ()) -> tuple[bytes, str]:
    """(PNG bytes, where it came from) for a lab, or (b'', '') when no official logo was found."""
    names = [lab] + aliases
    errors = []

    def attempt(label, fn):
        try:
            return fn()
        except Exception as exc:
            if isinstance(exc, requests.exceptions.RequestException):
                errors.append(label)
            print(f"  [logos] {label} failed for {lab}: {type(exc).__name__}: {str(exc)[:100]}")
            return None

    if avatar and is_uploaded_avatar(avatar):
        png = attempt("Hugging Face", lambda: to_square_png(_download(hf_avatar_url(avatar))))
        if png:
            return png, "Hugging Face"
    qid, site = attempt("ROR", lambda: ror_lookup(names)) or ("", "")
    qid = qid or attempt("Wikidata search", lambda: wikidata_entity(names)) or ""
    if qid:
        url, prop = attempt("Wikidata images", lambda: pick_wikidata(wikidata_images(qid))) or ("", "")
        if url:
            png = attempt("Wikimedia download", lambda: to_square_png(_download(url)))
            if png:
                return png, f"Wikidata {qid} {prop}"
        site = site or attempt("Wikidata website", lambda: wikidata_website(qid)) or ""
    if owners:
        url = attempt("GitHub", lambda: github_avatar(list(owners), names))
        if url:
            png = attempt("GitHub download", lambda: to_square_png(_download(url)))
            if png:
                return png, "GitHub"
    if site:
        png = attempt("website icon", lambda: website_icon(site))
        if png:
            return png, f"website {site}"
        png = attempt("Logo.dev", lambda: logo_dev(site))
        if png:
            return png, "Logo.dev"
    if errors:
        # The network failed somewhere, so "no logo" isn't known yet: try again on the next run
        raise ConnectionError("lookups failed: " + ", ".join(errors))
    return b"", ""


def refresh(labs_seen: dict[str, str], today: date | None = None, max_lookups: int = MAX_LOOKUPS,
            logo_dir: str = LOGO_DIR) -> int:
    """
    labs_seen maps each lab on the site to a Hugging Face avatar URL (or '').
    Looks up labs without a logo, most recent first as given. Returns how many were looked up.
    """
    import labs as lab_names
    today = today or date.today()
    path = os.path.join(logo_dir, "index.json")
    idx = load_index(path)
    done = 0
    for lab, hint in labs_seen.items():
        # hint: a Hugging Face avatar URL, or {"avatar": ..., "github": [owners of the papers' code]}
        avatar, owners = (hint.get("avatar") or "", hint.get("github") or []) if isinstance(hint, dict) else (hint or "", [])
        if done >= max_lookups:
            break
        if not due(idx.get(lab), today):
            continue
        aliases = [a for a in lab_names.LABS.get(lab, []) if len(a) >= 4 and not re.fullmatch(r"[a-z0-9\-]+", a)]
        entry = {"checked": today.isoformat(), "v": VERSION}
        try:
            png, source = find_logo(lab, aliases, avatar, owners)
            if png:
                file = slug(lab) + ".png"
                os.makedirs(logo_dir, exist_ok=True)
                with open(os.path.join(logo_dir, file), "wb") as f:
                    f.write(png)
                entry.update(file=file, source=source)
            else:
                old = os.path.join(logo_dir, slug(lab) + ".png")
                if os.path.exists(old):
                    os.remove(old)  # a logo chosen by an older rule that no longer qualifies
                print(f"  [logos] No official logo found for {lab}")
        except Exception as exc:
            print(f"  [logos] Lookup failed for {lab}: {str(exc)[:100]}")
            entry = dict(idx.get(lab) or {})  # try again next run
        idx[lab] = entry
        done += 1
    save_index(idx, path)
    return done


if __name__ == "__main__":
    import sys
    sys.path.insert(0, SRC_DIR)
    import paper_links
    import site_builder
    _papers = site_builder.merge_papers(site_builder.load_days(DATA_DIR))
    paper_links.refresh_logos(_papers, paper_links.load(), max_lookups=1000)
