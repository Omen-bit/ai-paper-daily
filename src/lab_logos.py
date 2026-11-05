"""
lab_logos.py
Each lab's own logo, in its own colours, saved once as a small square PNG in data/logos/.

Where a logo comes from, best first:
  1. the avatar the lab uploaded to its Hugging Face organization page
  2. Wikidata, for the entity whose name or alias is exactly the lab's name:
     its icon (P2910), logo (P154) or, for universities, seal (P158), whichever is closest to square,
     downloaded as a 128 px rendering from Wikimedia Commons
A lab with neither keeps the mark the site draws itself (Simple Icons outline or initials).
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
VERSION = 2


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
    if not entry or entry.get("v") != VERSION:
        return True
    if entry.get("file"):
        return False
    try:
        return (today - date.fromisoformat(entry.get("checked") or "")).days >= RETRY_DAYS
    except ValueError:
        return True


def find_logo(lab: str, aliases: list[str], avatar: str = "") -> tuple[bytes, str]:
    """(PNG bytes, where it came from) for a lab, or (b'', '') when no official logo was found."""
    if avatar and is_uploaded_avatar(avatar):
        try:
            return to_square_png(_download(hf_avatar_url(avatar))), "Hugging Face"
        except Exception as exc:
            print(f"  [logos] Hugging Face avatar failed for {lab}: {str(exc)[:100]}")
    qid = wikidata_entity([lab] + aliases)
    if qid:
        url, prop = pick_wikidata(wikidata_images(qid))
        if url:
            return to_square_png(_download(url)), f"Wikidata {qid} {prop}"
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
    for lab, avatar in labs_seen.items():
        if done >= max_lookups:
            break
        if not due(idx.get(lab), today):
            continue
        aliases = [a for a in lab_names.LABS.get(lab, []) if len(a) >= 4 and not re.fullmatch(r"[a-z0-9\-]+", a)]
        entry = {"checked": today.isoformat(), "v": VERSION}
        try:
            png, source = find_logo(lab, aliases, avatar)
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
