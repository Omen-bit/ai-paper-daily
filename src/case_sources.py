"""
case_sources.py
The company engineering blogs behind the Case studies page, the topics posts are sorted into,
and the technique tags shown on each card.

The site's focus is LLMs in production (RAG, agents, evaluation, cost), so those topics come
first; recommendations, ads, forecasting and vision keep their own topics.
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
    # Banking and payments
    ("Capital One", "https://medium.com/feed/capital-one-tech", "https://medium.com/capital-one-tech", "", "004879"),
    ("Intuit", "https://medium.com/feed/intuit-engineering", "https://medium.com/intuit-engineering", "intuit", "236CFF"),
    ("Wise", "https://medium.com/feed/wise-engineering", "https://medium.com/wise-engineering", "wise", "9FE870"),
    ("Nubank", "https://building.nubank.com.br/feed/", "https://building.nubank.com.br/", "nubank", "820AD1"),
    ("Klarna", "https://engineering.klarna.com/feed", "https://engineering.klarna.com/", "klarna", "FFB3C7"),
    ("Razorpay", "https://engineering.razorpay.com/feed", "https://engineering.razorpay.com/", "razorpay", "0C2451"),
    ("PhonePe", "https://tech.phonepe.com/feed/", "https://tech.phonepe.com/", "phonepe", "5F259F"),
    # Shopping
    ("Flipkart", "https://blog.flipkart.tech/feed", "https://blog.flipkart.tech/", "flipkart", "2874F0"),
    ("Myntra", "https://medium.com/feed/myntra-engineering", "https://medium.com/myntra-engineering", "", "FF3F6C"),
    ("Meesho", "https://medium.com/feed/meesho-tech", "https://medium.com/meesho-tech", "", "F43397"),
    ("Mercado Libre", "https://medium.com/feed/mercadolibre-tech", "https://medium.com/mercadolibre-tech", "", "2D3277"),
    ("Coupang", "https://medium.com/feed/coupang-engineering", "https://medium.com/coupang-engineering", "", "D52A1D"),
    ("Faire", "https://craft.faire.com/feed", "https://craft.faire.com/", "", "333333"),
    ("OLX", "https://tech.olx.com/feed", "https://tech.olx.com/", "", "002F34"),
    # Food delivery
    ("Swiggy", "https://bytes.swiggy.com/feed", "https://bytes.swiggy.com/", "swiggy", "FC8019"),
    ("Glovo", "https://medium.com/feed/glovo-engineering", "https://medium.com/glovo-engineering", "glovo", "F2CC38"),
    ("Delivery Hero", "https://tech.deliveryhero.com/feed/", "https://tech.deliveryhero.com/", "", "D61F26"),
    # Travel
    ("Tripadvisor", "https://medium.com/feed/tripadvisor", "https://medium.com/tripadvisor", "tripadvisor", "34E0A1"),
    ("Agoda", "https://medium.com/feed/agoda-engineering", "https://medium.com/agoda-engineering", "", "2067DA"),
    # Media, fitness and dating
    ("The New York Times", "https://open.nytimes.com/feed", "https://open.nytimes.com/", "newyorktimes", "000000"),
    ("JioHotstar", "https://blog.hotstar.com/feed", "https://blog.hotstar.com/", "", "1F80E0"),
    ("Strava", "https://medium.com/feed/strava-engineering", "https://medium.com/strava-engineering", "strava", "FC4C02"),
    ("Tinder", "https://medium.com/feed/tinder", "https://medium.com/tinder", "tinder", "FF6B6B"),
    # Software
    ("Microsoft", "https://www.microsoft.com/en-us/research/feed/", "https://www.microsoft.com/en-us/research/blog/", "", "0078D4"),
    ("Databricks", "https://www.databricks.com/feed", "https://www.databricks.com/blog", "databricks", "FF3621"),
    ("Adobe", "https://medium.com/feed/adobetech", "https://medium.com/adobetech", "adobe", "FF0000"),
    # Teams that write mostly about LLMs in production
    ("Hugging Face", "https://huggingface.co/blog/feed.xml", "https://huggingface.co/blog", "huggingface", "FFD21E"),
    ("LangChain", "https://blog.langchain.dev/rss/", "https://blog.langchain.dev/", "langchain", "1C3C3C"),
    ("Intercom", "https://www.intercom.com/blog/feed/", "https://www.intercom.com/blog/", "intercom", "1F8DED"),
    ("Replit", "https://blog.replit.com/feed.xml", "https://blog.replit.com/", "replit", "F26207"),
    ("Vercel", "https://vercel.com/atom", "https://vercel.com/blog", "vercel", "000000"),
    ("Weaviate", "https://weaviate.io/blog/rss.xml", "https://weaviate.io/blog", "", "00B061"),
    ("Honeycomb", "https://www.honeycomb.io/feed", "https://www.honeycomb.io/blog", "", "F5A623"),
]

BY_NAME = {s[0]: s for s in SOURCES}

# key -> (name, what it covers). The order is the order of the topic chips.
TOPICS = {
    "rag": ("RAG and search", "Retrieval, vector search, chunking and re-ranking, for search boxes and for LLM answers."),
    "agents": ("Agents", "LLMs that use tools and work through multi-step tasks."),
    "evals": ("Evaluation", "Offline evals, LLM judges, A/B tests: knowing a change is better before it ships."),
    "cost": ("Cost and speed", "Caching, smaller or distilled models, batching and GPU serving to cut cost and latency."),
    "tuning": ("Fine-tuning", "LoRA, distillation and training models on a company's own data."),
    "safety": ("Guardrails", "Stopping hallucinations, unsafe answers and prompt injection; moderation."),
    "llm": ("LLM products", "Prompting, assistants and copilots: shipping a product built on an LLM."),
    "recs": ("Recommendations", "Feeds, home screens and playlists: picking what each person sees next."),
    "ads": ("Ads", "Targeting, bidding and ranking ads."),
    "predict": ("Forecasting", "Predicting demand, prices, arrival times and fraud."),
    "vision": ("Vision", "Understanding and editing images and video."),
}
FOCUS = ["rag", "agents", "evals", "cost", "tuning", "safety", "llm"]

# Topic from keywords when Groq is not available: (topic, pattern), first match wins.
# Titles are checked first, then the opening text.
TOPIC_RULES = [
    ("safety", r"guardrail|hallucinat|jailbreak|prompt injection|red.?team|moderation|\bsafety\b"),
    ("evals", r"\bevals?\b|evaluat|llm.as.a.judge|\bjudges?\b|benchmark|a/b test|offline metric"),
    ("cost", r"\bcosts?\b|cheaper|latency|\bcach(e|ing)\b|distill|quantiz|quantis|small(er)? models?|batching|inference|\bserving\b|\bgpus?\b|throughput"),
    ("tuning", r"fine.?tun|\blora\b|rlhf|post.?training|synthetic data"),
    ("agents", r"\bagents?\b|agentic|tool.?(use|call)|multi.?step"),
    ("rag", r"\brag\b|retrieval|vector|embedding|semantic search|\bsearch\b|re-?rank|chunk|\bindex"),
    ("llm", r"\bllms?\b|large language|genai|generative ai|\bgpt|chatbot|assistant|copilot|prompt"),
    ("ads", r"\bads?\b|advertis|bidding|auction"),
    ("predict", r"forecast|demand|\beta\b|arrival time|fraud|risk|pricing|time series|churn"),
    ("vision", r"computer vision|image|video|visual|\bocr\b|detection"),
    ("recs", r"recommend|ranking|personali[sz]|feed\b|two.tower|candidate"),
]

# Posts that look like these are sent to Groq first each run, so its daily calls go on the focus topics
FOCUS_WORDS = r"\bllms?\b|large language|genai|generative|\bgpt|\brag\b|retrieval|agent|\bevals?\b|evaluat|prompt|fine.?tun|\blora\b|distill|inference|embedding|vector|copilot|assistant|chatbot|hallucinat|guardrail"

# Technique tags shown on each card and used as filters: (tag, pattern over title and text).
# Groq picks from these names; without Groq the patterns pick them. More specific tags come first.
TAGS = [
    ("Semantic caching", r"semantic cach"),
    ("Prompt caching", r"prompt cach|kv.?cache|context cach"),
    ("Distillation", r"distill"),
    ("Small models", r"small(er)? (language )?models?|\bslms?\b"),
    ("Quantisation", r"quantiz|quantis|\bint[48]\b|\bfp8\b"),
    ("LLM-as-judge", r"llm.as.a.judge|\bjudge (model|llm)|\bllm judges?"),
    ("Hybrid search", r"hybrid search|bm25"),
    ("Reranking", r"re-?rank"),
    ("Chunking", r"chunk"),
    ("Tool calling", r"tool.?(use|call)|function call"),
    ("Multi-agent", r"multi.?agent"),
    ("RAG", r"\brag\b|retrieval.augmented"),
    ("Agents", r"\bagents?\b|agentic"),
    ("Evals", r"\bevals?\b|evaluat|benchmark|offline metric"),
    ("A/B testing", r"a/b test|experiment"),
    ("Fine-tuning", r"fine.?tun|\blora\b"),
    ("Guardrails", r"guardrail|hallucinat|moderation|prompt injection"),
    ("Embeddings", r"embedding"),
    ("Vector search", r"vector (search|store|database|index)|nearest neighbou?r|\bann\b|semantic search"),
    ("Prompting", r"prompt"),
    ("Latency", r"latency|\bfaster\b|speed ?up"),
    ("Cost", r"\bcosts?\b|cheaper|cost.efficien"),
    ("GPUs", r"\bgpus?\b|cuda|accelerator"),
    ("LLMs", r"\bllms?\b|large language model|\bgpt|generative ai|genai"),
    ("Two-tower", r"two.tower"),
    ("Transformers", r"transformer"),
    ("Graph neural nets", r"graph neural|\bgnns?\b"),
    ("Feature store", r"feature (store|platform|pipeline)"),
    ("Real-time", r"real.?time|streaming|online learning"),
    ("Personalisation", r"personali[sz]"),
    ("Multimodal", r"multimodal|multi-modal|vision.language"),
    ("Speech", r"speech|voice|audio|\basr\b"),
    ("Code", r"\bcode\b|coding|code review"),
]
TAG_NAMES = [t for t, _ in TAGS]

# Posts saved before the topics changed (problem + step) -> today's topic
_OLD_LLM_STEPS = {0: "llm", 1: "rag", 2: "agents", 3: "safety", 4: "cost", 5: "evals"}


def topic_of(post: dict) -> str | None:
    """A saved post's topic, moving posts saved under the old problems onto today's topics."""
    key = post.get("problem")
    if key == "llm" and "step" in post:
        try:
            return _OLD_LLM_STEPS.get(int(post["step"]), "llm")
        except (TypeError, ValueError):
            return "llm"
    if key == "search":
        return "rag"
    return key if key in TOPICS else None
