/* case-finder.js
   The Case studies page's finder: category chips, filters and a keyword search over the write-ups.
   Everything runs here in the browser over the JSON index the page carries (case_pages.search_index):
   no LLM and no network call. Words are lowercased, stripped of punctuation and stopwords, lightly
   stemmed and mapped through a small synonym list; a hit in the title or the problem counts most.
   Node loads the same file for its tests (tests/test_case_finder.py), so the search part has no DOM. */
(function (root) {
  "use strict";

  var STOP = {};
  ("a an and are as at be been but by can could do does for from get has have how i if in into is it its just " +
   "like make my need of on or our over so some than that the their them then there these they this those to " +
   "up us use used using via want was way we what when where which who why will with without you your " +
   "e g eg based base build building built new one ones all any") .split(" ").forEach(function (w) { STOP[w] = 1; });

  // Words in one group count as the same word; the first is the one kept
  var GROUPS = [
    ["chatbot", "bot", "assistant", "copilot", "chat", "conversational"],
    ["rag", "retrieval", "retrieve", "knowledge", "grounded", "grounding"],
    ["eval", "evals", "evaluation", "evaluate", "testing", "test", "benchmark", "judge"],
    ["llm", "model", "gpt", "genai"],
    ["agent", "agentic"],
    ["cost", "cheap", "cheaper", "latency", "speed", "fast", "faster", "cache", "caching", "efficient", "efficiency"],
    ["support", "helpdesk", "ticket"],
    ["handoff", "escalation", "escalate", "human"],
    ["policy", "compliance", "guideline"],
    ["access", "permission", "rbac", "role", "authorization", "entitlement"],
    ["hr", "employee", "workforce"],
    ["code", "coding", "developer", "programming"],
    ["ci", "cicd", "pipeline"],
    ["recommend", "recommendation", "recommender", "personalization", "personalisation", "personalize", "personalise"],
    ["fraud", "risk", "abuse", "scam"],
    ["document", "doc", "docs", "pdf"],
    ["search", "query", "lookup"],
    ["guardrail", "safety", "moderation", "jailbreak", "injection"],
    ["finetune", "finetuning", "lora", "tuning"]
  ];

  function stem(w) {
    if (w.length > 4 && /ies$/.test(w)) return w.slice(0, -3) + "y";
    if (w.length > 5 && /ing$/.test(w)) { w = w.slice(0, -3); return /(.)\1$/.test(w) ? w.slice(0, -1) : w; }
    if (w.length > 4 && /ed$/.test(w)) { w = w.slice(0, -2); return /(.)\1$/.test(w) ? w.slice(0, -1) : w; }
    if (w.length > 4 && /(s|x|ch|sh)es$/.test(w)) return w.slice(0, -2);
    if (w.length > 3 && /s$/.test(w) && !/ss$/.test(w)) return w.slice(0, -1);
    return w;
  }

  var SYN = {};
  GROUPS.forEach(function (g) {
    var head = stem(g[0]);
    g.forEach(function (w) { SYN[stem(w)] = head; });
  });

  function key(word) {
    var s = stem(word);
    return SYN[s] || s;
  }

  // The words of a text as [{raw, key}], stopwords left out, one entry per key
  function terms(text) {
    var seen = {}, out = [];
    String(text || "").toLowerCase().replace(/&/g, " and ").split(/[^a-z0-9]+/).forEach(function (w) {
      if (!w || STOP[w] || (w.length < 2 && !/\d/.test(w))) return;
      var k = key(w);
      if (seen[k]) return;
      seen[k] = 1;
      out.push({ raw: w, key: k });
    });
    return out;
  }

  // How much a hit in each part of a write-up counts
  var WEIGHTS = [["t", 3], ["i", 3], ["s", 2], ["topic", 2], ["tags", 1.5], ["who", 1], ["r", 1]];

  function prepare(post, labels, topics) {
    var parts = {
      t: post.t, i: post.i, s: post.s, r: post.r,
      topic: (topics && topics[post.p] ? topics[post.p][0] : post.p),
      tags: (post.g || []).concat((post.x || []).map(function (x) { return (labels && labels.x && labels.x[x]) || x; })).join(" "),
      who: post.c + " " + ((labels && labels.n && labels.n[post.n]) || post.n || "")
    };
    var weight = {};
    WEIGHTS.forEach(function (fw) {
      terms(parts[fw[0]]).forEach(function (t) {
        if (!weight[t.key] || weight[t.key] < fw[1]) weight[t.key] = fw[1];
      });
    });
    return weight;
  }

  // The write-ups that match the query, best first. With detailFirst (the default), the ones that
  // describe the most build details come first (untagged ones count as 0), then the better match,
  // then the newest. One or two words need one hit; longer queries need half their words to match.
  // An empty query keeps every write-up.
  function search(index, query, opts) {
    opts = opts || {};
    var detailFirst = opts.detailFirst !== false;
    var q = terms(query);
    var need = q.length <= 2 ? 1 : Math.ceil(q.length / 2);
    var out = [];
    (index.posts || []).forEach(function (post) {
      var score = 0, hits = [];
      if (q.length) {
        var w = post._w || (post._w = prepare(post, index.labels, index.topics));
        q.forEach(function (t) {
          if (w[t.key]) { score += w[t.key]; hits.push(t.raw); }
        });
        if (hits.length < need) return;
        score += hits.length === q.length ? 2 : 0;
      }
      out.push({ post: post, score: score, hits: hits });
    });
    out.sort(function (a, b) {
      var bd = (b.post.b || 0) - (a.post.b || 0);
      if (detailFirst && bd) return bd;
      if (b.score !== a.score) return b.score - a.score;
      return (b.post.d || "") < (a.post.d || "") ? -1 : (b.post.d || "") > (a.post.d || "") ? 1 : 0;
    });
    return out;
  }

  var api = { stem: stem, key: key, terms: terms, prepare: prepare, search: search };
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.CaseFinder = api;

  // ---------- the page
  var data = document.getElementById("cf-index");
  var form = document.querySelector("[data-cf-form]");
  if (!data || !form) return;
  var index;
  try { index = JSON.parse(data.textContent); } catch (e) { return; }

  var q = form.querySelector("[data-cf-q]");
  var sections = document.querySelector("[data-cf-sections]");
  var results = document.querySelector("[data-cf-results]");
  var list = document.querySelector("[data-cf-list]");
  var status = document.querySelector("[data-cf-status]");
  var none = document.querySelector("[data-cf-none]");
  var more = document.querySelector("[data-cf-more]");
  var menus = { tech: document.querySelector("[data-cf-tech]"), ind: document.querySelector("[data-cf-ind]"),
                co: document.querySelector("[data-cf-co]") };
  var first = document.querySelector("[data-cf-first]");
  var chips = Array.prototype.slice.call(document.querySelectorAll("[data-cf-topic]"));
  var PAGE = 24;
  var state = { q: "", topic: "", tech: "", ind: "", co: "" };
  var found = [], shown = PAGE;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function host(url) { return String(url).split("://").pop().split("/")[0].replace(/^www\./, ""); }
  var MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(" ");
  function niceDate(d) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d || "");
    return m ? (+m[3]) + " " + MONTHS[+m[2] - 1] + " " + m[1] : "";
  }
  var EXT = '<svg class="cs-ext" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>';
  var BOOKMARK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/></svg>';
  var TREND = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 7 13.5 15.5 8.5 10.5 2 17"/><path d="M16 7h6v6"/></svg>';

  // The same card case_pages.post_card draws, plus the words that matched
  function card(hit) {
    var p = hit.post, brand = index.brands[p.c] || ["", "", "#5D5C63"], topic = index.topics[p.p] || ["Case study", "var(--accent)"];
    var body = p.i ? '<p class="cs-issue"><b>Problem</b> ' + esc(p.i) + "</p>" + (p.s ? '<p class="cs-fix"><b>Solution</b> ' + esc(p.s) + "</p>" : "")
                   : (p.s ? "<p>" + esc(p.s) + "</p>" : "");
    if (p.r) body += '<p class="cs-result">' + TREND + "<span>" + esc(p.r) + "</span></p>";
    var match = hit.hits.length ? '<p class="cf-match">Matches your search: ' +
      hit.hits.slice(0, 3).map(function (h) { return "<mark>" + esc(h) + "</mark>"; }).join(" ") + "</p>" : "";
    var tags = (p.g || []).map(function (t) { return '<li><button type="button" data-cs-tag="' + esc(t) + '">' + esc(t) + "</button></li>"; }).join("");
    var pill = p.b >= 2 ? '<span class="cs-bd cs-bd-' + (p.b >= 4 ? "hi" : "mid") + '"' +
      (p.bd ? ' title="Describes: ' + esc(p.bd.join(", ").replace(/_/g, " ")) + '"' : "") + ">✓ Build details " + p.b + "/5</span>" : "";
    var when = niceDate(p.d) ? '<time datetime="' + esc(p.d) + '">' + niceDate(p.d) + "</time>" : "";
    return '<li class="cs-card" style="--c:' + esc(topic[1]) + ";--b:" + esc(brand[2]) + '">' +
      '<div class="cs-cover">' + brand[0] + '<span class="cs-co">' + brand[1] + esc(p.c) + "</span>" + when +
      '<span class="cs-pills"><span class="cs-topic">' + esc(topic[0]) + "</span>" + pill + "</span></div>" +
      '<div class="cs-body"><h3><a class="cs-link" href="' + esc(p.u) + '" rel="noopener" target="_blank">' + esc(p.t) + "</a></h3>" +
      match + body + (tags ? '<ul class="cs-tags" aria-label="Techniques">' + tags + "</ul>" : "") +
      '<div class="cs-foot"><span class="cs-src">Read on ' + esc(host(p.u)) + EXT + "</span>" +
      '<button class="cs-save" type="button" data-cs-save="cs:' + esc(p.u) + '" data-title="' + esc(p.t) + '" data-url="' + esc(p.u) +
      '" data-co="' + esc(p.c) + '" aria-pressed="false">' + BOOKMARK + "<span>Save</span></button></div></div></li>";
  }

  function draw() {
    list.innerHTML = found.slice(0, shown).map(card).join("");
    more.hidden = found.length <= shown;
    none.hidden = found.length > 0;
    document.dispatchEvent(new CustomEvent("cs:cards"));  // app.js marks the saved ones
  }

  function active() { return !!(state.q || state.topic || state.tech || state.ind || state.co); }

  function remember() {
    try {
      var params = new URLSearchParams();
      if (state.q) params.set("q", state.q);
      if (state.topic) params.set("topic", state.topic);
      var qs = params.toString();
      history.replaceState(null, "", location.pathname + (qs ? "?" + qs : "") + location.hash);
    } catch (e) { /* an old browser keeps the address as it is */ }
  }

  function run(scroll) {
    chips.forEach(function (c) { c.setAttribute("aria-pressed", c.getAttribute("data-cf-topic") === state.topic ? "true" : "false"); });
    remember();
    var on = active();
    sections.hidden = on;
    results.hidden = !on;
    if (!on) { list.innerHTML = ""; return; }
    var detailFirst = !first || first.checked;
    found = search(index, state.q, { detailFirst: detailFirst }).filter(function (hit) {
      var p = hit.post;
      return (!state.topic || p.p === state.topic) && (!state.tech || (p.x || []).indexOf(state.tech) >= 0) &&
             (!state.ind || p.n === state.ind) && (!state.co || p.c === state.co);
    });
    shown = PAGE;
    var n = found.length, what = n + (n === 1 ? " write-up" : " write-ups");
    var text = state.q ? what + " match “" + state.q + "”"
             : state.topic ? what + " in " + (index.topics[state.topic] || [state.topic])[0] : what + " match these filters";
    if (state.q && state.topic) text += " in " + (index.topics[state.topic] || [state.topic])[0];
    status.textContent = n ? text + (detailFirst ? " · posts with the most build details first" : "") : text;
    draw();
    if (scroll) results.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    state.q = q.value.trim();
    run(true);
  });
  q.addEventListener("input", function () {
    if (!q.value.trim() && state.q) { state.q = ""; run(false); }  // clearing the box goes back to the sections
  });
  document.addEventListener("click", function (e) {
    var t = e.target.closest ? e.target : null;
    if (!t) return;
    var tryBtn = t.closest("[data-cf-try]");
    if (tryBtn) { q.value = tryBtn.getAttribute("data-cf-try"); state.q = q.value; run(true); return; }
    var chip = t.closest("[data-cf-topic]");
    if (chip) {
      var k = chip.getAttribute("data-cf-topic");
      state.topic = state.topic === k ? "" : k;
      run(!!state.topic);
      return;
    }
    var see = t.closest("[data-cf-see]");
    if (see) { e.preventDefault(); state.topic = see.getAttribute("data-cf-see"); run(true); return; }
    var tag = t.closest("[data-cs-tag]");
    if (tag) { q.value = tag.getAttribute("data-cs-tag"); state.q = q.value; run(true); return; }
    if (t.closest("[data-cf-clear]")) {
      q.value = ""; state = { q: "", topic: "", tech: "", ind: "", co: "" };
      Object.keys(menus).forEach(function (m) { if (menus[m]) menus[m].value = ""; });
      run(false);
      form.scrollIntoView({ behavior: "smooth", block: "center" });
      q.focus({ preventScroll: true });
    }
  });
  Object.keys(menus).forEach(function (m) {
    if (menus[m]) menus[m].addEventListener("change", function () { state[m] = menus[m].value; run(false); });
  });
  if (first) first.addEventListener("change", function () { if (active()) run(false); });
  more.addEventListener("click", function () { shown += PAGE; draw(); });

  // A shared link (?q=...&topic=...) opens with that search
  try {
    var params = new URLSearchParams(location.search);
    state.q = (params.get("q") || "").slice(0, 200);
    state.topic = index.topics[params.get("topic")] ? params.get("topic") : "";
    q.value = state.q;
    if (active()) run(false);
  } catch (e) { /* no URLSearchParams: start on the sections */ }
})(typeof window !== "undefined" ? window : this);
