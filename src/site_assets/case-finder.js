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

  // STOP and GROUPS are shared with case_research.py, which matches papers to cases at build time
  var api = { stem: stem, key: key, terms: terms, prepare: prepare, search: search, STOP: Object.keys(STOP), GROUPS: GROUPS };
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
  var EMPTY = function () { return { q: "", topic: "", tech: "", ind: "", co: "", fresh: false, mine: false }; };
  var state = EMPTY();
  var mineChip = document.querySelector("[data-cf-mine]");

  // Followed topics (app.js keeps them in localStorage) and the day of the reader's previous visit,
  // for the "Your topics" chip and the "N new" badges on followed topics
  function follows() {
    try { var f = JSON.parse(localStorage.getItem("apd.follows") || "[]"); return Array.isArray(f) ? f : []; } catch (e) { return []; }
  }
  var lastVisit = (function () {
    var today = new Date().toISOString().slice(0, 10), seen = {};
    try { seen = JSON.parse(localStorage.getItem("apd.casesVisit") || "{}") || {}; } catch (e) { /* a private window */ }
    if (seen.current !== today) { seen.last = seen.current || ""; seen.current = today; }
    try { localStorage.setItem("apd.casesVisit", JSON.stringify(seen)); } catch (e) { /* not kept */ }
    return seen.last || "";
  })();
  function paintFollows() {
    var mine = follows().filter(function (k) { return index.topics[k]; });
    if (mineChip) {
      mineChip.hidden = mine.length === 0;
      mineChip.querySelector("[data-cf-mine-n]").textContent = index.posts.filter(function (p) { return mine.indexOf(p.p) >= 0; }).length;
      if (!mine.length && state.mine) { state.mine = false; run(false); }
    }
    document.querySelectorAll("[data-cf-badge]").forEach(function (b) {
      var k = b.getAttribute("data-cf-badge");
      var n = lastVisit && mine.indexOf(k) >= 0
        ? index.posts.filter(function (p) { return p.p === k && (p.a || "") > lastVisit; }).length : 0;
      b.hidden = !n;
      b.textContent = n ? "+" + n + " new" : "";
    });
  }
  document.addEventListener("cs:follows", paintFollows);
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
  var PAPER = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/></svg>';
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
      '<span class="cs-pills">' + (p.nw ? '<span class="cs-new">New</span>' : "") + '<span class="cs-topic">' + esc(topic[0]) + "</span>" + pill + "</span></div>" +
      '<div class="cs-body"><h3><a class="cs-link" href="' + esc(p.u) + '" rel="noopener" target="_blank">' + esc(p.t) + "</a></h3>" +
      match + body + (tags ? '<ul class="cs-tags" aria-label="Techniques">' + tags + "</ul>" : "") +
      (p.rp ? '<a class="cs-rel" href="../paper/' + esc(p.rp[0]) + '.html">' + PAPER + "<div><span>Research behind this, on AI Papers Daily</span><b>" +
              esc(p.rp[1]) + "</b></div></a>" : "") +
      (p.sb ? '<p class="cs-by"><span class="cs-av" aria-hidden="true">' + esc(p.sb.replace(/^@/, "").charAt(0).toUpperCase()) +
              "</span><span>Suggested by <b>" + esc(p.sb) + "</b></span></p>" : "") +
      '<div class="cs-foot"><span class="cs-src">Read on ' + esc(host(p.u)) + EXT + "</span>" +
      (p.sl ? '<a class="cs-details" href="' + esc(p.sl) + '.html" aria-label="Details: ' + esc(p.t) + '">Details</a>' : "") +
      '<button class="cs-save" type="button" data-cs-save="cs:' + esc(p.u) + '" data-title="' + esc(p.t) + '" data-url="' + esc(p.u) +
      '" data-co="' + esc(p.c) + '" aria-pressed="false">' + BOOKMARK + "<span>Save</span></button></div></div></li>";
  }

  function draw() {
    list.innerHTML = found.slice(0, shown).map(card).join("");
    more.hidden = found.length <= shown;
    none.hidden = found.length > 0;
    document.dispatchEvent(new CustomEvent("cs:cards"));  // app.js marks the saved ones
  }

  function active() { return !!(state.q || state.topic || state.tech || state.ind || state.co || state.fresh || state.mine); }

  function remember() {
    try {
      var params = new URLSearchParams();
      if (state.q) params.set("q", state.q);
      if (state.topic) params.set("topic", state.topic);
      if (state.tech) params.set("tech", state.tech);
      if (state.ind) params.set("ind", state.ind);
      var qs = params.toString();
      history.replaceState(null, "", location.pathname + (qs ? "?" + qs : "") + location.hash);
    } catch (e) { /* an old browser keeps the address as it is */ }
  }

  function run(scroll) {
    chips.forEach(function (c) { c.setAttribute("aria-pressed", c.getAttribute("data-cf-topic") === state.topic ? "true" : "false"); });
    if (mineChip) mineChip.setAttribute("aria-pressed", state.mine ? "true" : "false");
    var mine = follows();
    remember();
    var on = active();
    sections.hidden = on;
    results.hidden = !on;
    if (!on) { list.innerHTML = ""; return; }
    var detailFirst = !first || first.checked;
    found = search(index, state.q, { detailFirst: detailFirst }).filter(function (hit) {
      var p = hit.post;
      return (!state.topic || p.p === state.topic) && (!state.tech || (p.x || []).indexOf(state.tech) >= 0) &&
             (!state.ind || p.n === state.ind) && (!state.co || p.c === state.co) &&
             (!state.fresh || p.nw) && (!state.mine || mine.indexOf(p.p) >= 0);
    });
    shown = PAGE;
    var n = found.length, what = n + (n === 1 ? " write-up" : " write-ups");
    var text = state.q ? what + " match “" + state.q + "”"
             : state.topic ? what + " in " + (index.topics[state.topic] || [state.topic])[0]
             : state.fresh ? n + " new " + (n === 1 ? "write-up" : "write-ups") + " this week"
             : state.mine ? what + " in your topics" : what + " match these filters";
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
    if (t.closest("[data-cf-fresh]")) { e.preventDefault(); state.fresh = true; run(true); return; }
    if (t.closest("[data-cf-mine]")) { state.mine = !state.mine; run(state.mine); return; }
    var see = t.closest("[data-cf-see]");
    if (see) { e.preventDefault(); state.topic = see.getAttribute("data-cf-see"); run(true); return; }
    var tag = t.closest("[data-cs-tag]");
    if (tag) { q.value = tag.getAttribute("data-cs-tag"); state.q = q.value; run(true); return; }
    if (t.closest("[data-cf-clear]")) {
      q.value = ""; state = EMPTY();
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

  // ---------- "Suggest a write-up": the dialog, its instant checks, and sending it
  (function () {
    var dialog = document.querySelector("[data-sg]");
    var opener = document.querySelector("[data-sg-open]");
    if (!dialog || !opener || typeof dialog.showModal !== "function") { if (opener) opener.hidden = true; return; }
    var sgForm = dialog.querySelector("[data-sg-form]");
    var url = dialog.querySelector("[data-sg-url]");
    var msg = dialog.querySelector("[data-sg-url-msg]");
    var note = dialog.querySelector("[data-sg-note]");
    var count = dialog.querySelector("[data-sg-count]");
    var credit = dialog.querySelector("[data-sg-credit]");
    var hp = dialog.querySelector("[data-sg-hp]");
    var error = dialog.querySelector("[data-sg-error]");
    var send = dialog.querySelector("[data-sg-send]");
    var bodyEl = dialog.querySelector("[data-sg-body]");
    var thanks = dialog.querySelector("[data-sg-thanks]");
    var sending = false;

    // The same address rules as normalise_url() in case_studies.py and canonicalUrl() in the function
    function canonical(u) {
      u = String(u || "").trim().replace(/[?#].*$/, "").replace(/^http:\/\//i, "https://");
      u = u.replace(/^https:\/\/[^/]+/i, function (m) { return m.toLowerCase(); });
      return u.replace(/\/+$/, "");
    }
    var onSite = {};
    index.posts.forEach(function (p) { onSite[canonical(p.u)] = p; });

    // What the link field says: {state: "ok" | "dup" | "bad", text, post}
    function judge(raw) {
      var text = raw.trim();
      if (!text) return { state: "bad", text: "Add the link to the post so we can check it." };
      var u;
      try { u = new URL(text); } catch (e) { return { state: "bad", text: "We need the full link to the post, starting with https://" }; }
      if (u.protocol !== "https:") return { state: "bad", text: "We can only take https:// links." };
      var h = u.hostname.toLowerCase();
      if (u.username || u.password || h === "localhost" || h.indexOf(".") < 0 || /^[\d.]+$/.test(h) || h.indexOf(":") >= 0 ||
          /\.(local|internal|localhost)$/.test(h)) {
        return { state: "bad", text: "We can only take links to public websites." };
      }
      if (u.pathname.replace(/\/+$/, "") === "") return { state: "bad", text: "That\u2019s the blog\u2019s front page. Paste the link to the post itself." };
      var known = onSite[canonical(text)];
      if (known) return { state: "dup", text: "This one is already on the site", post: known };
      return { state: "ok", text: "\u2713 Looks like a blog post. Not in our list yet." };
    }
    function show(result, asError) {
      msg.className = "sg-msg" + (result ? " sg-" + result.state : "");
      url.setAttribute("aria-invalid", asError ? "true" : "false");
      if (!result) { msg.textContent = ""; return; }
      msg.textContent = result.text;
      if (result.state === "dup") {
        var a = document.createElement("a");
        a.href = "index.html?q=" + encodeURIComponent(result.post.t);
        a.textContent = "See it on the site";
        msg.appendChild(document.createTextNode(". "));
        msg.appendChild(a);
      }
    }
    url.addEventListener("input", function () {  // errors clear as soon as the link changes
      error.hidden = true;
      var r = judge(url.value);
      show(r.state === "bad" ? null : r, false);
    });
    url.addEventListener("blur", function () {
      if (!url.value.trim()) { show(null, false); return; }
      var r = judge(url.value);
      show(r, r.state === "bad");
    });
    note.addEventListener("input", function () { count.textContent = note.value.length + " / 280"; });

    function reset() {
      sgForm.reset();
      show(null, false);
      count.textContent = "0 / 280";
      error.hidden = true;
      bodyEl.hidden = false;
      thanks.hidden = true;
      send.disabled = false;
      send.textContent = "Send suggestion";
    }
    opener.addEventListener("click", function () {
      reset();
      dialog.showModal();
      url.focus();
    });
    dialog.addEventListener("close", function () { opener.focus(); });  // focus goes back to the button
    // Tab and Shift+Tab cycle inside the dialog instead of leaving it for the browser's own controls
    dialog.addEventListener("keydown", function (e) {
      if (e.key !== "Tab") return;
      var items = Array.prototype.slice.call(dialog.querySelectorAll("a[href], button, input, textarea, [tabindex='0']"))
        .filter(function (el) { return !el.disabled && !el.closest("[hidden]") && !el.closest(".sg-hp") && el.getClientRects().length; });
      if (!items.length) return;
      var first = items[0], last = items[items.length - 1], at = document.activeElement;
      if (e.shiftKey && (at === first || !dialog.contains(at) || at === thanks)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && (at === last || !dialog.contains(at))) { e.preventDefault(); first.focus(); }
    });
    dialog.addEventListener("click", function (e) {
      if (e.target === dialog) { dialog.close(); return; }  // a click on the backdrop
      var t = e.target.closest && e.target.closest("[data-sg-close], [data-sg-again]");
      if (!t) return;
      if (t.hasAttribute("data-sg-again")) { reset(); url.focus(); } else dialog.close();
    });
    sgForm.addEventListener("submit", function (e) {
      e.preventDefault();
      if (sending) return;
      var r = judge(url.value);
      if (r.state !== "ok") { show(r, r.state === "bad"); url.focus(); return; }
      sending = true;
      send.disabled = true;
      send.textContent = "Sending\u2026";
      error.hidden = true;
      fetch(sgForm.getAttribute("data-endpoint"), {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ url: url.value.trim(), note: note.value, credit: credit.value, website: hp.value })
      }).then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (body) { return { status: res.status, body: body }; });
      }).then(function (r2) {
        if (r2.status === 200 && r2.body.ok) {
          bodyEl.hidden = true;
          thanks.hidden = false;
          thanks.focus();
          return;
        }
        error.textContent = r2.body.error || "We couldn\u2019t send it just now. Please try again in a minute.";
        error.hidden = false;
      }).catch(function () {
        error.textContent = "We couldn\u2019t reach our server just now. Please try again in a minute.";
        error.hidden = false;
      }).then(function () {
        sending = false;
        send.disabled = false;
        send.textContent = "Send suggestion";
      });
    });
  })();

  paintFollows();

  // A shared link (?q=...&topic=...) opens with that search
  try {
    var params = new URLSearchParams(location.search);
    state.q = (params.get("q") || "").slice(0, 200);
    state.topic = index.topics[params.get("topic")] ? params.get("topic") : "";
    // Links from a case page's chips: ?tech=rag, ?ind=fintech; ?suggest=1 opens the suggestion form
    var tech = params.get("tech") || "", ind = params.get("ind") || "";
    if ((index.labels.x || {})[tech]) { state.tech = tech; if (menus.tech) menus.tech.value = tech; }
    if ((index.labels.n || {})[ind]) { state.ind = ind; if (menus.ind) menus.ind.value = ind; }
    q.value = state.q;
    if (active()) run(false);
    var opener = document.querySelector("[data-sg-open]");
    if (params.get("suggest") && opener && !opener.hidden) opener.click();
  } catch (e) { /* no URLSearchParams: start on the sections */ }
})(typeof window !== "undefined" ? window : this);
