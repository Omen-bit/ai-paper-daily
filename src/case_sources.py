"""
case_sources.py
The company engineering blogs behind the Case studies pages, and the map they are sorted onto.

Each problem is a line on the map and each step is a stop. Serving and Evaluation are shared
by every line, and Feature pipelines by the lines that rank things, so a post about one of
those steps shows on every line that shares it.
"""

# (name, RSS or Atom feed, blog home, Simple Icons slug or "", brand colour without #)
SOURCES = [
    ("Meta", "https://engineering.fb.com/feed/", "https://engineering.fb.com/", "meta", "0467DF"),
    ("Netflix", "https://netflixtechblog.com/feed", "https://netflixtechblog.com/", "netflix", "E50914"),
    ("Google", "https://research.google/blog/rss/", "https://research.google/blog/", "google", "4285F4"),
    ("Pinterest", "https://medium.com/feed/pinterest-engineering", "https://medium.com/pinterest-engineering", "pinterest", "BD081C"),
    ("Spotify", "https://engineering.atspotify.com/feed/", "https://engineering.atspotify.com/", "spotify", "1ED760"),
    ("Airbnb", "https://medium.com/feed/airbnb-engineering", "https://medium.com/airbnb-engineering", "airbnb", "FF5A5F"),
    ("Uber", "https://www.uber.com/blog/engineering/rss/", "https://www.uber.com/blog/engineering/", "uber", "000000"),
    ("DoorDash", "https://careersatdoordash.com/feed/", "https://careersatdoordash.com/engineering-blog/", "doordash", "FF3008"),
    ("Shopify", "https://shopify.engineering/blog.atom", "https://shopify.engineering/", "shopify", "7AB55C"),
    ("LinkedIn", "https://www.linkedin.com/blog/engineering/feed", "https://www.linkedin.com/blog/engineering", "linkedin", "0A66C2"),
    ("Dropbox", "https://dropbox.tech/feed", "https://dropbox.tech/", "dropbox", "0061FF"),
    ("Amazon", "https://www.amazon.science/index.rss", "https://www.amazon.science/", "amazon", "FF9900"),
    ("Apple", "https://machinelearning.apple.com/rss.xml", "https://machinelearning.apple.com/", "apple", "000000"),
    ("NVIDIA", "https://developer.nvidia.com/blog/feed", "https://developer.nvidia.com/blog/", "nvidia", "76B900"),
    ("Instacart", "https://tech.instacart.com/feed", "https://tech.instacart.com/", "instacart", "43B02A"),
    ("Slack", "https://slack.engineering/feed/", "https://slack.engineering/", "slack", "4A154B"),
    ("GitHub", "https://github.blog/engineering/feed/", "https://github.blog/engineering/", "github", "181717"),
    ("Stripe", "https://stripe.com/blog/feed.rss", "https://stripe.com/blog/engineering", "stripe", "635BFF"),
    ("Grab", "https://engineering.grab.com/feed.xml", "https://engineering.grab.com/", "grab", "00B14F"),
    ("Lyft", "https://eng.lyft.com/feed", "https://eng.lyft.com/", "lyft", "FF00BF"),
    ("Zillow", "https://www.zillow.com/tech/feed/", "https://www.zillow.com/tech/", "zillow", "006AFF"),
    ("Salesforce", "https://engineering.salesforce.com/feed/", "https://engineering.salesforce.com/", "salesforce", "00A1E0"),
    ("Etsy", "https://www.etsy.com/codeascraft/rss", "https://www.etsy.com/codeascraft", "etsy", "F16521"),
    ("Walmart", "https://medium.com/feed/walmartglobaltech", "https://medium.com/walmartglobaltech", "walmart", "0071CE"),
    ("Yelp", "https://engineeringblog.yelp.com/feed.xml", "https://engineeringblog.yelp.com/", "yelp", "FF1A1A"),
    ("Duolingo", "https://blog.duolingo.com/rss/", "https://blog.duolingo.com/", "duolingo", "58CC02"),
    ("Zalando", "https://engineering.zalando.com/atom.xml", "https://engineering.zalando.com/", "zalando", "FF6900"),
    ("Discord", "https://discord.com/blog/rss.xml", "https://discord.com/category/engineering", "discord", "5865F2"),
    ("Cloudflare", "https://blog.cloudflare.com/rss/", "https://blog.cloudflare.com/", "cloudflare", "F38020"),
    ("Expedia", "https://medium.com/feed/expedia-group-tech", "https://medium.com/expedia-group-tech", "expedia", "191E3B"),
    ("PayPal", "https://medium.com/feed/paypal-tech", "https://medium.com/paypal-tech", "paypal", "003087"),
    ("Booking.com", "https://booking.ai/feed", "https://booking.ai/", "", "003580"),
]

BY_NAME = {s[0]: s for s in SOURCES}

