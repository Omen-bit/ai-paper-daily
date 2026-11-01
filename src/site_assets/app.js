// AI Papers Daily: the only script on the site. No libraries.
// Everything personal (reading history, saved papers, text size, theme) stays in
// this browser's localStorage. Nothing is sent anywhere.
(function () {
  "use strict";
  var root = document.documentElement;
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  // ---- Small helpers ----
  function load(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) || fallback; } catch (e) { return fallback; }
  }
  function store(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* private mode: not remembered */ }
  }
  // Calls to our server functions give up after a while, so a slow or stuck
  // service never leaves a spinner running forever. The page then shows its
  // usual "try again" message, and everything that doesn't need the server keeps working.
  function callApi(url, options, ms) {
    if (!window.AbortController) return fetch(url, options);
    var ctl = new AbortController();
    var timer = setTimeout(function () { ctl.abort(); }, ms);
    options.signal = ctl.signal;
    return fetch(url, options).then(function (r) { clearTimeout(timer); return r; },
                                    function (e) { clearTimeout(timer); throw e; });
  }
  // An error worth showing as written: one our server sent in words. Anything else
  // (a timeout, no connection, a broken reply) gets the caller's own friendly message.
  function serverError(message) {
    var e = new Error(message);
    e.fromServer = true;
    return e;
  }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function ago(ms) {
    var min = Math.round((Date.now() - ms) / 60000);
    if (min < 1) return "just now";
    if (min < 60) return min + " min ago";
    var h = Math.round(min / 60);
    if (h < 24) return h + (h === 1 ? " hour ago" : " hours ago");
    var d = Math.round(h / 24);
    return d === 1 ? "yesterday" : d + " days ago";
  }
  // Briefly swap a button's label to confirm an action, then put it back
  function confirmLabel(button, text) {
    var label = button.querySelector("span") || button;
    var before = label.textContent;
    label.textContent = text;
    setTimeout(function () { label.textContent = before; }, 1800);
  }

  var reads = load("apd.history", []);
  var saved = load("apd.saved", []);
  var readIds = {};
  reads.forEach(function (h) { readIds[h.id] = true; });

  // ---- Theme toggle ----
  var toggle = document.querySelector("[data-theme-toggle]");
  if (toggle) {
    toggle.addEventListener("click", function () {
      var next = root.dataset.theme === "dark" ? "light" : "dark";
      root.dataset.theme = next;
      try { localStorage.setItem("apd.theme", next); } catch (e) { /* private mode */ }
    });
  }

  // ---- "/" jumps to search from anywhere ----
  document.addEventListener("keydown", function (e) {
    if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
    var tag = (document.activeElement && document.activeElement.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    e.preventDefault();
    var box = document.getElementById("q");
    if (box) { box.focus(); return; }
    var trigger = document.querySelector("[data-search-trigger]");
    if (trigger) location.href = trigger.getAttribute("href");
  });

  // ---- Saved count in the header ----
  function showSavedCount() {
    var el = document.querySelector("[data-saved-count]");
    if (!el) return;
    el.textContent = saved.length;
    el.hidden = saved.length === 0;
  }
  showSavedCount();

  // ---- Mark papers already read in any list ----
  function markRead(scope) {
    Array.prototype.forEach.call((scope || document).querySelectorAll(".row[data-id], .syl-row[data-id]"), function (row) {
      if (readIds[row.getAttribute("data-id")]) row.classList.add("is-read");
    });
  }
  markRead();

  // ---- Day key, used to cache For you once a day ----
  function dayKey(ms) {
    var d = new Date(ms);
    return d.getFullYear() + "-" + (d.getMonth() + 1) + "-" + d.getDate();
  }
  // ---- Ticker: time until the next edition (01:30 UTC every day) ----
  var nextEl = document.querySelector("[data-next-edition]");
  if (nextEl) {
    var tick = function () {
      var now = new Date(), next = new Date(now);
      next.setUTCHours(1, 30, 0, 0);
      if (next <= now) next.setUTCDate(next.getUTCDate() + 1);
      var mins = Math.floor((next - now) / 60000);
      nextEl.textContent = "Next edition in " + String(Math.floor(mins / 60)).padStart(2, "0") + ":" + String(mins % 60).padStart(2, "0");
    };
    tick();
    setInterval(tick, 30000);
  }

  // ---- Home: read marks on the pick cards ----
  Array.prototype.forEach.call(document.querySelectorAll(".pick[data-id]"), function (card) {
    if (readIds[card.getAttribute("data-id")]) card.querySelector(".pick-read").hidden = false;
  });
  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest("[data-quick-save]");
    if (!btn) return;
    var id = btn.getAttribute("data-quick-save");
    var on = saved.some(function (s) { return s.id === id; });
    saved = on ? saved.filter(function (s) { return s.id !== id; })
               : [{ id: id, t: btn.getAttribute("data-title"), at: Date.now() }].concat(saved);
    store("apd.saved", saved);
    btn.setAttribute("aria-pressed", on ? "false" : "true");
    btn.textContent = on ? "+" : "✓";
    showSavedCount();
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-quick-save]"), function (btn) {
    if (saved.some(function (s) { return s.id === btn.getAttribute("data-quick-save"); })) {
      btn.setAttribute("aria-pressed", "true");
      btn.textContent = "✓";
    }
  });

  // ---- Home: "For you", papers close in meaning to this browser's reading ----
  // Only the IDs of papers opened here are sent, to our own Supabase function.
  // Results are kept for the day so the function is not called on every visit.
  var forYou = document.querySelector("[data-foryou]");
  if (forYou && reads.length && window.fetch) {
    var fyIds = reads.slice(0, 50).map(function (h) { return h.id; });
    var fyKey = dayKey(Date.now()) + ":" + fyIds.slice(0, 20).join(",");
    var fyNames = {};
    try { fyNames = JSON.parse(forYou.getAttribute("data-names")) || {}; } catch (e) { /* plain slugs */ }
    var fyList = forYou.querySelector("[data-foryou-list]");
    var fySub = forYou.querySelector(".sub");
    var paintForYou = function (results, onSite) {
      if (!results || !results.length) { forYou.hidden = true; return; }
      fyList.innerHTML = results.slice(0, 6).map(function (p) {
        var topic = (p.categories && p.categories[0]) || "other-ml";
        var local = onSite[p.id];
        var href = local ? "paper/" + esc(p.id) + ".html" : "https://huggingface.co/papers/" + esc(p.id);
        var when = p.submitted || p.first_seen;
        var date = when ? new Date(String(when).slice(0, 10) + "T00:00:00") : null;
        var meta = (date ? "Published " + date.getDate() + " " + MONTHS[date.getMonth()] : "") +
          (isOlder(p) ? '<span class="sep"></span>Older paper, trending now' : "") +
          (p.code_url ? '<span class="sep"></span>Code available' : "") +
          (local ? "" : '<span class="sep"></span>On Hugging Face');
        return '<li class="foryou-item" data-id="' + esc(p.id) + '">' +
          '<span class="topic t-' + esc(topic) + '"><span class="dot"></span>' + esc(fyNames[topic] || topic) + "</span>" +
          '<a href="' + href + '"' + (local ? "" : ' rel="noopener"') + ">" + esc(p.title) + "</a>" +
          '<span class="foryou-meta">' + meta + "</span></li>";
      }).join("");
      fyList.removeAttribute("aria-busy");
      if (fySub) fySub.textContent = "Close in meaning to the " + (fyIds.length === 1 ? "paper" : fyIds.length + " papers") +
        " you’ve opened here. Worked out from this browser’s history only.";
      forYou.hidden = false;
    };
    var cached = load("apd.foryou", null);
    var idsReq = fetch("data/ids.json").then(function (r) { return r.ok ? r.json() : []; }).catch(function () { return []; });
    var recReq = cached && cached.key === fyKey ? Promise.resolve(cached.results) :
      callApi(forYou.getAttribute("data-url"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: fyIds, limit: 6, days: 30 })
      }, 15000).then(function (r) { return r.ok ? r.json() : { results: [] }; })
        .then(function (d) {
          var results = d.results || [];
          store("apd.foryou", { key: fyKey, results: results });
          return results;
        });
    forYou.hidden = false;
    Promise.all([recReq, idsReq]).then(function (both) {
      var onSite = {};
      (both[1] || []).forEach(function (id) { onSite[id] = true; });
      paintForYou(both[0], onSite);
    }).catch(function () { forYou.hidden = true; });
  }

  // ---- Watch a Scout project: new matching papers on the home page ----
  // Kept in this browser only. The home page checks once a day with search by meaning,
  // sending only the project's search phrases.
  var WATCH_MAX = 3;
  var NEW_MARGIN = 0.06;  // new papers must match a little better than Scout's floor
  var watchKey = function (text) {
    var h = 0;
    for (var i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) | 0;
    return "w" + (h >>> 0).toString(36);
  };
  var isoToday = function () { return new Date().toISOString().slice(0, 10); };
  var longDay = function (iso) {
    var d = new Date(String(iso || "").slice(0, 10) + "T00:00:00");
    return isNaN(d) ? "" : d.getDate() + " " + MONTHS[d.getMonth()] + " " + d.getFullYear();
  };
  // A paper that reached Hugging Face more than 30 days after arXiv: "older, trending now"
  var isOlder = function (p) {
    var a = new Date(String(p.submitted || "").slice(0, 10) + "T00:00:00");
    var b = new Date(String(p.first_seen || "").slice(0, 10) + "T00:00:00");
    return !isNaN(a) && !isNaN(b) && (b - a) / 864e5 > 30;
  };
  var publishedLine = function (p) {
    var when = longDay(p.submitted || p.first_seen);
    return (when ? '<span class="pub-date">Published ' + esc(when) + "</span>" : "") +
      (isOlder(p) ? '<span class="old-flag">Older paper, trending now</span>' : "");
  };
  var shortDay = function (iso) {
    var d = new Date(String(iso).slice(0, 10) + "T00:00:00");
    return isNaN(d) ? "" : d.getDate() + " " + MONTHS[d.getMonth()];
  };
  window.apdWatch = {
    list: function () { return load("apd.watch", []); },
    wire: function (btn, data, description) {
      var key = watchKey(description);
      var paint = function () {
        var on = window.apdWatch.list().some(function (w) { return w.key === key; });
        btn.setAttribute("aria-pressed", String(on));
        btn.textContent = on ? "Watching ✓" : "Watch this project";
        btn.classList.toggle("btn-primary", !on);
        btn.classList.toggle("btn-outline", on);
      };
      paint();
      btn.addEventListener("click", function () {
        var list = window.apdWatch.list();
        var on = list.some(function (w) { return w.key === key; });
        if (on) {
          list = list.filter(function (w) { return w.key !== key; });
        } else {
          var queries = (data.needs || []).slice(0, 2).map(function (n) { return n.query; });
          list.unshift({
            key: key, title: data.summary || description.slice(0, 140), description: description,
            queries: queries.length ? queries : [description.slice(0, 300)], floor: data.floor || 0.74,
            seen: (data.plan || []).map(function (p) { return p.id; }), since: isoToday()
          });
          list = list.slice(0, WATCH_MAX);
        }
        store("apd.watch", list);
        store("apd.watchnews", null);
        paint();
        if (!on) confirmLabel(btn, "Watching ✓ · new papers will show on the home page");
      });
    }
  };

  var watchBox = document.querySelector("[data-watch]");
  var watched = window.apdWatch.list();
  if (watchBox && watched.length && window.fetch) {
    var watchList = watchBox.querySelector("[data-watch-list]");
    var search = function (q, since) {
      return callApi(watchBox.getAttribute("data-url"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ q: q, limit: 10, since: since })
      }, 20000).then(function (r) { return r.ok ? r.json() : { results: [] }; })
        .then(function (d) { return d.results || []; }).catch(function () { return []; });
    };
    var newFor = function (w) {
      return Promise.all(w.queries.map(function (q) { return search(q, w.since); })).then(function (lists) {
        var best = {};
        lists.forEach(function (l) {
          l.forEach(function (p) {
            if (w.seen.indexOf(p.id) >= 0 || p.similarity < w.floor + NEW_MARGIN) return;
            if (!best[p.id] || best[p.id].similarity < p.similarity) best[p.id] = p;
          });
        });
        return Object.keys(best).map(function (id) { return best[id]; })
          .sort(function (a, b) { return b.similarity - a.similarity; }).slice(0, 3);
      });
    };
    var paintWatch = function (news, onSite) {
      var list = window.apdWatch.list();
      if (!list.length) { watchBox.hidden = true; return; }
      watchList.innerHTML = list.map(function (w) {
        var items = news[w.key] || [];
        return '<div class="card pad watch-card" data-key="' + esc(w.key) + '">' +
          '<div class="watch-head"><span class="label">Watching since ' + esc(shortDay(w.since)) + "</span>" +
          '<span class="watch-count' + (items.length ? " has-new" : "") + '">' + (items.length ? items.length + " new" : "Nothing new") + "</span></div>" +
          '<p class="watch-title">' + esc(w.title) + "</p>" +
          (items.length ? '<ol class="watch-items">' + items.map(function (p) {
            var local = onSite[p.id];
            return '<li><a href="' + (local ? "paper/" + esc(p.id) + ".html" : "https://huggingface.co/papers/" + esc(p.id)) + '"' +
              (local ? "" : ' rel="noopener"') + ">" + esc(p.title) + "</a>" +
              '<span class="foryou-meta">' + esc(shortDay(p.first_seen || p.submitted)) + (p.code_url ? '<span class="sep"></span>Code available' : "") + "</span></li>";
          }).join("") + "</ol>" : '<p class="watch-empty">No new papers fit yet. We check every day.</p>') +
          '<div class="watch-actions"><a class="text-link" href="scout.html" data-rescout>Run Scout again</a>' +
          '<button class="text-link" type="button" data-unwatch>Stop watching</button></div></div>';
      }).join("");
      Array.prototype.forEach.call(watchList.querySelectorAll(".watch-card"), function (card) {
        var key = card.getAttribute("data-key");
        var w = list.filter(function (x) { return x.key === key; })[0];
        card.querySelector("[data-unwatch]").addEventListener("click", function () {
          store("apd.watch", window.apdWatch.list().filter(function (x) { return x.key !== key; }));
          card.remove();
          if (!window.apdWatch.list().length) watchBox.hidden = true;
        });
        card.querySelector("[data-rescout]").addEventListener("click", function () { store("apd.scoutdraft", w.description); });
      });
      watchList.removeAttribute("aria-busy");
      watchBox.hidden = false;
    };
    var cachedNews = load("apd.watchnews", null);
    var newsReq = cachedNews && cachedNews.day === isoToday() ? Promise.resolve(cachedNews.items) :
      Promise.all(watched.map(newFor)).then(function (all) {
        var items = {};
        watched.forEach(function (w, i) { items[w.key] = all[i]; });
        store("apd.watchnews", { day: isoToday(), items: items });
        return items;
      });
    watchBox.hidden = false;
    Promise.all([newsReq, fetch("data/ids.json").then(function (r) { return r.ok ? r.json() : []; }).catch(function () { return []; })])
      .then(function (both) {
        var onSite = {};
        (both[1] || []).forEach(function (id) { onSite[id] = true; });
        paintWatch(both[0] || {}, onSite);
      }).catch(function () { watchBox.hidden = true; });
  }

  // ---- Paper page ----
  var article = document.querySelector("[data-paper-id]");
  if (article) {
    var id = article.getAttribute("data-paper-id");
    var title = article.getAttribute("data-title");

    // Remember the visit (powers Continue reading and, later, For you)
    reads = reads.filter(function (h) { return h.id !== id; });
    reads.unshift({ id: id, t: title, at: Date.now(), c: (article.getAttribute("data-topics") || "").split(" ").filter(Boolean) });
    store("apd.history", reads.slice(0, 500));
    readIds[id] = true;

    // Save for later
    var saveBtn = document.querySelector("[data-save]");
    var paintSave = function () {
      var on = saved.some(function (s) { return s.id === id; });
      saveBtn.setAttribute("aria-pressed", on ? "true" : "false");
      saveBtn.querySelector("span").textContent = on ? "Saved" : "Save";
    };
    saveBtn.addEventListener("click", function () {
      var on = saved.some(function (s) { return s.id === id; });
      saved = on ? saved.filter(function (s) { return s.id !== id; })
                 : [{ id: id, t: title, at: Date.now() }].concat(saved);
      store("apd.saved", saved);
      paintSave();
      showSavedCount();
    });
    paintSave();

    // Share: the system share sheet on phones, copy the link elsewhere
    document.querySelector("[data-share]").addEventListener("click", function () {
      var btn = this;
      if (navigator.share) {
        navigator.share({ title: title, url: location.href }).catch(function () {});
      } else if (navigator.clipboard) {
        navigator.clipboard.writeText(location.href).then(function () { confirmLabel(btn, "Link copied"); });
      }
    });

    // Cite: copy BibTeX; Esc closes the box and returns focus to its button
    var cite = document.querySelector(".cite");
    var copyBtn = document.querySelector("[data-copy-bibtex]");
    copyBtn.addEventListener("click", function () {
      var text = document.querySelector("[data-bibtex]").textContent;
      if (navigator.clipboard) navigator.clipboard.writeText(text).then(function () { confirmLabel(copyBtn, "Copied"); });
    });

    // Text size, remembered across papers
    var SIZES = [0.9, 1, 1.1, 1.2, 1.32];
    var size = load("apd.textsize", 1);
    var paintSize = function () { document.documentElement.style.setProperty("--reader-scale", SIZES[size]); };
    paintSize();
    Array.prototype.forEach.call(document.querySelectorAll("[data-size]"), function (b) {
      b.addEventListener("click", function () {
        size = Math.max(0, Math.min(SIZES.length - 1, size + Number(b.getAttribute("data-size"))));
        store("apd.textsize", size);
        paintSize();
      });
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && cite && cite.open) { cite.open = false; cite.querySelector("summary").focus(); }
    });

    // Check yourself
    var showAnswer = document.querySelector("[data-check-show]");
    if (showAnswer) {
      showAnswer.addEventListener("click", function () {
        document.querySelector("[data-check-answer]").hidden = false;
        showAnswer.hidden = true;
      });
    }

    // Section list: marks the section being read
    var layers = document.querySelectorAll("[data-layer]");
    var tocLinks = {};
    Array.prototype.forEach.call(document.querySelectorAll("[data-toc]"), function (a) { tocLinks[a.getAttribute("data-toc")] = a; });
    var ticking = false;
    var update = function () {
      var current = null;
      Array.prototype.forEach.call(layers, function (s) {
        var r = s.getBoundingClientRect();
        var link = tocLinks[s.id];
        if (!link) return;
        link.classList.toggle("done", r.bottom < window.innerHeight * 0.35);
        if (r.top < window.innerHeight * 0.5) current = link;
      });
      Array.prototype.forEach.call(Object.keys(tocLinks), function (k) { tocLinks[k].classList.remove("now"); });
      if (current && !current.classList.contains("done")) current.classList.add("now");
      ticking = false;
    };
    window.addEventListener("scroll", function () {
      if (!ticking) { ticking = true; requestAnimationFrame(update); }
    }, { passive: true });
    update();

    // Highlights and notes, kept in this browser per paper
    var prose = document.querySelector("[data-highlightable]");
    var notesKey = "apd.notes";
    var allNotes = load(notesKey, {});
    var mine = allNotes[id] || [];
    var list = document.querySelector("[data-notes-list]");
    var emptyNote = document.querySelector("[data-notes-empty]");
    var original = prose ? prose.innerHTML : "";

    var paintHighlights = function () {
      if (!prose) return;
      prose.innerHTML = original;
      mine.forEach(function (n, i) {
        // Wrap the first plain-text match of each highlight
        var walker = document.createTreeWalker(prose, NodeFilter.SHOW_TEXT);
        var node;
        while ((node = walker.nextNode())) {
          var at = node.nodeValue.indexOf(n.text);
          if (at < 0 || node.parentNode.closest("mark")) continue;
          var range = document.createRange();
          range.setStart(node, at);
          range.setEnd(node, at + n.text.length);
          var mark = document.createElement("mark");
          mark.className = "hl";
          mark.setAttribute("data-note-i", i);
          range.surroundContents(mark);
          break;
        }
      });
      list.innerHTML = mine.map(function (n, i) {
        return "<li><blockquote>" + esc(n.text) + "</blockquote>" + (n.note ? "<p>" + esc(n.note) + "</p>" : "") +
          '<button type="button" data-note-remove="' + i + '">Remove</button></li>';
      }).join("");
      emptyNote.hidden = mine.length > 0;
    };
    var saveNotes = function () {
      allNotes = load(notesKey, {});
      if (mine.length) allNotes[id] = mine; else delete allNotes[id];
      store(notesKey, allNotes);
      paintHighlights();
    };
    list.addEventListener("click", function (e) {
      var i = e.target.getAttribute && e.target.getAttribute("data-note-remove");
      if (i === null || i === undefined) return;
      mine.splice(Number(i), 1);
      saveNotes();
    });

    if (prose) {
      var pop = document.createElement("div");
      pop.className = "sel-pop";
      pop.hidden = true;
      pop.innerHTML = '<button type="button" class="sel-hl" data-act="hl">Highlight</button><button type="button" data-act="note">Add note</button><button type="button" data-act="copy">Copy</button>' +
        (document.querySelector("[data-ask]") ? '<button type="button" class="sel-ask" data-act="ask">Ask</button>' : "");
      prose.parentNode.appendChild(pop);
      var picked = "";
      var hidePop = function () { pop.hidden = true; };
      var showPop = function () {
        var sel = window.getSelection();
        var text = sel && sel.toString().replace(/\s+/g, " ").trim();
        if (!text || text.length < 3 || !sel.rangeCount || !prose.contains(sel.anchorNode) || !prose.contains(sel.focusNode)) return hidePop();
        picked = text;
        var r = sel.getRangeAt(0).getBoundingClientRect();
        var box = prose.parentNode.getBoundingClientRect();
        pop.style.left = (r.left + r.width / 2 - box.left) + "px";
        pop.style.top = (r.top - box.top - 8) + "px";
        pop.hidden = false;
      };
      prose.addEventListener("mouseup", function () { setTimeout(showPop, 0); });
      prose.addEventListener("keyup", function (e) { if (e.shiftKey) showPop(); });
      document.addEventListener("mousedown", function (e) { if (!pop.contains(e.target)) hidePop(); });
      pop.addEventListener("click", function (e) {
        var act = e.target.getAttribute("data-act");
        if (act === "copy" && navigator.clipboard) navigator.clipboard.writeText(picked);
        if (act === "ask" && window.apdAsk) {
          var quote = picked.length > 220 ? picked.slice(0, 217) + "…" : picked;
          window.apdAsk("Explain this part in plain words: “" + quote + "”");
        }
        if (act === "hl" || act === "note") {
          var note = act === "note" ? (window.prompt("Your note on this passage") || "") : "";
          if (act === "note" && !note) return hidePop();
          mine.push({ text: picked, note: note.trim(), at: Date.now() });
          saveNotes();
        }
        window.getSelection().removeAllRanges();
        hidePop();
      });
    }
    paintHighlights();
  }

  // ---- Paper page: the full breakdown, copied from the paper itself ----
  var bd = document.querySelector("[data-breakdown]");
  if (bd && window.fetch) {
    var bdId = bd.getAttribute("data-breakdown");
    var bdUrl = bd.getAttribute("data-url");
    var bdWantSummary = bd.hasAttribute("data-summary");
    var bdOut = bd.querySelector("[data-bd-out]");
    var bdBtn = bd.querySelector("[data-bd-load]");
    var bdNote = bd.querySelector("[data-bd-note]");
    var bdShort = document.querySelector("[data-bd-short]");
    var bdLayer = bd.closest("[data-layer]");
    var bdCall = function (extra) {
      var payload = { id: bdId, summary: bdWantSummary };
      for (var k in extra) payload[k] = extra[k];
      return callApi(bdUrl, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }, 45000)
        .then(function (r) {
          return r.json().catch(function () { return {}; }).then(function (d) {
            if (!r.ok || !d.status) throw serverError(d.error || "");
            return d;
          });
        });
    };
    var quoted = function (title, q) {
      return '<h3>' + title + '</h3><blockquote class="bd-quote">' + esc(q.text) + '</blockquote>' +
        '<p class="bd-src">From the section “' + esc(q.heading) + '”</p>';
    };
    var paintBreakdown = function (d) {
      if (d.status === "none") {
        bdBtn.hidden = true;
        bdNote.textContent = "arXiv has no web version of this paper yet, so there’s no breakdown. The PDF has everything.";
        return;
      }
      var b = d.breakdown || {}, html = "";
      if (b.contributions && b.contributions.length) {
        html += '<h3>What they contribute</h3><ul class="bd-list">' + b.contributions.map(function (c) { return "<li>" + esc(c) + "</li>"; }).join("") + "</ul>";
      }
      if (b.tables && b.tables.length) {
        html += "<h3>Key results</h3>" + b.tables.map(function (t) {
          var rows = t.rows.map(function (r, i) {
            var tag = i === 0 ? "th" : "td";
            return "<tr>" + r.map(function (c) { return "<" + tag + ">" + esc(c) + "</" + tag + ">"; }).join("") + "</tr>";
          }).join("");
          return '<figure class="bd-table"><div class="bd-scroll" tabindex="0"><table>' + rows + "</table></div>" +
            (t.caption ? "<figcaption>" + esc(t.caption) + "</figcaption>" : "") + "</figure>";
        }).join("");
      }
      if (b.limitations) html += quoted("Limitations", b.limitations);
      if (b.conclusion) html += quoted("Conclusion", b.conclusion);
      if (b.links && b.links.length) {
        html += '<h3>Links in the paper</h3><ul class="bd-links">' + b.links.map(function (u) {
          return '<li><a href="' + esc(u) + '" rel="noopener" data-out="code">' + esc(u.replace(/^https?:\/\/(www\.)?/, "")) + "</a></li>";
        }).join("") + "</ul>";
      }
      bdOut.innerHTML = html;
      bdBtn.hidden = true;
      bdNote.textContent = "Copied from the paper by our code, not written by AI. Tables may lose some formatting.";
      if (d.summary && bdShort) {
        bdShort.querySelector("[data-bd-short-text]").textContent = d.summary;
        bdShort.hidden = false;
      }
    };
    var bdMake = function () {
      bdBtn.disabled = true;
      bdBtn.textContent = "Reading the paper on arXiv…";
      track("site", "breakdown_load");
      bdCall({}).then(paintBreakdown).catch(function (e) {
        bdBtn.disabled = false;
        bdBtn.textContent = "Try again";
        bdNote.textContent = e.fromServer && e.message ? e.message : "Couldn’t read the paper right now. Try again in a minute.";
      });
    };
    bdBtn.addEventListener("click", bdMake);
    bdCall({ peek: true }).then(function (d) {
      if (d.status === "missing") { bdBtn.hidden = false; return; }
      paintBreakdown(d);
      // Saved before anyone asked for a summary: make it now (once per paper, capped per day)
      if (d.status === "ready" && d.summaryLater && bdWantSummary) bdCall({}).then(function (x) { if (x.summary) paintBreakdown(x); }).catch(function () {});
    }).catch(function () {
      if (bdLayer) bdLayer.hidden = true; // the service is down: leave the page as it was
    });
  }
  document.addEventListener("click", function (e) {
    var out = e.target.closest && e.target.closest("[data-out]");
    if (out && document.querySelector("[data-paper-id]")) track("site", "out_" + out.getAttribute("data-out"));
  });

  // ---- Paper page: "Ask this paper" ----
  var ask = document.querySelector("[data-ask]");
  var askPaper = document.querySelector("[data-paper-id]");
  if (ask && askPaper) {
    var askForm = ask.querySelector("[data-ask-form]");
    var askInput = document.getElementById("ask-q");
    var askLog = ask.querySelector("[data-ask-log]");
    var askErr = ask.querySelector("[data-ask-error]");
    var askBtn = askForm.querySelector("button");
    var lastTurn = null;

    // Find a sentence of the abstract and mark it for a moment
    var showInAbstract = function (sentence) {
      var prose = document.querySelector("[data-prose]");
      if (!prose) return;
      var probe = sentence.slice(0, 40);
      var walker = document.createTreeWalker(prose, NodeFilter.SHOW_TEXT);
      var node;
      while ((node = walker.nextNode())) {
        var at = node.nodeValue.indexOf(probe);
        if (at < 0) continue;
        var range = document.createRange();
        range.setStart(node, at);
        range.setEnd(node, Math.min(node.nodeValue.length, at + sentence.length));
        var mark = document.createElement("mark");
        mark.className = "flash";
        try { range.surroundContents(mark); } catch (e) { break; }
        mark.scrollIntoView({ behavior: "smooth", block: "center" });
        setTimeout(function () {
          var parent = mark.parentNode;
          while (mark.firstChild) parent.insertBefore(mark.firstChild, mark);
          parent.removeChild(mark);
          parent.normalize();
        }, 2600);
        return;
      }
      document.getElementById("l-abstract").scrollIntoView({ behavior: "smooth", block: "start" });
    };

    var askQuestion = function (question) {
      question = question.replace(/\s+/g, " ").trim();
      if (question.length < 4) { askErr.textContent = "Type a question first."; askErr.hidden = false; return; }
      askErr.hidden = true;
      var turn = document.createElement("li");
      turn.className = "ask-turn";
      turn.innerHTML = '<p class="ask-q">' + esc(question) + '</p><div class="ask-a is-loading"><span class="pixbar pixbar-run" aria-hidden="true">' +
        new Array(7).join("<i></i>") + '</span><span class="ask-wait">Reading the paper…</span></div>';
      // The first question on a paper reads the whole thing from arXiv, which takes a few seconds
      var slow = setTimeout(function () {
        var w = turn.querySelector(".ask-wait");
        if (w) w.textContent = "Reading the full paper for the first time. This takes a few seconds, and later questions are instant.";
      }, 2500);
      askLog.appendChild(turn);
      askLog.scrollTop = askLog.scrollHeight;
      askInput.value = "";
      askBtn.disabled = true;
      callApi(ask.getAttribute("data-url"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: askPaper.getAttribute("data-paper-id"), question: question, previous: lastTurn })
      }, 60000).then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok, data: d }; });
      }).then(function (res) {
        clearTimeout(slow);
        var box = turn.querySelector(".ask-a");
        box.classList.remove("is-loading");
        if (!res.ok || typeof res.data.answer !== "string") {
          box.classList.add("is-error");
          box.textContent = res.data.error || "Couldn’t answer that right now. Try again in a minute.";
          return;
        }
        var d = res.data;
        var fromAbstract = !d.section || d.section === "Abstract";
        var quote = "";
        if (d.quote && fromAbstract) {
          quote = '<button class="ask-quote" type="button"><span class="label">From the abstract</span>“' + esc(d.quote) + "”</button>";
        } else if (d.quote) {
          // A sentence from the full paper: open it on arXiv
          quote = '<a class="ask-quote" href="https://arxiv.org/html/' + esc(askPaper.getAttribute("data-paper-id")) +
            '" target="_blank" rel="noopener"><span class="label">From the paper · ' + esc(d.section) + "</span>“" + esc(d.quote) + "”</a>";
        } else if (d.answerable) {
          quote = '<p class="ask-note">Not tied to one sentence of the paper, so check it before relying on this.</p>';
        }
        var only = d.mode === "abstract" ? '<p class="ask-note">Answered from the abstract only: the full paper couldn’t be read.</p>' : "";
        box.innerHTML = "<p>" + esc(d.answer) + "</p>" + quote + only;
        var qb = box.querySelector("button.ask-quote");
        if (qb) qb.addEventListener("click", function () { showInAbstract(d.quote); });
        lastTurn = d.answerable ? { q: question, a: d.answer } : null;
        askLog.scrollTop = askLog.scrollHeight;
      }).catch(function () {
        clearTimeout(slow);
        var box = turn.querySelector(".ask-a");
        box.classList.remove("is-loading");
        box.classList.add("is-error");
        box.textContent = navigator.onLine === false ? "You’re offline. Reconnect and ask again." :
          "That took too long or the connection dropped. Please ask again.";
      }).then(function () { askBtn.disabled = false; });
    };

    // On smaller screens the panel is a sheet behind the "Ask this paper" button
    var askFab = document.querySelector("[data-ask-open]");
    var openAsk = function (focus) {
      ask.classList.add("is-open");
      if (askFab) askFab.setAttribute("aria-expanded", "true");
      if (focus) askInput.focus();
    };
    var closeAsk = function () {
      ask.classList.remove("is-open");
      if (askFab) { askFab.setAttribute("aria-expanded", "false"); askFab.focus(); }
    };
    if (askFab) askFab.addEventListener("click", function () { openAsk(true); });
    ask.querySelector("[data-ask-close]").addEventListener("click", closeAsk);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && ask.classList.contains("is-open")) closeAsk();
    });
    window.apdAsk = function (question) { openAsk(false); askQuestion(question); };

    askForm.addEventListener("submit", function (e) { e.preventDefault(); askQuestion(askInput.value); });
    askInput.addEventListener("input", function () { askErr.hidden = true; });
    Array.prototype.forEach.call(ask.querySelectorAll("[data-ask-suggest]"), function (b) {
      b.addEventListener("click", function () { askQuestion(b.textContent); });
    });
  }

  // ---- Anonymous counts: views for "Most read", and the feedback buttons ----
  // Only the paper ID and the kind of event are sent. Each browser counts a
  // paper once, and only after 15 seconds on its page.
  var trackMeta = document.querySelector('meta[name="apd-track"]');
  function track(id, event) {
    if (!trackMeta || !window.fetch || /localhost|127\.0\.0\.1/.test(location.hostname) && !window.APD_TRACK_LOCAL) return;
    fetch(trackMeta.content, {
      method: "POST", keepalive: true,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: id, event: event })
    }).catch(function () { /* counts are best effort */ });
  }
  var viewedPaper = document.querySelector("[data-paper-id]");
  if (viewedPaper) {
    var viewed = load("apd.viewed", []);
    var vid = viewedPaper.getAttribute("data-paper-id");
    if (viewed.indexOf(vid) < 0) {
      setTimeout(function () {
        if (document.visibilityState === "hidden") return;
        viewed = [vid].concat(viewed).slice(0, 1000);
        store("apd.viewed", viewed);
        track(vid, "view");
      }, 15000);
    }
  }
  function wireFeedback(box) {
    var fid = box.getAttribute("data-feedback");
    var votes = load("apd.feedback", {});
    var paintVote = function () {
      var v = votes[fid];
      Array.prototype.forEach.call(box.querySelectorAll("[data-vote]"), function (b) {
        b.setAttribute("aria-pressed", b.getAttribute("data-vote") === v ? "true" : "false");
        b.disabled = !!v;
      });
      if (v) box.querySelector("[data-feedback-q]").textContent = "Thanks. This helps us pick better papers.";
    };
    box.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("[data-vote]");
      if (!b || votes[fid]) return;
      votes = load("apd.feedback", {});
      votes[fid] = b.getAttribute("data-vote");
      store("apd.feedback", votes);
      track(fid, votes[fid]);
      paintVote();
    });
    paintVote();
  }
  Array.prototype.forEach.call(document.querySelectorAll("[data-feedback]"), wireFeedback);

  // ---- Site-wide counts: is our pick worth choosing over Hugging Face? ----
  // Sent as totals only, with id "site": one visit per browser per day (new,
  // back within a week, or back after longer), the first click on each
  // featured card, and the answer to "Seen this paper before today?".
  function slotKey(el) { return (el.getAttribute("data-slot") || "").replace(/-/g, "_"); }
  (function countVisit() {
    var today = new Date().toISOString().slice(0, 10);
    var last = load("apd.lastVisit", "");
    if (last === today) return;
    store("apd.lastVisit", today);
    var gap = last ? (Date.parse(today) - Date.parse(last)) / 86400000 : -1;
    track("site", gap < 0 || isNaN(gap) ? "visit_new" : gap <= 7 ? "visit_return_7d" : "visit_return_old");
    track("site", "src_" + visitSource());
  })();

  // Where today's first visit came from: a ?ref= tag on our own links (rss,
  // newsletter, a launch post), else the referring site's name. Only that
  // one word is sent, never the address.
  function visitSource() {
    var known = ["google", "bing", "duckduckgo", "hn", "reddit", "x", "linkedin", "github",
                 "producthunt", "discord", "telegram", "newsletter", "rss"];
    var params = new URLSearchParams(location.search);
    var tag = (params.get("ref") || params.get("utm_source") || "").toLowerCase();
    if (tag) {
      if (/buttondown|email|newsletter/.test(tag)) tag = "newsletter";
      if (tag === "twitter") tag = "x";
      if (tag === "hackernews" || tag === "ycombinator") tag = "hn";
      return known.indexOf(tag) >= 0 ? tag : "other";
    }
    var host = "";
    try { host = document.referrer ? new URL(document.referrer).hostname.replace(/^www\./, "") : ""; } catch (e) { host = ""; }
    if (!host || host === location.hostname) return "direct";
    var rules = [
      [/(^|\.)google\./, "google"], [/(^|\.)bing\.com$/, "bing"], [/(^|\.)duckduckgo\.com$/, "duckduckgo"],
      [/^news\.ycombinator\.com$/, "hn"], [/(^|\.)reddit\.com$/, "reddit"],
      [/^(t\.co|x\.com|twitter\.com|mobile\.twitter\.com)$/, "x"], [/(^|\.)(linkedin\.com|lnkd\.in)$/, "linkedin"],
      [/(^|\.)github\.com$/, "github"], [/(^|\.)producthunt\.com$/, "producthunt"],
      [/(^|\.)discord(app)?\.com$/, "discord"], [/^(t\.me|web\.telegram\.org)$/, "telegram"]
    ];
    for (var i = 0; i < rules.length; i++) if (rules[i][0].test(host)) return rules[i][1];
    return "other";
  }
  // Drop the tag from the address bar, so a reader who shares the link doesn't pass it on
  (function dropRefTag() {
    if (!window.history || !history.replaceState || !/[?&](ref|utm_[a-z]+)=/.test(location.search)) return;
    var params = new URLSearchParams(location.search);
    ["ref", "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"].forEach(function (k) { params.delete(k); });
    var q = params.toString();
    history.replaceState(history.state, "", location.pathname + (q ? "?" + q : "") + location.hash);
  })();

  // Sign-ups: the RSS link and the email form, counted as totals like everything else
  document.addEventListener("click", function (e) {
    if (e.target.closest && e.target.closest('[data-subscribe="rss"]')) track("site", "subscribe_rss");
  });

  // ---- Email sign-up without leaving the page ----
  // The form goes to Buttondown in the background; the box then asks the reader to
  // confirm from their inbox. "apd.subscribed" remembers it in this browser only, so
  // the box shrinks to one line and the header button goes away on later visits.
  var subbed = load("apd.subscribed", null);
  function showSubscribed() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-sub-box]"), function (box) {
      box.hidden = true;
      var mini = box.nextElementSibling;
      if (mini && mini.hasAttribute("data-sub-mini")) mini.hidden = false;
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-sub-jump]"), function (a) { a.hidden = true; });
  }
  if (document.querySelector("[data-sub-confirmed]")) {
    // The confirm link in the email lands here
    if (!subbed || !subbed.confirmed) track("site", "subscribe_confirmed");
    subbed = { at: (subbed && subbed.at) || Date.now(), confirmed: true };
    store("apd.subscribed", subbed);
  }
  if (subbed) showSubscribed();

  function sendSignup(form) {
    // Sent like a normal form post. Buttondown's endpoint gives no readable reply to
    // other sites, so a sent request counts as done; if the network fails we fall
    // back to its own page in a new tab
    var data = new URLSearchParams(new FormData(form));
    return fetch(form.action, { method: "POST", mode: "no-cors", body: data });
  }
  Array.prototype.forEach.call(document.querySelectorAll("[data-subscribe-form]"), function (form) {
    var box = form.closest("[data-sub-box]");
    form.addEventListener("submit", function (e) {
      if (!window.fetch || !window.FormData || !box) return; // old browsers: Buttondown's page in a new tab
      e.preventDefault();
      var email = form.querySelector('input[type="email"]').value.trim();
      var button = form.querySelector('button[type="submit"]');
      button.disabled = true;
      sendSignup(form).then(function () {
        track("site", "subscribe_email");
        store("apd.subscribed", { at: Date.now(), confirmed: false });
        box.querySelector("[data-sub-email]").textContent = email;
        box.querySelector("[data-sub-ask]").hidden = true;
        box.querySelector("[data-sub-done]").hidden = false;
        Array.prototype.forEach.call(document.querySelectorAll("[data-sub-jump]"), function (a) { a.hidden = true; });
      }, function () {
        button.disabled = false;
        form.submit();
      });
    });
    var resend = box && box.querySelector("[data-sub-resend]");
    if (resend) resend.addEventListener("click", function () {
      resend.disabled = true;
      sendSignup(form).then(function () { resend.textContent = "sent again"; }, function () { resend.disabled = false; });
    });
  });

  // Header button: jump to the sign-up box on this page, or the home page's
  Array.prototype.forEach.call(document.querySelectorAll("[data-sub-jump]"), function (a) {
    a.addEventListener("click", function (e) {
      var box = document.getElementById("subscribe");
      if (!box || box.hidden) return;
      e.preventDefault();
      box.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
      var input = box.querySelector('input[type="email"]');
      if (input) input.focus({ preventScroll: true });
    });
  });
  if (location.hash === "#subscribe") {
    var jumpInput = document.querySelector('#subscribe:not([hidden]) input[type="email"]');
    if (jumpInput) setTimeout(function () { jumpInput.focus({ preventScroll: true }); }, 300);
  }
  document.addEventListener("click", function (e) {
    var card = e.target.closest && e.target.closest("article.pick[data-slot]");
    if (!card || !slotKey(card) || e.target.closest("[data-seen]")) return;
    var clicked = load("apd.pickClicks", []);
    var cid = card.getAttribute("data-id");
    if (clicked.indexOf(cid) >= 0) return;
    store("apd.pickClicks", [cid].concat(clicked).slice(0, 200));
    track("site", "click_" + slotKey(card));
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-seen]"), function (box) {
    var card = box.closest("article.pick[data-slot]");
    var sid = box.getAttribute("data-seen");
    var paint = function () {
      var v = load("apd.seen", {})[sid];
      Array.prototype.forEach.call(box.querySelectorAll("[data-seen-vote]"), function (b) {
        b.setAttribute("aria-pressed", b.getAttribute("data-seen-vote") === v ? "true" : "false");
        b.disabled = !!v;
      });
      if (v) box.querySelector("[data-seen-q]").textContent = "Thanks, noted.";
    };
    box.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("[data-seen-vote]");
      var answers = load("apd.seen", {});
      if (!b || !card || answers[sid]) return;
      answers[sid] = b.getAttribute("data-seen-vote");
      store("apd.seen", answers);
      track("site", "seen_" + slotKey(card) + "_" + answers[sid]);
      paint();
    });
    paint();
  });

  // ---- Trends: show every technology in the leaderboard ----
  Array.prototype.forEach.call(document.querySelectorAll("[data-board-all]"), function (btn) {
    var wrap = btn.closest(".tech-board-wrap");
    var label = btn.textContent;
    btn.addEventListener("click", function () {
      var open = wrap.hasAttribute("data-all");
      if (open) wrap.removeAttribute("data-all"); else wrap.setAttribute("data-all", "");
      btn.setAttribute("aria-expanded", String(!open));
      btn.textContent = open ? label : "Show fewer";
    });
  });

  // ---- Trends: you vs the field, from this browser's reading history ----
  var youField = document.querySelector("[data-you-field]");
  if (youField) {
    var mine = {}, counted = 0;
    reads.forEach(function (h) {
      if (!h.c || !h.c.length) return;
      counted++;
      h.c.forEach(function (c) { mine[c] = (mine[c] || 0) + 1 / h.c.length; });
    });
    if (counted >= 3) {
      var field = {}, ynames = {};
      try { field = JSON.parse(youField.getAttribute("data-field")) || {}; } catch (e) { /* none */ }
      try { ynames = JSON.parse(youField.getAttribute("data-names")) || {}; } catch (e) { /* slugs */ }
      var topics = Object.keys(mine).concat(Object.keys(field)).filter(function (t, i, a) { return a.indexOf(t) === i; });
      topics = topics.map(function (t) { return { t: t, you: (mine[t] || 0) / counted, field: field[t] || 0 }; })
        .sort(function (a, b) { return (b.you + b.field) - (a.you + a.field); }).slice(0, 6);
      var max = Math.max.apply(null, topics.map(function (x) { return Math.max(x.you, x.field); })) || 1;
      var pctTxt = function (v) { return Math.round(v * 100) + "%"; };
      youField.querySelector("[data-you-chart]").innerHTML =
        '<p class="you-key"><span><i class="k-you"></i>You, ' + counted + " papers</span><span><i class=\"k-field\"></i>The field</span></p>" +
        '<ol class="you-bars">' + topics.map(function (x) {
          return '<li><span class="topic t-' + esc(x.t) + '"><span class="dot"></span>' + esc(ynames[x.t] || x.t) + "</span>" +
            '<span class="bars" aria-label="You ' + pctTxt(x.you) + ", the field " + pctTxt(x.field) + '">' +
            '<span class="bar-row"><span class="bar-you" style="width:' + (x.you / max * 85).toFixed(1) + '%"></span>' + pctTxt(x.you) + "</span>" +
            '<span class="bar-row"><span class="bar-field" style="width:' + (x.field / max * 85).toFixed(1) + '%"></span>' + pctTxt(x.field) + "</span></span></li>";
        }).join("") + "</ol>";
      youField.querySelector("[data-you-chart]").hidden = false;
      youField.querySelector("[data-you-empty]").hidden = true;
    }
  }

  // ---- Lists built from this browser's history or saved papers ----
  function storedRow(item, verb, removable) {
    return '<li class="row" data-id="' + esc(item.id) + '">' +
      '<span class="row-title"><a href="paper/' + esc(item.id) + '.html">' + esc(item.t || item.id) + "</a></span>" +
      '<span class="row-authors">' + verb + " " + ago(item.at) + "</span>" +
      (removable ? '<div class="badges"><button class="btn btn-outline btn-sm" type="button" data-remove="' + esc(item.id) + '">Remove</button></div>' : "") +
      "</li>";
  }

  var cont = document.querySelector("[data-continue]");
  if (cont && reads.length) {
    cont.querySelector("[data-continue-list]").innerHTML =
      reads.slice(0, 3).map(function (h) { return storedRow(h, "Opened", false); }).join("");
    cont.hidden = false;
  }

  var savedList = document.querySelector("[data-saved-list]");
  if (savedList) {
    var empty = document.querySelector("[data-saved-empty]");
    var paintSaved = function () {
      savedList.innerHTML = saved.map(function (s) { return storedRow(s, "Saved", true); }).join("");
      savedList.hidden = saved.length === 0;
      empty.hidden = saved.length !== 0;
      markRead(savedList);
    };
    savedList.addEventListener("click", function (e) {
      var rid = e.target.getAttribute && e.target.getAttribute("data-remove");
      if (!rid) return;
      saved = saved.filter(function (s) { return s.id !== rid; });
      store("apd.saved", saved);
      paintSaved();
      showSavedCount();
    });
    paintSaved();
  }

  // ---- Project Scout: describe a project, get a reading plan ----
  // Same rules as looksLikeCode() in supabase/functions/_shared/scout.ts.
  var CODE_PATTERNS = [
    /```/, /^\s*(import|from)\s+[\w.]+(\s+import\b|\s*;|\s*$)/m, /^\s*(def|class)\s+\w+\s*[(:]/m,
    /^\s*return\b[^.!?]*$/m, /\bfunction\s*\w*\s*\([^)]*\)\s*\{/, /=>\s*\{/, /^\s*#include\s*</m,
    /\b(console\.log|print)\s*\(/, /<\/?[a-z][\w-]*(\s[^>]*)?>/i, /^\s*(const|let|var)\s+\w+\s*=/m,
    /;\s*$/m, /^\s*[\w.]+\s*=\s*[\w.]+\(.*\)\s*$/m
  ];
  function looksLikeCode(t) {
    if (!t.trim()) return false;
    if (/```/.test(t)) return true;
    var signals = CODE_PATTERNS.filter(function (re) { return re.test(t); }).length;
    if (signals >= 2) return true;
    var symbols = (t.match(/[{}();=<>\[\]]/g) || []).length;
    return t.length >= 40 && symbols / t.length > 0.06;
  }

  var scoutForm = document.querySelector("[data-scout]");
  if (scoutForm) {
    var desc = document.getElementById("desc");
    var descErr = document.getElementById("desc-error");
    var countEl = scoutForm.querySelector("[data-count]");
    var goBtn = scoutForm.querySelector("[data-scout-go]");
    var out = document.querySelector("[data-scout-out]");
    var introHtml = out.innerHTML;
    var scoutWrap = scoutForm.closest(".scout") || document.body;
    var onSiteIds = null;

    var problemWith = function (text) {
      if (looksLikeCode(text)) return "This looks like code. Describe what you want to build in plain words instead.";
      if (text.length < 30) return "Add a little more detail, at least 30 characters, so Scout knows what to look for.";
      return "";
    };
    var showProblem = function (msg) {
      descErr.textContent = msg;
      descErr.hidden = !msg;
      desc.setAttribute("aria-invalid", msg ? "true" : "false");
    };
    var paintCount = function () { countEl.textContent = desc.value.length + " / 1000"; };
    desc.addEventListener("input", function () { paintCount(); if (!descErr.hidden) showProblem(""); });
    desc.addEventListener("blur", function () {
      var v = desc.value.trim();
      if (v) showProblem(problemWith(v));
    });
    // Pasted code is caught straight away, before any typing
    desc.addEventListener("paste", function () {
      setTimeout(function () { if (looksLikeCode(desc.value)) showProblem(problemWith(desc.value)); }, 0);
    });
    Array.prototype.forEach.call(scoutForm.querySelectorAll("[data-example]"), function (b) {
      b.addEventListener("click", function () {
        desc.value = b.getAttribute("data-example");
        paintCount(); showProblem(""); desc.focus();
      });
    });

    var siteIds = function () {
      if (onSiteIds) return Promise.resolve(onSiteIds);
      return fetch("data/ids.json").then(function (r) { return r.ok ? r.json() : []; }).catch(function () { return []; })
        .then(function (list) { onSiteIds = {}; list.forEach(function (id) { onSiteIds[id] = true; }); return onSiteIds; });
    };

    // ---- Results: the papers most relevant to the project, best first ----
    var FIT_LABEL = { strong: "Strong match", related: "Related", unchecked: "Not checked" };
    var NEED_COLORS = ["#3B5BDB", "#B4530F", "#7C3AED", "#0E7490"];
    var STATUS_LABEL = { covered: "Covered", partial: "Gap", missing: "Gap" };
    var FIRST_SHOWN = 10;
    var paperHref = function (p, onSite) {
      return onSite[p.id] ? "paper/" + esc(p.id) + ".html" : "https://huggingface.co/papers/" + esc(p.id);
    };
    var plural = function (n, one, many) { return n + " " + (n === 1 ? one : many); };

    // Plans saved by earlier versions of Scout, in today's shape
    var upgrade = function (data) {
      if (data.version === 3) return data;
      var plan = (data.plan || []).map(function (p) {
        return Object.assign({}, p, { score: null, fit: p.fit === "direct" ? "strong" : "related", why: p.reason || "" });
      });
      var cov = (data.needs || []).map(function (nd) {
        var mine = plan.filter(function (p) { return (p.needs || []).indexOf(nd.id) >= 0; });
        var strong = mine.filter(function (p) { return p.fit === "strong"; }).length;
        return { need: nd.id, label: nd.label, status: strong ? "covered" : mine.length ? "partial" : "missing", strong: strong, related: mine.length - strong };
      });
      return Object.assign({}, data, { version: 3, plan: plan, coverage: cov, gaps: [] });
    };

    var asMarkdown = function (data, description) {
      var lines = ["# " + (data.summary || description), ""];
      (data.coverage || []).forEach(function (c) {
        lines.push("- **" + c.label + "**: " + (c.status === "covered" ? "covered" : "gap") + " (" + c.strong + " strong, " + c.related + " related)");
      });
      lines.push("", "## Papers");
      (data.plan || []).forEach(function (p, i) {
        lines.push((i + 1) + ". [" + p.title + "](https://arxiv.org/abs/" + p.id + ")" + " (" + FIT_LABEL[p.fit] + (p.score != null ? ", " + p.score + "/100" : "") + ")" +
          (p.why ? "\n   " + p.why : "") + (p.code_url ? "\n   Code: " + p.code_url : ""));
      });
      lines.push("", "Made with Project Scout, AI Papers Daily");
      return lines.join("\n");
    };

    var paintPlan = function (raw, description, at) {
      var data = upgrade(raw);
      siteIds().then(function (onSite) {
        var needs = (data.needs || []).filter(function (nd) { return nd.label; });
        var colorOf = {}, labelOf = {};
        needs.forEach(function (nd, i) { colorOf[nd.id] = NEED_COLORS[i % NEED_COLORS.length]; labelOf[nd.id] = nd.label; });
        var cov = data.coverage || [];
        var state = { need: "", code: false, recent: false, all: false, dismissed: (raw.dismissed || []).slice() };
        var sixMonthsAgo = new Date(Date.now() - 182 * 864e5).toISOString().slice(0, 10);

        var needTag = function (id) {
          return labelOf[id] ? '<span class="sx-tag" style="--n:' + colorOf[id] + '">' + esc(labelOf[id]) + "</span>" : "";
        };
        var entry = function (p) {
          var local = onSite[p.id];
          var isSaved = saved.some(function (s) { return s.id === p.id; });
          var score = p.score != null ? p.score : "–";
          var meta = (p.submitted || p.first_seen ? "<span>" + esc(shortDay(p.submitted || p.first_seen)) + " " + String(p.submitted || p.first_seen).slice(0, 4) + "</span>" : "") +
            (p.code_url ? '<a class="sx-code" href="' + esc(p.code_url) + '" rel="noopener">Code</a>' : "") +
            (p.hf_upvotes ? '<span class="sx-up">▲ ' + p.hf_upvotes + "</span>" : "") +
            (local ? "" : '<span class="sx-up">On Hugging Face</span>');
          return '<article class="sx-entry fit-' + esc(p.fit) + (readIds[p.id] ? " is-read" : "") + '" data-id="' + esc(p.id) + '">' +
            '<div class="sx-score"><b>' + score + "</b>" + (p.score != null ? '<i style="--w:' + p.score + '%"></i>' : "") +
            '<span class="sx-fit">' + FIT_LABEL[p.fit] + "</span></div>" +
            '<div class="sx-body"><h3><a href="' + paperHref(p, onSite) + '"' + (local ? "" : ' rel="noopener"') + ' data-sx-open>' + esc(p.title) + "</a></h3>" +
            (p.why ? '<p class="sx-why">' + esc(p.why) + "</p>" : "") +
            '<div class="sx-row">' + (p.needs || []).map(needTag).join("") + '<span class="sx-meta">' + meta + "</span>" +
            '<span class="sx-acts"><button class="sx-act" type="button" data-sx-save aria-pressed="' + isSaved + '" aria-label="' + (isSaved ? "Saved" : "Save") + '">' +
            (isSaved ? "★" : "☆") + "<span>" + (isSaved ? " Saved" : " Save") + "</span></button>" +
            '<a class="sx-act" href="papers.html?q=' + encodeURIComponent(p.title) + '&amp;m=1" data-sx-more>More like this</a>' +
            '<button class="sx-act sx-ghost" type="button" data-sx-dismiss aria-label="Not relevant">✕<span> Not relevant</span></button></span></div></div></article>';
        };

        var needRows = cov.map(function (c) {
          var sub = c.strong ? plural(c.strong, "strong paper", "strong papers") + (c.related ? ", " + c.related + " related" : "")
            : c.related ? "Only " + plural(c.related, "related paper", "related papers") : "No papers yet";
          return '<li><button class="sx-need" type="button" data-sx-need="' + esc(c.need) + '" aria-pressed="false" style="--n:' + colorOf[c.need] + '">' +
            '<span class="sx-sq"></span><span class="sx-nl">' + esc(c.label) + '</span><span class="sx-st st-' + esc(c.status) + '">' + STATUS_LABEL[c.status] + "</span>" +
            '<span class="sx-nsub">' + sub + "</span></button></li>";
        }).join("");
        var chips = '<button class="sx-chip" type="button" data-sx-need="" aria-pressed="true">All<b>' + (data.plan || []).length + "</b></button>" +
          cov.map(function (c) {
            return '<button class="sx-chip" type="button" data-sx-need="' + esc(c.need) + '" aria-pressed="false"><span class="sx-dot st-' + esc(c.status) + '"></span>' +
              esc(c.label) + "<b>" + (c.strong + c.related) + "</b></button>";
          }).join("") + '<button class="sx-chip" type="button" data-sx-toggle="code" aria-pressed="false">Code released</button>';
        var hasPlan = (data.plan || []).length > 0;

        out.innerHTML = '<div class="sx">' +
          '<aside class="sx-brief">' +
          '<p class="sx-kicker">' + (at ? "Your last Scout, " + esc(ago(at)) : "Your project") + "</p>" +
          '<p class="sx-prompt"><span class="sx-ptext">' + esc(description) + "</span></p>" +
          '<div class="sx-pfoot"><span>' + (data.searched ? "Searched " + Number(data.searched).toLocaleString() + " papers" : "") + "</span>" +
          '<button type="button" data-sx-edit>Edit and search again</button></div>' +
          (cov.length ? '<p class="sx-kicker sx-hide-sm">What it needs</p><ul class="sx-needs">' + needRows + "</ul>" : "") +
          '<div class="sx-filters"><label><input type="checkbox" data-sx-toggle="code"> Code released</label>' +
          '<label><input type="checkbox" data-sx-toggle="recent"> Last 6 months</label></div>' +
          (cov.length ? '<div class="sx-chips">' + chips + "</div>" : "") +
          '<div class="sx-tools">' + (hasPlan ? '<button class="btn btn-primary btn-sm" type="button" data-scout-watch aria-pressed="false">Watch this project</button>' +
            '<button class="btn btn-outline btn-sm" type="button" data-scout-copy><span>Copy as Markdown</span></button>' : "") +
          '<button class="btn btn-outline btn-sm" type="button" data-scout-new>Start over</button></div>' +
          "</aside>" +
          '<section class="sx-results"><div class="sx-head"><h2>Papers to build on</h2><p data-sx-count></p></div>' +
          (data.mode === "basic" && hasPlan ? '<p class="sx-note">Relevance scoring was unavailable, so these are the closest papers by search and haven’t been checked for fit.</p>' : "") +
          '<div data-sx-list></div>' +
          '<div class="feedback" data-feedback="scout"><span data-feedback-q>Were these papers relevant?</span>' +
          '<button class="btn btn-outline btn-sm" type="button" data-vote="useful">Yes, relevant</button>' +
          '<button class="btn btn-outline btn-sm" type="button" data-vote="not_useful">Not really</button></div>' +
          "</section></div>";

        var listEl = out.querySelector("[data-sx-list]");
        var countEl2 = out.querySelector("[data-sx-count]");
        var gapsHtml = function () {
          return cov.filter(function (c) { return c.status !== "covered" && (!state.need || state.need === c.need); }).map(function (c) {
            var g = (data.gaps || []).filter(function (x) { return x.need === c.need; })[0];
            var tries = (g && g.try || []).map(function (t) {
              return '<a class="qchip" href="papers.html?q=' + encodeURIComponent(t) + '&amp;m=1">' + esc(t) + "</a>";
            }).join("");
            return '<div class="sx-gap"><p><b>No strong paper for “' + esc(c.label) + '” yet.</b> ' +
              (c.related ? "The related papers above are the closest we have." : "Nothing in our database covers this part.") + "</p>" +
              (tries ? '<div class="sx-try"><span>Try searching for</span>' + tries + "</div>" : "") + "</div>";
          }).join("");
        };
        var render = function () {
          var shown = (data.plan || []).filter(function (p) {
            if (state.dismissed.indexOf(p.id) >= 0) return false;
            if (state.need && (p.needs || []).indexOf(state.need) < 0) return false;
            if (state.code && !p.code_url) return false;
            if (state.recent && String(p.submitted || p.first_seen || "") < sixMonthsAgo) return false;
            return true;
          });
          var strong = shown.filter(function (p) { return p.fit !== "related"; });
          var related = shown.filter(function (p) { return p.fit === "related"; });
          var limit = state.all ? Infinity : FIRST_SHOWN;
          var html = strong.slice(0, limit).map(entry).join("");
          var left = Math.max(0, limit - strong.length);
          if (related.length && left > 0) {
            html += '<div class="sx-split">Related <small>Close to your project, but would need adapting</small></div>' +
              related.slice(0, left).map(entry).join("");
          }
          var hidden = shown.length - Math.min(shown.length, limit);
          if (hidden > 0) html += '<button class="sx-more" type="button" data-sx-all>Show ' + plural(hidden, "more paper", "more papers") + "</button>";
          if (!shown.length) {
            html = '<div class="sx-empty"><b>' + (hasPlan ? "No papers match these filters." : "No relevant papers in our database yet.") + "</b>" +
              (hasPlan ? "Clear a filter to see them again." : "Try naming the task and the data, for example “summarise legal contracts” instead of “legal AI app”.") + "</div>";
          }
          listEl.innerHTML = html + gapsHtml();
          var nStrong = strong.length, nRel = related.length;
          countEl2.textContent = data.mode === "basic" ? plural(shown.length, "paper", "papers") : nStrong + " strong, " + nRel + " related";
          Array.prototype.forEach.call(out.querySelectorAll("[data-sx-need]"), function (b) {
            b.setAttribute("aria-pressed", b.getAttribute("data-sx-need") === state.need ? "true" : "false");
          });
          Array.prototype.forEach.call(out.querySelectorAll("[data-sx-toggle]"), function (el) {
            var on = !!state[el.getAttribute("data-sx-toggle")];
            if (el.type === "checkbox") el.checked = on; else el.setAttribute("aria-pressed", on ? "true" : "false");
          });
        };
        var remember = function () {
          var last = load("apd.scout", null);
          if (last && last.description === description) { last.data.dismissed = state.dismissed; store("apd.scout", last); }
        };

        // One handler per paint (assigned, not added), so an older result's state can't answer clicks
        out.onclick = function (e) {
          var t = e.target.closest ? e.target : null;
          if (!t) return;
          var needBtn = t.closest("[data-sx-need]");
          if (needBtn) {
            var id = needBtn.getAttribute("data-sx-need");
            state.need = state.need === id ? "" : id;
            render(); return;
          }
          var tog = t.closest("button[data-sx-toggle]");
          if (tog) { var k = tog.getAttribute("data-sx-toggle"); state[k] = !state[k]; render(); return; }
          if (t.closest("[data-sx-all]")) { state.all = true; render(); return; }
          var undo = t.closest("[data-sx-undo]");
          if (undo) { var u = undo.getAttribute("data-sx-undo"); state.dismissed = state.dismissed.filter(function (x) { return x !== u; }); remember(); render(); return; }
          var card = t.closest(".sx-entry");
          if (!card) return;
          var pid = card.getAttribute("data-id");
          var p = (data.plan || []).filter(function (x) { return x.id === pid; })[0];
          if (t.closest("[data-sx-open]")) { track("site", "scout_click"); return; }
          if (t.closest("[data-sx-more]")) { track("site", "scout_more"); return; }
          if (t.closest("[data-sx-dismiss]")) {
            state.dismissed.push(pid); remember(); track("site", "scout_dismiss");
            card.outerHTML = '<p class="sx-removed">Removed “' + esc(p ? p.title : pid) + '”. <button type="button" data-sx-undo="' + esc(pid) + '">Undo</button></p>';
            return;
          }
          var sv = t.closest("[data-sx-save]");
          if (sv && p) {
            var on = saved.some(function (s) { return s.id === pid; });
            saved = on ? saved.filter(function (s) { return s.id !== pid; }) : [{ id: pid, t: p.title, at: Date.now() }].concat(saved);
            store("apd.saved", saved);
            if (!on) track("site", "scout_save");
            sv.setAttribute("aria-pressed", on ? "false" : "true");
            sv.setAttribute("aria-label", on ? "Save" : "Saved");
            sv.innerHTML = (on ? "☆" : "★") + "<span>" + (on ? " Save" : " Saved") + "</span>";
            showSavedCount();
          }
        };
        Array.prototype.forEach.call(out.querySelectorAll("input[data-sx-toggle]"), function (cb) {
          cb.addEventListener("change", function () { state[cb.getAttribute("data-sx-toggle")] = cb.checked; render(); });
        });
        render();

        wireFeedback(out.querySelector("[data-feedback]"));
        out.querySelector("[data-scout-new]").addEventListener("click", function () {
          try { localStorage.removeItem("apd.scout"); } catch (e) { /* private mode */ }
          scoutWrap.classList.remove("has-results");
          out.onclick = null;
          out.innerHTML = introHtml; desc.value = ""; paintCount(); desc.focus();
        });
        out.querySelector("[data-sx-edit]").addEventListener("click", function () {
          scoutWrap.classList.remove("has-results");
          desc.value = description; paintCount(); desc.focus();
          scoutForm.scrollIntoView({ behavior: "smooth", block: "start" });
        });
        var copyBtn = out.querySelector("[data-scout-copy]");
        if (copyBtn) copyBtn.addEventListener("click", function () {
          if (navigator.clipboard) navigator.clipboard.writeText(asMarkdown(data, description)).then(function () { confirmLabel(copyBtn, "Copied"); });
        });
        var watchBtn = out.querySelector("[data-scout-watch]");
        if (watchBtn && window.apdWatch) window.apdWatch.wire(watchBtn, data, description);
        scoutWrap.classList.add("has-results");
      });
    };

    var scoutNames = {};
    try { scoutNames = JSON.parse(scoutForm.getAttribute("data-names")) || {}; } catch (e) { /* slugs */ }

    var LOADING = ["Reading your description…", "Searching by meaning and by keywords…", "Scoring each paper for your project…"];
    var loading = function () {
      var step = 0;
      out.innerHTML = '<div class="card pad scout-loading" aria-busy="true"><span class="label" data-loading-text>' + LOADING[0] + "</span>" +
        '<span class="pixbar pixbar-run" aria-hidden="true">' + new Array(9).join("<i></i>") + "</span></div>" +
        '<div class="plan-skeleton" aria-hidden="true"><i></i><i></i><i></i></div>';
      var label = out.querySelector("[data-loading-text]");
      return setInterval(function () { step = Math.min(step + 1, LOADING.length - 1); label.textContent = LOADING[step]; }, 2500);
    };

    scoutForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var text = desc.value.replace(/\s+/g, " ").trim();
      var problem = problemWith(text);
      if (problem) { showProblem(problem); desc.focus(); return; }
      showProblem("");
      goBtn.disabled = true;
      goBtn.textContent = "Finding papers…";
      var timer = loading();
      callApi(scoutForm.getAttribute("data-url"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description: text })
      }, 90000).then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok, status: r.status, data: d }; });
      }).then(function (res) {
        clearInterval(timer);
        if (res.ok && !Array.isArray(res.data.plan)) res = { ok: false, status: 502, data: {} };  // a broken reply
        if (!res.ok) {
          if (res.status === 400 || /code|characters/.test(res.data.error || "")) showProblem(res.data.error || "");
          out.innerHTML = '<div class="card pad empty-card"><span class="label">Couldn’t find papers</span><p>' +
            esc(res.data.error || "Scout is unavailable right now. Try again in a minute.") + "</p></div>";
          return;
        }
        store("apd.scout", { description: text, data: res.data, at: Date.now() });
        paintPlan(res.data, text, 0);
        out.scrollIntoView({ behavior: "smooth", block: "start" });
      }).catch(function () {
        clearInterval(timer);
        out.innerHTML = '<div class="card pad empty-card"><span class="label">Couldn’t reach Scout</span><p>' +
          (navigator.onLine === false ? "You’re offline. Reconnect and try again." : "That took too long or the connection dropped. Please try again.") + "</p></div>";
      }).then(function () {
        goBtn.disabled = false;
        goBtn.textContent = "Find papers";
      });
    });

    // Bring back the last plan from this browser
    var last = load("apd.scout", null);
    if (last && last.data && last.data.plan) {
      desc.value = last.description || "";
      paintCount();
      paintPlan(last.data, last.description || "", last.at);
    }
    // "Run Scout again" from a watched project on the home page
    var draft = load("apd.scoutdraft", null);
    if (draft) {
      desc.value = String(draft);
      paintCount();
      try { localStorage.removeItem("apd.scoutdraft"); } catch (e) { /* private mode */ }
      desc.focus();
    }
  }

  // ---- All papers: cards, quick views and search over data/papers.json ----
  // Short keys are documented in compact() in site_builder.py.
  var results = document.getElementById("results");
  if (!results) return;

  var PAGE = 36;
  var q = document.getElementById("q");
  var cat = document.getElementById("cat");
  var meaning = document.getElementById("meaning");
  var chips = Array.prototype.slice.call(document.querySelectorAll("[data-view]"));
  var SEARCH_URL = results.getAttribute("data-search-url");
  var onSite = {};          // ids that have a page on this site
  var searchToken = 0;      // drops answers to searches the visitor has already replaced
  var more = document.getElementById("more");
  var count = document.getElementById("count");
  var all = [], matches = [], shown = 0, newest = "";

  var VIEWS = {
    "": { label: "papers, newest first" },
    week: { label: "most upvoted papers of the last 7 days",
            keep: function (p) { return p.u > 0 && p.d >= weekAgo(); },
            order: function (a, b) { return b.u - a.u; } },
    nothf: { label: "papers not on Hugging Face yet", keep: function (p) { return p.h; } },
    picks: { label: "of our daily picks", keep: function (p) { return p.f; } },
    code: { label: "papers with code", keep: function (p) { return p.k; } },
    easy: { label: "beginner-friendly papers", keep: function (p) { return p.l === "b"; } }
  };
  var LEVEL = { b: "Beginner", i: "Intermediate", a: "Advanced" };

  var params = new URLSearchParams(location.search);
  var view = VIEWS[params.get("view") || ""] ? params.get("view") || "" : "";
  q.value = params.get("q") || "";
  cat.value = params.get("cat") || "";
  meaning.checked = params.get("m") === "1";

  var names = {};
  Array.prototype.forEach.call(cat.options, function (o) { if (o.value) names[o.value] = o.textContent; });

  var thisYear = String(new Date().getFullYear());
  function shortDate(iso) {  // "Oct 31", or "4 Mar 2025" for another year
    var p = (iso || "").split("-");
    if (p.length !== 3) return iso;
    return p[0] === thisYear ? MONTHS[Number(p[1]) - 1] + " " + Number(p[2])
                             : Number(p[2]) + " " + MONTHS[Number(p[1]) - 1] + " " + p[0];
  }
  // "This week" counts back from the newest paper, so a quiet weekend isn't empty
  function weekAgo() {
    var d = new Date((newest || new Date().toISOString().slice(0, 10)) + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() - 7);
    return d.toISOString().slice(0, 10);
  }

  function card(p) {
    var local = onSite[p.i];
    var href = local ? "paper/" + esc(p.i) + ".html" : "https://huggingface.co/papers/" + esc(p.i);
    var topic = (p.c && p.c[0]) || "other-ml";
    var isSaved = saved.some(function (s) { return s.id === p.i; });
    var sig = "";
    if (p.f === 1) sig += '<span class="sig sig-pick">★ Our pick</span>';
    if (p.f === 2) sig += '<span class="sig sig-hot">Trending</span>';
    if (p.u) sig += '<span class="sig" title="Upvotes on Hugging Face">▲ ' + p.u + "</span>";
    else if (p.h) sig += '<span class="sig sig-new" title="Not on the Hugging Face daily list">Not on HF yet</span>';
    if (p.k) sig += '<span class="sig">' + "Code" + "</span>";
    if (p.l) sig += '<span class="sig">' + LEVEL[p.l] + "</span>";
    var first = (p.a && p.a[0]) || "";
    var authors = esc(first) + (p.n > 1 ? " +" + (p.n - 1) : "");
    return '<article class="pcard' + (readIds[p.i] ? " is-read" : "") + '" data-id="' + esc(p.i) + '">' +
      '<div class="pcard-top"><a class="topic t-' + esc(topic) + '" href="papers.html?cat=' + esc(topic) + '"><span class="dot"></span>' +
        esc(names[topic] || topic) + '</a><span class="pcard-date">' + esc(shortDate(p.d)) + "</span>" +
        (readIds[p.i] ? '<span class="pcard-read">Read</span>' : "") +
        '<button class="quick-save" type="button" data-quick-save="' + esc(p.i) + '" data-title="' + esc(p.t) +
        '" aria-pressed="' + isSaved + '" aria-label="Save this paper">' + (isSaved ? "✓" : "+") + "</button></div>" +
      '<h3><a href="' + href + '"' + (local ? "" : ' rel="noopener"') + ">" + esc(p.t) + "</a></h3>" +
      (p.m ? '<p class="pcard-sum">' + esc(p.m) + "</p>" : "") +
      '<div class="pcard-foot">' + sig + '<span class="pcard-auth">' + authors +
        (local ? "" : ' · <span class="ext">HF ↗</span>') + "</span></div></article>";
  }

  // A search function result in the short form card() expects
  function fromSearch(r) {
    var authors = r.authors || [];
    var known = byId[r.id] || {};
    return { i: r.id, t: r.title, a: authors.slice(0, 3), n: authors.length,
             c: (r.categories && r.categories.length) ? r.categories : ["other-ml"],
             d: String(r.submitted || r.first_seen || "").slice(0, 10), s: 0, f: known.f || (r.featured ? 1 : 0),
             m: known.m || "", u: known.u || r.hf_upvotes || 0, k: known.k, h: known.h, l: known.l, x: known.x };
  }
  var byId = {};

  function render(reset) {
    if (reset) { results.innerHTML = ""; shown = 0; }
    results.removeAttribute("aria-busy");
    if (!matches.length) {
      results.innerHTML = '<div class="empty"><strong>No papers match.</strong>Try fewer words, another view, or every topic.' +
        '<div class="empty-action"><button class="btn btn-outline btn-sm" type="button" data-clear>Clear all filters</button></div></div>';
    } else {
      results.insertAdjacentHTML("beforeend", matches.slice(shown, shown + PAGE).map(card).join(""));
    }
    shown = Math.min(shown + PAGE, matches.length);
    more.hidden = shown >= matches.length;
    if (meaning.checked && q.value.trim().length >= 3) {
      count.textContent = matches.length + " papers closest in meaning, best match first";
    } else {
      var n = matches.length.toLocaleString();
      count.textContent = view ? n + " " + VIEWS[view].label
        : matches.length === all.length ? n + " papers, newest first" : n + " of " + all.length.toLocaleString() + " papers";
    }
  }

  function keepFiltered(list) {
    var v = VIEWS[view];
    return list.filter(function (p) {
      if (cat.value && p.c.indexOf(cat.value) < 0) return false;
      if (v.keep && !v.keep(p)) return false;
      return true;
    });
  }

  function searchByMeaning() {
    var token = ++searchToken;
    results.setAttribute("aria-busy", "true");
    results.innerHTML = new Array(7).join('<div class="pcard skeleton" aria-hidden="true"><span></span><span></span><span></span></div>');
    count.textContent = "Searching by meaning…";
    callApi(SEARCH_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ q: q.value.trim(), limit: 50 })
    }, 20000)
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (body) { return { ok: r.ok, body: body }; }); })
      .then(function (res) {
        if (token !== searchToken) return;
        if (!res.ok || !Array.isArray(res.body.results)) throw serverError(res.body.error || "");
        matches = keepFiltered(res.body.results.map(fromSearch));
        render(true);
      })
      .catch(function (err) {
        if (token !== searchToken) return;
        meaning.checked = false;
        apply();
        count.textContent = (err.fromServer && err.message ? err.message : "Search by meaning is unavailable right now.") + " Showing word matches instead.";
      });
  }

  function paintChips() {
    chips.forEach(function (c) { c.setAttribute("aria-pressed", c.getAttribute("data-view") === view ? "true" : "false"); });
  }

  function apply() {
    paintChips();
    if (meaning.checked && q.value.trim().length >= 3) {
      searchByMeaning();
      syncUrl();
      return;
    }
    searchToken++;  // a word search replaces any meaning search still in flight
    var words = q.value.toLowerCase().split(/\s+/).filter(Boolean);
    matches = keepFiltered(all).filter(function (p) {
      if (!words.length) return true;
      var hay = (p.t + " " + p.a.join(" ") + " " + (p.m || "")).toLowerCase();
      return words.every(function (w) { return hay.indexOf(w) >= 0; });
    });
    if (VIEWS[view].order) matches.sort(VIEWS[view].order);
    render(true);
    syncUrl();
  }

  function syncUrl() {
    var u = new URLSearchParams();
    if (q.value) u.set("q", q.value);
    if (cat.value) u.set("cat", cat.value);
    if (view) u.set("view", view);
    if (meaning.checked) u.set("m", "1");
    history.replaceState(null, "", u.toString() ? "?" + u : location.pathname);
  }

  var timer;
  q.addEventListener("input", function () {
    clearTimeout(timer);
    timer = setTimeout(apply, meaning.checked ? 450 : 120);  // wait for a pause before asking the server
  });
  [cat, meaning].forEach(function (el) { el.addEventListener("change", apply); });
  chips.forEach(function (c) {
    c.addEventListener("click", function () { view = c.getAttribute("data-view"); apply(); });
  });
  more.addEventListener("click", function () { render(false); });
  results.addEventListener("click", function (e) {
    if (!e.target.closest || !e.target.closest("[data-clear]")) return;
    q.value = ""; cat.value = ""; view = ""; meaning.checked = false;
    apply();
    q.focus();
  });

  fetch("data/papers.json")
    .then(function (r) { return r.json(); })
    .then(function (data) {
      all = data;
      all.forEach(function (p) {
        byId[p.i] = p;
        if (!p.x) onSite[p.i] = true;
        if (p.d > newest) newest = p.d;
      });
      apply();
    })
    .catch(function () {
      results.removeAttribute("aria-busy");
      results.innerHTML = "";
      count.textContent = "We could not load the paper list. Reload the page to try again.";
    });
})();
