"""
labs.py
Which lab or company a paper comes from, from evidence that names it directly:
  1. the organization that claimed the paper on Hugging Face Papers
  2. the owner of the paper's GitHub code (github.com/google-deepmind/... -> Google DeepMind)
  3. the arXiv comment or affiliation field ("Work done at Meta FAIR")
  4. the authors' institutions on OpenAlex, most common first

The abstract is never used: papers name other labs' models all the time
("we compare with OpenAI's GPT-4o"), which says nothing about who wrote them.
Every match is exact (whole names, not fragments), so a wrong lab is rarer than a missing one.
"""
import re
from collections import Counter

# Display name -> the names it goes by: Hugging Face org ids, GitHub owners and written names.
# Lowercase, matched as whole words.
LABS = {
    "Google DeepMind": ["google deepmind", "deepmind", "google-deepmind", "googledeepmind"],
    "Google": ["google", "google research", "google-research", "googleresearch", "google brain",
               "google cloud ai research", "googlecloudplatform"],
    "OpenAI": ["openai"],
    "Anthropic": ["anthropic", "anthropics", "anthropicai"],
    "Meta": ["meta", "meta ai", "meta fair", "fair", "facebook ai research", "facebookresearch",
             "facebook", "meta-llama", "meta platforms", "meta superintelligence labs"],
    "Microsoft": ["microsoft", "microsoft research", "msft", "microsoft research asia", "azure"],
    "NVIDIA": ["nvidia", "nvlabs", "nvidia research", "nvidia corporation", "nv-tlabs"],
    "Apple": ["apple", "apple inc", "apple machine learning research"],
    "Amazon": ["amazon", "amazon science", "amazon-science", "aws", "amazon web services", "amazon agi"],
    "Hugging Face": ["hugging face", "huggingface", "huggingfacetb", "huggingfacem4"],
    "Ai2": ["ai2", "allenai", "allen institute for ai", "allen institute for artificial intelligence"],
    "Mistral AI": ["mistral ai", "mistralai"],
    "Alibaba Qwen": ["qwen", "qwenlm", "qwen team"],
    "Alibaba": ["alibaba", "alibaba group", "alibaba-nlp", "alibaba cloud", "damo academy",
                "alibaba damo academy", "modelscope", "alibaba-damo-academy", "tongyi lab"],
    "DeepSeek": ["deepseek", "deepseek-ai", "deepseek ai"],
    "ByteDance": ["bytedance", "bytedance seed", "bytedance-seed", "bytedance research", "bytedance inc"],
    "Tencent": ["tencent", "tencent ai lab", "tencent hunyuan", "tencent-hunyuan", "tencentarc",
                "tencent arc lab", "tencent youtu lab"],
    "Baidu": ["baidu", "baidu inc", "paddlepaddle", "baidu research"],
    "Huawei": ["huawei", "huawei noah's ark lab", "huawei-noah", "huawei technologies"],
    "Moonshot AI": ["moonshot ai", "moonshotai", "kimi"],
    "Zhipu AI": ["zhipu ai", "zai-org", "z.ai", "thudm", "zhipu"],
    "MiniMax": ["minimax", "minimaxai", "minimax-ai"],
    "Shanghai AI Lab": ["shanghai ai laboratory", "shanghai ai lab", "opengvlab", "internlm",
                        "shanghai artificial intelligence laboratory"],
    "Samsung": ["samsung", "samsung research", "samsung ai center", "samsung electronics"],
    "Salesforce": ["salesforce", "salesforce research", "salesforce ai research", "salesforceairesearch"],
    "IBM": ["ibm", "ibm research", "ibm-granite", "ibm granite"],
    "Adobe": ["adobe", "adobe research"],
    "Sony": ["sony", "sony ai", "sony research"],
    "Xiaomi": ["xiaomi", "xiaomimimo", "xiaomi mimo"],
    "Kuaishou": ["kuaishou", "kwai", "kwaivgi", "kwai-kolors", "kuaishou technology"],
    "Meituan": ["meituan", "meituan-longcat", "longcat"],
    "StepFun": ["stepfun", "stepfun-ai"],
    "Ant Group": ["ant group", "inclusionai", "antgroup", "ant research"],
    "LG AI Research": ["lg ai research", "lgai-exaone", "lg ai"],
    "NAVER": ["naver", "naver ai lab", "naver cloud", "naver-ai", "naver labs europe"],
    "Cohere": ["cohere", "cohereforai", "cohere for ai", "cohere labs", "coherelabs"],
    "Stability AI": ["stability ai", "stabilityai", "stability-ai"],
    "xAI": ["xai", "xai-org"],
    "Snowflake": ["snowflake"],
    "Intel": ["intel", "intel labs", "intel corporation", "intellabs"],
    "Databricks": ["databricks", "mosaicml"],
    "Together AI": ["together ai", "togethercomputer", "together computer"],
    "Stanford": ["stanford", "stanford university", "stanford-crfm", "stanfordnlp", "hazyresearch"],
    "MIT": ["mit", "massachusetts institute of technology", "mit-han-lab", "mit csail", "csail"],
    "UC Berkeley": ["uc berkeley", "berkeley", "university of california, berkeley",
                    "university of california berkeley", "berkeley-ai-research", "bair"],
    "Carnegie Mellon": ["carnegie mellon university", "cmu", "carnegie mellon", "cmu-lti"],
    "Princeton": ["princeton university", "princeton-nlp", "princeton-pli", "princeton"],
    "Harvard": ["harvard university", "harvard"],
    "University of Washington": ["university of washington", "uwnlp"],
    "NYU": ["new york university", "nyu"],
    "Oxford": ["university of oxford", "oxford"],
    "Cambridge": ["university of cambridge"],
    "ETH Zurich": ["eth zurich", "eth zürich", "eth-zurich"],
    "EPFL": ["epfl", "école polytechnique fédérale de lausanne", "epfl-vilab"],
    "Mila": ["mila", "mila - quebec ai institute", "mila quebec"],
    "University of Toronto": ["university of toronto"],
    "Tsinghua University": ["tsinghua university", "tsinghua", "thu-ml", "thunlp"],
    "Peking University": ["peking university", "pku", "pku-alignment", "pku-yuangroup"],
    "Shanghai Jiao Tong University": ["shanghai jiao tong university", "sjtu"],
    "Zhejiang University": ["zhejiang university", "zju"],
    "Fudan University": ["fudan university", "fudan", "openmoss"],
    "CUHK": ["the chinese university of hong kong", "chinese university of hong kong", "cuhk"],
    "HKUST": ["hong kong university of science and technology", "hkust"],
    "HKU": ["university of hong kong", "the university of hong kong", "hku", "hkunlp", "hkuds"],
    "NTU Singapore": ["nanyang technological university", "ntu singapore"],
    "NUS": ["national university of singapore", "nus"],
    "KAIST": ["kaist", "korea advanced institute of science and technology"],
    "Renmin University": ["renmin university of china", "rucaibox"],
    "USTC": ["university of science and technology of china", "ustc"],
}

