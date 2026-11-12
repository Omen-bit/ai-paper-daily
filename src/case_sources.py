"""
case_sources.py
The company engineering blogs behind the Case studies page, the topics posts are sorted into,
and the technique tags shown on each card.

Sources run from the largest tech companies to small startups, plus the AWS and Google Cloud AI
blogs, whose posts are mostly write-ups of how other companies (of every size) built on them.
A feed that moves or goes down is skipped and logged; the posts already saved stay.

The site's focus is LLMs in production (RAG, agents, evaluation, cost), so those topics come
first; recommendations, ads, forecasting and vision keep their own topics.
"""
import re

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
    ("Booking.com", "https://booking.ai/feed", "https://booking.ai/", "bookingdotcom", "003580"),
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
    ("Microsoft", "https://www.microsoft.com/en-us/research/feed/", "https://www.microsoft.com/en-us/research/blog/", "microsoft", "0078D4"),
    ("Databricks", "https://www.databricks.com/feed", "https://www.databricks.com/blog", "databricks", "FF3621"),
    ("Adobe", "https://medium.com/feed/adobetech", "https://medium.com/adobetech", "adobe", "FF0000"),
    # Teams that write mostly about LLMs in production
    ("Hugging Face", "https://huggingface.co/blog/feed.xml", "https://huggingface.co/blog", "huggingface", "FFD21E"),
    ("LangChain", "https://blog.langchain.dev/rss/", "https://blog.langchain.dev/", "langchain", "1C3C3C"),
    ("Intercom", "https://www.intercom.com/blog/feed/", "https://www.intercom.com/blog/", "intercom", "1F8DED"),
    ("Replit", "https://blog.replit.com/feed.xml", "https://blog.replit.com/", "replit", "F26207"),
    ("Vercel", "https://vercel.com/atom", "https://vercel.com/blog", "vercel", "000000"),
    ("Weaviate", "https://weaviate.io/blog/rss.xml", "https://weaviate.io/blog", "weaviate", "00B061"),
    ("Honeycomb", "https://www.honeycomb.io/feed", "https://www.honeycomb.io/blog", "", "F5A623"),
    # Cloud AI blogs: customer write-ups from companies of every size
    ("AWS", "https://aws.amazon.com/blogs/machine-learning/feed/", "https://aws.amazon.com/blogs/machine-learning/", "", "FF9900"),
    ("Google Cloud", "https://cloudblog.withgoogle.com/products/ai-machine-learning/rss/", "https://cloud.google.com/blog/products/ai-machine-learning", "", "4285F4"),
    # Large software and internet companies
    ("Atlassian", "https://www.atlassian.com/engineering/feed", "https://www.atlassian.com/engineering", "", "0052CC"),
    ("Reddit", "https://www.reddit.com/r/RedditEng/.rss", "https://www.reddit.com/r/RedditEng/", "", "FF4500"),
    ("Twilio", "https://www.twilio.com/blog/feed", "https://www.twilio.com/blog", "", "F22F46"),
    ("Block", "https://developer.squareup.com/blog/rss.xml", "https://developer.squareup.com/blog/", "", "000000"),
    ("Indeed", "https://engineering.indeedblog.com/feed/", "https://engineering.indeedblog.com/", "", "003A9B"),
    ("GitLab", "https://about.gitlab.com/atom.xml", "https://about.gitlab.com/blog/", "", "FC6D26"),
    ("JetBrains", "https://blog.jetbrains.com/ai/feed/", "https://blog.jetbrains.com/ai/", "", "000000"),
    ("MongoDB", "https://www.mongodb.com/blog/rss", "https://www.mongodb.com/blog", "", "47A248"),
    ("Elastic", "https://www.elastic.co/search-labs/rss/feed", "https://www.elastic.co/search-labs", "", "005571"),
    ("Snowflake", "https://medium.com/feed/snowflake", "https://medium.com/snowflake", "", "29B5E8"),
    ("Datadog", "https://www.datadoghq.com/blog/index.xml", "https://www.datadoghq.com/blog/", "", "632CA6"),
    ("HubSpot", "https://product.hubspot.com/blog/rss.xml", "https://product.hubspot.com/blog", "", "FF7A59"),
    ("Zendesk", "https://zendesk.engineering/feed", "https://zendesk.engineering/", "", "03363D"),
    ("Asana", "https://blog.asana.com/category/eng/feed/", "https://blog.asana.com/category/eng/", "", "F06A6A"),
    ("Grammarly", "https://www.grammarly.com/blog/engineering/feed/", "https://www.grammarly.com/blog/engineering/", "", "15C39A"),
    ("Box", "https://medium.com/feed/box-tech-blog", "https://medium.com/box-tech-blog", "", "0061D5"),
    ("Wix", "https://www.wix.engineering/blog-feed.xml", "https://www.wix.engineering/", "", "000000"),
    ("monday.com", "https://engineering.monday.com/feed/", "https://engineering.monday.com/", "", "FF3D57"),
    ("Miro", "https://medium.com/feed/miro-engineering", "https://medium.com/miro-engineering", "", "FFD02F"),
    ("Postman", "https://blog.postman.com/feed/", "https://blog.postman.com/", "", "FF6C37"),
    ("Medium", "https://medium.engineering/feed", "https://medium.engineering/", "", "000000"),
    ("Nextdoor", "https://engblog.nextdoor.com/feed", "https://engblog.nextdoor.com/", "", "8ED500"),
    # Retail and marketplaces
    ("Target", "https://tech.target.com/feed.xml", "https://tech.target.com/", "", "CC0000"),
    ("The Home Depot", "https://medium.com/feed/thd-engineering", "https://medium.com/thd-engineering", "", "F96302"),
    ("Mercari", "https://engineering.mercari.com/en/blog/feed.xml", "https://engineering.mercari.com/en/blog/", "", "FF0211"),
    ("Allegro", "https://blog.allegro.tech/feed.xml", "https://blog.allegro.tech/", "", "FF5A00"),
    ("Adevinta", "https://medium.com/feed/adevinta-tech-blog", "https://medium.com/adevinta-tech-blog", "", "1B1B1B"),
    ("Thumbtack", "https://medium.com/feed/thumbtack-engineering", "https://medium.com/thumbtack-engineering", "", "009FD9"),
    ("Tokopedia", "https://medium.com/feed/tokopedia-engineering", "https://medium.com/tokopedia-engineering", "", "42B549"),
    ("Klaviyo", "https://klaviyo.tech/feed", "https://klaviyo.tech/", "", "232426"),
    ("Criteo", "https://medium.com/feed/criteo-engineering", "https://medium.com/criteo-engineering", "", "FE5000"),
    # Food, travel and transport
    ("Deliveroo", "https://deliveroo.engineering/feed.xml", "https://deliveroo.engineering/", "", "00CCBC"),
    ("HelloFresh", "https://engineering.hellofresh.com/feed", "https://engineering.hellofresh.com/", "", "91C11E"),
    ("Picnic", "https://blog.picnic.nl/feed", "https://blog.picnic.nl/", "", "E1171E"),
    ("iFood", "https://medium.com/feed/ifood-engineering", "https://medium.com/ifood-engineering", "", "EA1D2C"),
    ("trivago", "https://tech.trivago.com/index.xml", "https://tech.trivago.com/", "", "007FAD"),
    ("Traveloka", "https://medium.com/feed/traveloka-engineering", "https://medium.com/traveloka-engineering", "", "0194F3"),
    ("BlaBlaCar", "https://medium.com/feed/blablacar", "https://medium.com/blablacar", "", "00AFF5"),
    ("Gojek", "https://medium.com/feed/gojekengineering", "https://medium.com/gojekengineering", "", "00AA13"),
    # Money
    ("Brex", "https://medium.com/feed/brexeng", "https://medium.com/brexeng", "", "212121"),
    ("Ramp", "https://engineering.ramp.com/rss.xml", "https://engineering.ramp.com/", "", "E4F222"),
    ("Gusto", "https://engineering.gusto.com/rss/", "https://engineering.gusto.com/", "", "F45D48"),
    ("CRED", "https://engineering.cred.club/feed", "https://engineering.cred.club/", "", "1B1B1B"),
    ("Groww", "https://tech.groww.in/feed", "https://tech.groww.in/", "", "00D09C"),
    ("Zerodha", "https://zerodha.tech/index.xml", "https://zerodha.tech/", "", "387ED1"),
    # Media, learning, health and games
    ("Dream11", "https://blog.dream11engineering.com/feed", "https://blog.dream11engineering.com/", "", "D32F2F"),
    ("ShareChat", "https://medium.com/feed/sharechat-techbyte", "https://medium.com/sharechat-techbyte", "", "FF6D00"),
    ("Urban Company", "https://medium.com/feed/urbancompany-engineering", "https://medium.com/urbancompany-engineering", "", "000000"),
    ("Deezer", "https://deezer.io/feed", "https://deezer.io/", "", "A238FF"),
    ("Scribd", "https://tech.scribd.com/feed.xml", "https://tech.scribd.com/", "", "1E7B85"),
    ("Udemy", "https://medium.com/feed/udemy-engineering", "https://medium.com/udemy-engineering", "", "A435F0"),
    ("Coursera", "https://medium.com/feed/coursera-engineering", "https://medium.com/coursera-engineering", "", "0056D2"),
    ("Khan Academy", "https://blog.khanacademy.org/feed/", "https://blog.khanacademy.org/", "", "14BF96"),
    ("Doctolib", "https://medium.com/feed/doctolib", "https://medium.com/doctolib", "", "107ACA"),
    # Small teams and startups that build AI products and write about it
    ("Sourcegraph", "https://sourcegraph.com/blog/rss.xml", "https://sourcegraph.com/blog", "", "A112FF"),
    ("PostHog", "https://posthog.com/rss.xml", "https://posthog.com/blog", "", "F54E00"),
    ("Supabase", "https://supabase.com/rss.xml", "https://supabase.com/blog", "", "3FCF8E"),
    ("Neon", "https://neon.tech/blog/rss.xml", "https://neon.tech/blog", "", "00E599"),
    ("Fly.io", "https://fly.io/blog/feed.xml", "https://fly.io/blog/", "", "7B3BE2"),
    ("Sentry", "https://blog.sentry.io/feed.xml", "https://blog.sentry.io/", "", "362D59"),
    ("Grafana Labs", "https://grafana.com/blog/index.xml", "https://grafana.com/blog/", "", "F46800"),
    ("Qdrant", "https://qdrant.tech/blog/index.xml", "https://qdrant.tech/blog/", "", "DC244C"),
    ("Vespa", "https://blog.vespa.ai/feed.xml", "https://blog.vespa.ai/", "", "61D790"),
    ("LlamaIndex", "https://www.llamaindex.ai/blog/feed", "https://www.llamaindex.ai/blog", "", "000000"),
    ("Mozilla.ai", "https://blog.mozilla.ai/rss/", "https://blog.mozilla.ai/", "", "000000"),
]