# key -> (name, short description, its six steps). Steps 4 and 5 are shared by every line.
PROBLEMS = {
    "recs": ("Recommendations", "Pick what each person sees next: feeds, home screens, playlists.",
             ["Understanding the user", "Feature pipelines", "Candidate retrieval", "Ranking", "Serving", "Evaluation"]),
    "search": ("Search", "Turn what someone types into the right results.",
               ["Query understanding", "Indexing", "Retrieval", "Re-ranking", "Serving", "Evaluation"]),
    "ads": ("Ads and ranking", "Choose which ads to show, and what to bid.",
            ["Targeting", "Feature pipelines", "Ad retrieval", "Bidding and ranking", "Serving", "Evaluation"]),
    "llm": ("LLM apps and agents", "Products built on LLMs, from chat to agents that act.",
            ["Prompts and context", "Retrieval for LLMs", "Agents and tools", "Guardrails", "Serving", "Evaluation"]),
    "vision": ("Vision and video", "Understand and edit images and video.",
               ["Labelling data", "Detection", "Tracking", "Video editing", "Serving", "Evaluation"]),
    "predict": ("Forecasting and risk", "Predict demand, prices, arrival times and fraud.",
                ["Defining the target", "Feature pipelines", "Model training", "Decisions", "Serving", "Evaluation"]),
}

# What each step is about, in one line, for the step sections on a problem page
STEP_QUESTIONS = {
    "Understanding the user": "What does this person want right now?",
    "Feature pipelines": "Getting signals to the models, and shipping new ones quickly.",
    "Candidate retrieval": "From millions of items, find the few hundred worth scoring.",
    "Ranking": "Put the candidates in the best order for this person.",
    "Serving": "Run the models fast and cheaply for every request.",
    "Evaluation": "Know a new model is better before it launches.",
    "Query understanding": "Work out what someone means from a few typed words.",
    "Indexing": "Store items so the right ones can be found fast.",
    "Retrieval": "Find the items that match the query.",
    "Re-ranking": "Order the matches by what is most useful.",
    "Targeting": "Decide who an ad is for.",
    "Ad retrieval": "Find the ads worth considering for this moment.",
    "Bidding and ranking": "Decide what to bid and which ad wins.",
    "Prompts and context": "Give the model the right instructions and facts.",
    "Retrieval for LLMs": "Fetch the documents an answer should be based on.",
    "Agents and tools": "Let the model take steps and call other systems.",
    "Guardrails": "Keep answers safe, correct and on topic.",
    "Labelling data": "Get images and video labelled well enough to train on.",
    "Detection": "Find the objects, faces or text in a frame.",
    "Tracking": "Follow things from one frame to the next.",
    "Video editing": "Change footage automatically: crop, cut or enhance.",
    "Defining the target": "Decide exactly what to predict, and from what.",
    "Model training": "Train models that hold up when the world changes.",
    "Decisions": "Turn a prediction into an action: a price, an alert, a block.",
}

# Steps several lines share: step index -> the lines that share it
SHARED_STEPS = {1: ["recs", "ads", "predict"], 4: list(PROBLEMS), 5: list(PROBLEMS)}


def shared_with(problem: str, step: int) -> list[str]:
    """The other lines that share this stop, or [] when the stop is the line's own."""
    lines = SHARED_STEPS.get(step, [])
    return [p for p in lines if p != problem] if problem in lines else []


def lines_at(problem: str, step: int) -> list[str]:
    """Every line a post about this stop shows on: its own, plus the lines sharing the stop."""
    return [problem] + shared_with(problem, step)

# Technique tags shown on each card and used as filters: (tag, pattern over title and text).
# Groq picks from these names; without Groq the patterns pick them.
TAGS = [
    ("LLMs", r"\bllms?\b|large language model|\bgpt\b|generative ai|genai"),
    ("RAG", r"\brag\b|retrieval.augmented"),
    ("Agents", r"\bagents?\b|agentic|tool.?(use|call)"),
    ("Embeddings", r"embedding"),
    ("Vector search", r"vector (search|store|database|index)|nearest neighbou?r|\bann\b|semantic search"),
    ("Two-tower", r"two.tower"),
    ("Transformers", r"transformer"),
    ("Graph neural nets", r"graph neural|\bgnns?\b"),
    ("Fine-tuning", r"fine.?tun|\blora\b|distill"),
    ("Feature store", r"feature (store|platform|pipeline)"),
    ("Real-time", r"real.?time|streaming|online learning"),
    ("GPUs", r"\bgpus?\b|cuda|accelerator"),
    ("Latency", r"latency|\bfaster\b|speed ?up"),
    ("Cost", r"\bcost|cheaper|efficien"),
    ("A/B testing", r"a/b test|experiment"),
    ("Evaluation", r"\bevaluat|benchmark|offline metric"),
    ("Guardrails", r"guardrail|safety|hallucinat|moderation"),
    ("Personalisation", r"personali[sz]"),
    ("Multimodal", r"multimodal|multi-modal|vision.language"),
    ("Computer vision", r"computer vision|image|object detection|\bocr\b"),
    ("Video", r"\bvideo"),
    ("Speech", r"speech|voice|audio|asr\b"),
    ("Forecasting", r"forecast|time series|demand"),
    ("Fraud", r"fraud|abuse|spam|risk"),
    ("Pricing", r"pricing|price"),
    ("Search ranking", r"search ranking|learning.to.rank|relevance"),
    ("Code", r"\bcode\b|coding|developer|code review"),
]
TAG_NAMES = [t for t, _ in TAGS]