# How each lab's mark looks: (Simple Icons logo id or "" for initials, official brand colour).
# Logos come from Simple Icons (simple-icons.org) and sit in site_assets/labs.svg; labs without
# a published logo there get their initials on their official colour instead.
BRANDS = {
    "Google DeepMind": ("deepmind", "4285F4"), "Google": ("google", "4285F4"),
    "OpenAI": ("", "000000"), "Anthropic": ("anthropic", "191919"), "Meta": ("meta", "0467DF"),
    "Microsoft": ("", "0078D4"), "NVIDIA": ("nvidia", "76B900"), "Apple": ("apple", "000000"),
    "Amazon": ("", "FF9900"), "Hugging Face": ("huggingface", "FFD21E"), "Ai2": ("", "F0529C"),
    "Mistral AI": ("mistralai", "FA520F"), "Alibaba Qwen": ("qwen", "6950EF"),
    "Alibaba": ("alibabacloud", "FF6A00"), "DeepSeek": ("deepseek", "4D6BFE"),
    "ByteDance": ("bytedance", "3C8CFF"), "Tencent": ("", "0052D9"), "Baidu": ("baidu", "2932E1"),
    "Huawei": ("huawei", "FF0000"), "Moonshot AI": ("moonshotai", "000000"), "Zhipu AI": ("", "3859FF"),
    "MiniMax": ("minimax", "E73562"), "Shanghai AI Lab": ("", "0052A4"), "Samsung": ("samsung", "1428A0"),
    "Salesforce": ("", "00A1E0"), "IBM": ("", "0F62FE"), "Adobe": ("", "FA0F00"), "Sony": ("sony", "000000"),
    "Xiaomi": ("xiaomi", "FF6900"), "Kuaishou": ("kuaishou", "FF4906"), "Meituan": ("meituan", "FFD100"),
    "StepFun": ("", "005AFF"), "Ant Group": ("", "1677FF"), "LG AI Research": ("lg", "A50034"),
    "NAVER": ("naver", "03C75A"), "Cohere": ("", "39594D"), "Stability AI": ("", "000000"),
    "xAI": ("", "000000"), "Snowflake": ("snowflake", "29B5E8"), "Databricks": ("databricks", "FF3621"),
    "Intel": ("intel", "0071C5"), "Together AI": ("", "0F6FFF"),
    # Universities: their official identity colours
    "Stanford": ("", "8C1515"), "MIT": ("", "A31F34"), "UC Berkeley": ("", "002676"),
    "Carnegie Mellon": ("", "C41230"), "Princeton": ("", "E77500"), "Harvard": ("", "A51C30"),
    "University of Washington": ("", "4B2E83"), "NYU": ("", "57068C"), "Oxford": ("", "002147"),
    "Cambridge": ("", "0072CF"), "ETH Zurich": ("", "215CAF"), "EPFL": ("", "FF0000"), "Mila": ("", "1B1B1B"),
    "University of Toronto": ("", "1E3765"), "Tsinghua University": ("", "660874"),
    "Peking University": ("", "8F0E1A"), "Shanghai Jiao Tong University": ("", "C8161E"),
    "Zhejiang University": ("", "003F88"), "Fudan University": ("", "0E419C"), "CUHK": ("", "6F2C91"),
    "HKUST": ("", "003366"), "HKU": ("", "1E5B3A"), "NTU Singapore": ("", "181C62"), "NUS": ("", "003D7C"),
    "KAIST": ("", "004191"), "Renmin University": ("", "AE0B2A"), "USTC": ("", "0A3D91"),
}