BY_NAME = {s[0]: s for s in SOURCES}
# Blogs where most posts tell how a customer built something: the card shows the customer's name
CUSTOMER_BLOGS = {"AWS", "Google Cloud"}

# key -> (name, what it covers). The order is the order of the topic chips.
TOPICS = {
    "rag": ("RAG and search", "Retrieval, vector search, chunking and re-ranking, for search boxes and for LLM answers."),
    "agents": ("Agents", "LLMs that use tools and work through multi-step tasks, when no narrower agent topic fits."),
    "coding": ("Coding agents", "Agents that write, review, migrate and test code, or build whole apps."),
    "data": ("Data agents", "Agents that answer business questions over a company's data, metrics and dashboards."),
    "ops": ("Ops agents", "Agents that watch production: alerts, incidents, failure diagnosis and security work."),
    "support": ("Customer support", "Assistants and agents that answer customers and the teams that help them."),
    "platforms": ("Agent platforms", "Running agents at scale: harnesses, sandboxes, memory, MCP, observability and training."),
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
FOCUS = ["rag", "agents", "coding", "data", "ops", "support", "platforms", "evals", "cost", "tuning", "safety", "llm"]
# The narrower topics a post about agents can move to; "agents" stays for the ones none of them fit
AGENT_TOPICS = ("coding", "data", "ops", "support", "platforms")

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
    ("Speculative decoding", r"speculative decod|multi.token prediction"),
    ("Graph RAG", r"graph.?rag|knowledge graph"),
    ("Query rewriting", r"query (rewrit|expan|reformulat|understanding)"),
    ("Hybrid search", r"hybrid search|bm25"),
    ("Reranking", r"re-?rank"),
    ("Chunking", r"chunk"),
    ("Tool calling", r"tool.?(use|call)|function call"),
    ("Multi-agent", r"multi.?agent"),
    ("Agent memory", r"(agent|long.term|persistent|episodic|shared) memory"),
    ("Routing", r"\brout(er|ing)\b|orchestrat"),
    ("Planning", r"\bplann(er|ing)\b"),
    ("Human review", r"human.(in|on).the.loop|human (review|approval|feedback)"),
    ("Sandboxing", r"sandbox"),
    ("Context engineering", r"context (engineering|management|window)|long.context"),
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
    ("Sequence models", r"sequen(ce|tial) (model|recommend)|generative (recommend|retrieval)"),
    ("Bandits", r"bandit"),
    ("Synthetic data", r"synthetic data"),
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


# A post about agents moves to a narrower topic when its title (first) or its text matches one of
# these, checked in this order. Picked from the 148 posts that were all "Agents" before the split.
AGENT_RULES = [
    ("support", r"customer (support|service|questions|context)|support (tickets?|team|agents?|work)|helpdesk|"
                r"contact cent|\bfin\b|speed.to.lead|engineering support|customers? (ask|wait)"),
    ("ops", r"\bsre\b|incidents?|on.?call|alerts?|paging|failure diagnosis|root cause|production issues|"
            r"factory operations|security (work|investigation|fix)|investigat|outages?|monitoring agent"),
    ("data", r"analytic|\bdata (apps?|sources|analys|questions)|metrics|dashboards?|\bgenie\b|\bsql\b|spreadsheet|"
             r"business (data|context|question)|stripe data|ml exploration|machine learning model|data graph|analysts?"),
    ("coding", r"\bcod(e|es|ing)\b|codebase|software|developers?|\bapps?\b|vibe|\bgit\b|pull requests?|\bmerge\b|"
               r"migrat|rewrite|translat|cuda|\budfs?\b|ros 2|full.stack|web ?sites?|storefront|\bcli\b|\bsdk\b|"
               r"agentic (development|engineering)|programm|e2e test|prototyp"),
    ("platforms", r"platform|sandbox|harness|kubernetes|\bmcp\b|infrastructure|memory|protocol|identity|govern|"
                  r"secur|durable|runtime|substrate|gateway|observab|telemetry|fleet|orchestrat|router|framework|"
                  r"open.?sourc|on.device|reinforcement|\brl\b|post.train|training data|benchmark"),
]


def split_agents(post: dict) -> str:
    """The narrower agent topic for a post about agents, or "agents" when none fits. Keywords only, no network."""
    title = (post.get("title") or "").lower()
    text = " ".join(str(post.get(k) or "") for k in ("title", "issue", "summary", "text")).lower()[:1500]
    for scope in (title, text):
        for topic, pattern in AGENT_RULES:
            if re.search(pattern, scope):
                return topic
    return "agents"


# ---------- categories the classifier proposes
# Groq may name a new category when none of TOPICS fits. Names are compared in a normal form
# (lower case, singular words, no filler words) so "Voice Agents", "voice agent" and "Voice-agents"
# are one category, and a name that only restates a topic ("AI agents", "Search") joins that topic.
CATEGORY_SYNONYMS = {
    "agent": "agents", "ai agent": "agents", "llm agent": "agents", "agentic": "agents", "autonomous agent": "agents",
    "search": "rag", "retrieval": "rag", "semantic search": "rag", "vector search": "rag", "enterprise search": "rag",
    "evaluation": "evals", "eval": "evals", "testing": "evals", "llm evaluation": "evals", "benchmarking": "evals",
    "cost": "cost", "latency": "cost", "inference": "cost", "serving": "cost", "model serving": "cost", "efficiency": "cost",
    "fine tuning": "tuning", "finetuning": "tuning", "training": "tuning", "model training": "tuning", "post training": "tuning",
    "safety": "safety", "moderation": "safety", "content moderation": "safety", "trust safety": "safety", "guardrail": "safety",
    "llm": "llm", "llm product": "llm", "generative": "llm", "assistant": "llm", "copilot": "llm", "chatbot": "llm",
    "recommendation": "recs", "recommender": "recs", "personalization": "recs", "personalisation": "recs",
    "ranking": "recs", "feed ranking": "recs",
    "ad": "ads", "advertising": "ads", "ad ranking": "ads",
    "forecasting": "predict", "prediction": "predict", "fraud detection": "predict", "fraud": "predict",
    "demand forecasting": "predict",
    "computer vision": "vision", "image": "vision", "video": "vision", "image generation": "vision",
    "coding": "coding", "code generation": "coding", "coding assistant": "coding", "developer tool": "coding",
    "developer productivity": "coding", "software engineering": "coding", "code review": "coding",
    "data analysis": "data", "analytics": "data", "data analytics": "data", "text to sql": "data",
    "business intelligence": "data",
    "sre": "ops", "incident response": "ops", "devop": "ops", "observability": "ops", "aiop": "ops",
    "customer service": "support", "support": "support", "support agent": "support", "customer support agent": "support",
    "agent infrastructure": "platforms", "agent platform": "platforms", "agent framework": "platforms",
    "agent tooling": "platforms",
    "other": "", "misc": "", "miscellaneous": "", "general": "", "none": "", "n/a": "",
}
_FILLER = {"and", "for", "the", "of", "with", "in", "a", "an", "&", "ai", "ml", "system"}


def _singular(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def category_norm(name: str) -> str:
    """A category name in its normal form, for comparing: "Voice-Agents" -> "voice agent"."""
    words = [_singular(w) for w in re.sub(r"[^a-z0-9&/]+", " ", (name or "").lower()).split()]
    kept = [w for w in words if w not in _FILLER]
    return " ".join(kept or words)


_TOPIC_BY_NORM = {category_norm(k): v for k, v in CATEGORY_SYNONYMS.items()}
_TOPIC_BY_NORM.update({category_norm(name): key for key, (name, _) in TOPICS.items()})
_TOPIC_BY_NORM.update({category_norm(key): key for key in TOPICS})


def clean_category(name: str) -> str:
    """A proposed name tidied for the chip row: 1-3 words in sentence case like "Coding agents",
    acronyms kept ("LLM", "SQL"). "" when it is too long or too short to be a category."""
    words = re.sub(r"[^\w&+/ -]+", " ", str(name or "")).replace("_", " ").split()
    if not words or len(words) > 3 or len("".join(words)) < 3:
        return ""
    out = []
    for i, w in enumerate(words):
        if 1 < len(w) <= 4 and w.isupper():  # LLM, SQL, RAG, GPU
            out.append(w)
        else:
            out.append(w.capitalize() if i == 0 else w.lower())
    return " ".join(out)


def match_category(name: str, known: dict[str, str] | None = None) -> tuple[str | None, str]:
    """Where a proposed category name belongs:
    (topic key, "") when it is one of TOPICS or a synonym of one;
    ("", display name) for a new category, using the name already in known (normal form -> display
    name) when it is the same category spelled differently;
    (None, "") when the name is unusable or just "Other"."""
    shown = clean_category(name)
    norm = category_norm(shown)
    if not shown or not norm:
        return None, ""
    if norm in _TOPIC_BY_NORM:
        key = _TOPIC_BY_NORM[norm]
        return (key, "") if key else (None, "")
    if known and norm in known:
        return "", known[norm]
    return "", shown


def category_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