def brand(name: str) -> tuple[str, str]:
    """(logo id or '', brand colour as hex without #) for a lab; unknown labs get ('', '')."""
    return BRANDS.get(name, ("", ""))


def initials(name: str) -> str:
    """A short mark for a lab without a logo: 'MIT' stays, 'OpenAI' -> 'OA', 'Tsinghua University' -> 'TU'."""
    words = re.sub(r"[^A-Za-z0-9 ]", "", name or "").split()
    if not words:
        return ""
    if len(words) == 1 and len(words[0]) <= 4:
        return words[0]
    if len(words) == 1:
        caps = "".join(c for c in words[0] if c.isupper())
        return caps[:2] if len(caps) >= 2 else words[0][0].upper()
    return "".join(w[0] for w in words[:2]).upper()


def ink_on(hex_colour: str) -> str:
    """Dark text on light brand colours (Hugging Face yellow), white on the rest."""
    try:
        r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except (ValueError, IndexError):
        return "fff"
    lum = sum(w * (c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4) for w, c in zip((.2126, .7152, .0722), (r, g, b)))
    return "1a1a1a" if lum > .45 else "fff"


# Short or common names that only count when written with these exact capitals in free text
# ("fair evaluation" is not Meta, "MIT license" is handled below).
_CASED = {"fair": "FAIR", "mit": "MIT", "meta": "Meta", "apple": "Apple", "amazon": "Amazon",
          "berkeley": "Berkeley", "oxford": "Oxford", "princeton": "Princeton", "harvard": "Harvard",
          "kimi": "Kimi", "aws": "AWS", "nyu": "NYU", "bair": "BAIR", "csail": "CSAIL", "nus": "NUS",
          "pku": "PKU", "zju": "ZJU", "sjtu": "SJTU", "ustc": "USTC", "hku": "HKU", "cmu": "CMU",
          "ibm": "IBM", "ai2": "Ai2", "xai": "xAI", "mila": "Mila", "sony": "Sony", "google": "Google",
          "naver": "NAVER", "azure": "Azure", "qwen": "Qwen", "fudan": "Fudan", "tsinghua": "Tsinghua",
          "stanford": "Stanford", "facebook": "Facebook", "minimax": "MiniMax", "longcat": "LongCat",
          "kwai": "Kwai", "msft": "MSFT", "zhipu": "Zhipu", "cohere": "Cohere", "snowflake": "Snowflake"}

_ALIAS = {alias: name for name, aliases in LABS.items() for alias in aliases}
for _name in LABS:
    _ALIAS.setdefault(_name.lower(), _name)
# Longest first, so "Google DeepMind" wins over "Google"
_BY_LENGTH = sorted(_ALIAS, key=len, reverse=True)
# Things a comment says that contain a lab name but aren't the lab
_NOT_A_LAB = re.compile(r"\bMIT\s+licen[sc]e\b|\bApache\b", re.I)


def canonical(name: str) -> str:
    """A known lab's display name for an exact alias, or '' when it isn't one we know."""
    key = " ".join((name or "").lower().replace("_", "-").split())
    key = re.sub(r"\s*\([^)]*\)$", "", key)  # "Google (United States)" -> "google"
    return _ALIAS.get(key, "")


def _clean(name: str) -> str:
    name = re.sub(r"\s*\([^)]*\)$", "", " ".join((name or "").split()))
    return name.strip(" ,;")


def from_hf_org(org) -> str:
    """The organization that claimed the paper on Hugging Face, as {'name', 'fullname'} or a string."""
    if not org:
        return ""
    if isinstance(org, str):
        return canonical(org) or _clean(org)
    if not isinstance(org, dict):
        return ""
    for key in ("name", "fullname"):
        hit = canonical(org.get(key) or "")
        if hit:
            return hit
    return _clean(org.get("fullname") or org.get("name") or "")


def from_code_url(url: str) -> str:
    """The lab that owns the repository, only when the owner is a known lab account."""
    m = re.search(r"(?:github|gitlab)\.com/([\w.\-]+)/", url or "", re.I)
    return canonical(m.group(1)) if m else ""


def from_text(text: str) -> str:
    """A known lab named in an arXiv comment or affiliation field, matched as a whole name."""
    text = _NOT_A_LAB.sub(" ", " ".join((text or "").split()))
    if not text:
        return ""
    lower = text.lower()
    for alias in _BY_LENGTH:
        if len(alias) < 3 and alias not in _CASED:
            continue
        pattern = rf"(?<![\w\-]){re.escape(alias)}(?![\w\-])"
        if alias in _CASED:
            if re.search(rf"(?<![\w\-]){re.escape(_CASED[alias])}(?![\w\-])", text):
                return _ALIAS[alias]
        elif re.search(pattern, lower):
            return _ALIAS[alias]
    return ""


def from_institutions(names: list[str]) -> str:
    """
    The authors' most common institution (OpenAlex lists one or more per author).
    Known labs win ties, and a known lab with at least as many authors beats an unknown one.
    """
    counts = Counter()
    for raw in names or []:
        name = canonical(raw) or _clean(raw)
        if name:
            counts[name] += 1
    if not counts:
        return ""
    return max(counts, key=lambda n: (counts[n], bool(canonical(n)), -len(n)))


def openalex_institutions(work: dict) -> list[str]:
    """Each author's first institution name from an OpenAlex work."""
    out = []
    for a in (work or {}).get("authorships") or []:
        insts = a.get("institutions") or []
        if insts and insts[0].get("display_name"):
            out.append(insts[0]["display_name"])
    return out


def detect(paper: dict) -> str:
    """The lab for a pipeline paper from what the fetchers saw, or ''."""
    return (from_hf_org(paper.get("hf_org"))
            or from_code_url(paper.get("code_url") or paper.get("github_repo") or "")
            or from_text(paper.get("arxiv_affiliation") or "")
            or from_text(paper.get("arxiv_comment") or ""))
