// AI Papers Daily: the site's own script. No libraries.
// Everything personal (reading history, saved papers, text size, theme) stays in
// this browser's localStorage. Only anonymous counts are sent (see "Anonymous counts").
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
    var box = document.getElementById("q") || document.getElementById("cs-q") || document.getElementById("cf-q");
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
    var saveBtns = document.querySelectorAll("[data-save]");
    var paintSave = function () {
      var on = saved.some(function (s) { return s.id === id; });
      Array.prototype.forEach.call(saveBtns, function (b) {
        b.setAttribute("aria-pressed", on ? "true" : "false");
        var label = b.querySelector("span");
        if (label) label.textContent = on ? "Saved" : "Save";
      });
    };
    Array.prototype.forEach.call(saveBtns, function (b) { b.addEventListener("click", function () {
      var on = saved.some(function (s) { return s.id === id; });
      saved = on ? saved.filter(function (s) { return s.id !== id; })
                 : [{ id: id, t: title, at: Date.now() }].concat(saved);
      store("apd.saved", saved);
      paintSave();
      showSavedCount();
    }); });
    paintSave();

    // "Added" date reads as today or yesterday by the reader's own calendar
    Array.prototype.forEach.call(document.querySelectorAll("[data-added]"), function (pill) {
      var iso = pill.getAttribute("data-added"), now = new Date();
      var key = function (d) { return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2); };
      var word = iso === key(now) ? "today" : (now.setDate(now.getDate() - 1), iso === key(now)) ? "yesterday" : "";
      if (!word) return;
      pill.querySelector("time").textContent = word;
      pill.hidden = false;
      if (word === "today") pill.classList.add("is-today");
    });

    // How deep to explain it: New to this, Practitioner or Researcher, remembered across papers
    var levelBox = document.querySelector("[data-levels]");
    if (levelBox) {
      var levelOut = document.querySelector("[data-level-out]");
      var paintLevel = function (lv) {
        var tpl = document.querySelector('[data-level-text="' + lv + '"]');
        if (!tpl) return;
        levelOut.innerHTML = tpl.innerHTML;
        Array.prototype.forEach.call(levelBox.querySelectorAll("[data-level]"), function (b) {
          b.setAttribute("aria-pressed", b.getAttribute("data-level") === lv ? "true" : "false");
        });
      };
      levelBox.addEventListener("click", function (e) {
        var b = e.target.closest("[data-level]");
        if (!b) return;
        store("apd.level", b.getAttribute("data-level"));
        paintLevel(b.getAttribute("data-level"));
      });
      var savedLevel = load("apd.level", "standard");
      if (savedLevel !== "standard") paintLevel(savedLevel);
    }

    // Definitions: hover or focus opens them; a tap toggles them on touch screens
    document.addEventListener("click", function (e) {
      var t = e.target.closest && e.target.closest(".term");
      Array.prototype.forEach.call(document.querySelectorAll(".term.is-open"), function (o) { if (o !== t) o.classList.remove("is-open"); });
      if (t) t.classList.toggle("is-open");
    });

    // Skim colours in the abstract, on by default, remembered
    var skimBtn = document.querySelector("[data-skim-toggle]");
    if (skimBtn) {
      var skimAbs = document.querySelector(".np-abs"), skimLegend = document.querySelector("[data-skim-legend]");
      var paintSkim = function (on) {
        skimAbs.classList.toggle("no-skim", !on);
        skimLegend.classList.toggle("no-skim", !on);
        skimBtn.setAttribute("aria-pressed", on ? "true" : "false");
        skimBtn.textContent = on ? "Hide colours" : (rdSkim ? "Colour to skim" : "Show colours");
      };
      // The reading layout starts plain; the older layout kept its colours on
      var rdSkim = !!document.querySelector(".rd");
      paintSkim(rdSkim ? load("apd.skim.rd", false) : load("apd.skim", true));
      skimBtn.addEventListener("click", function () {
        var on = skimBtn.getAttribute("aria-pressed") !== "true";
        store(rdSkim ? "apd.skim.rd" : "apd.skim", on);
        paintSkim(on);
      });
    }

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

    // "Copy for LLM" and "View as Markdown": the same notes as a plain .md file
    var mdCopy = document.querySelector("[data-md-copy]");
    if (mdCopy) {
      var mdUrl = mdCopy.getAttribute("data-md"), mdText = null;
      var getMd = function () {
        if (mdText !== null) return Promise.resolve(mdText);
        return fetch(mdUrl).then(function (r) {
          if (!r.ok) throw new Error("No Markdown");
          return r.text();
        }).then(function (t) { mdText = t; return t; });
      };
      mdCopy.addEventListener("click", function () {
        getMd().then(function (t) { return navigator.clipboard.writeText(t); }).then(function () {
          mdCopy.classList.add("is-done");
          confirmLabel(mdCopy, "Copied for your LLM");
          setTimeout(function () { mdCopy.classList.remove("is-done"); }, 1800);
        }).catch(function () { confirmLabel(mdCopy, "Couldn't copy, try View as Markdown"); });
      });
      var mdView = document.querySelector("[data-md-view]");
      if (mdView && window.HTMLDialogElement) {
        mdView.addEventListener("click", function (e) {
          e.preventDefault();
          getMd().then(function (t) {
            var d = document.querySelector(".np-md");
            if (!d) {
              d = document.createElement("dialog");
              d.className = "np-md";
              d.setAttribute("aria-label", "This page as Markdown");
              d.innerHTML = '<div class="np-md-head"><b>' + esc(mdUrl) + '</b><small>Notes, numbers and links as plain text</small>' +
                '<div class="np-md-btns"><button class="btn btn-outline btn-sm" type="button" data-md-dcopy><span>Copy</span></button>' +
                '<button class="btn btn-outline btn-sm" type="button" data-md-close>Close</button></div></div><pre></pre>';
              d.querySelector("pre").textContent = t;
              d.querySelector("[data-md-close]").addEventListener("click", function () { d.close(); });
              d.querySelector("[data-md-dcopy]").addEventListener("click", function () {
                var b = this;
                navigator.clipboard.writeText(t).then(function () { confirmLabel(b, "Copied"); });
              });
              d.addEventListener("click", function (ev) { if (ev.target === d) d.close(); });
              d.addEventListener("close", function () { mdView.focus(); });
              document.body.appendChild(d);
            }
            d.showModal();
          }).catch(function () { location.href = mdUrl; });
        });
      }
    }

    // "On this page": highlights the section you are reading, and the thin line fills as you read
    var otp = document.querySelector("[data-otp]");
    if (otp) {
      var otpLinks = Array.prototype.slice.call(otp.querySelectorAll("a[href^='#']"));
      var otpBar = otp.querySelector("[data-otp-bar]");
      var visible = function (el) { return el && el.offsetParent !== null; };
      var otpSecs = function () {
        return otpLinks.map(function (a) {
          var sec = document.getElementById(a.getAttribute("href").slice(1));
          a.hidden = !visible(sec);
          return a.hidden ? null : sec;
        });
      };
      // A # link on each heading, so any section can be shared
      Array.prototype.forEach.call(document.querySelectorAll(".np-sec[id] > h2, .rd-sec[id] > h2:not(.sr-only)"), function (h) {
        var a = document.createElement("a");
        a.className = "np-hash";
        a.href = "#" + h.parentNode.id;
        a.textContent = "#";
        a.setAttribute("aria-label", "Link to this section");
        h.insertBefore(a, h.querySelector("small"));
      });
      var otpTick = false;
      var paintOtp = function () {
        otpTick = false;
        var max = root.scrollHeight - root.clientHeight;
        otpBar.style.transform = "scaleX(" + (max > 0 ? Math.min(1, root.scrollTop / max) : 0) + ")";
        var pct = otp.querySelector("[data-rd-pct]");
        if (pct) pct.textContent = Math.round(100 * (max > 0 ? Math.min(1, root.scrollTop / max) : 0)) + "%";
        // The reading layout keeps its list in the side column, so read from a third of the way down the screen
        var line = otp.classList.contains("rd-toc") ? innerHeight * 0.33 : otp.getBoundingClientRect().bottom + 24, cur = -1;
        otpSecs().forEach(function (sec, i) { if (sec && sec.getBoundingClientRect().top <= line) cur = i; });
        otpLinks.forEach(function (a, i) {
          if (i === cur) {
            if (!a.hasAttribute("aria-current")) {
              a.setAttribute("aria-current", "true");
              var box = a.parentNode;
              if (box.scrollWidth > box.clientWidth) box.scrollTo({ left: a.offsetLeft - 16, behavior: "smooth" });
            }
          } else a.removeAttribute("aria-current");
        });
      };
      var askOtp = function () { if (!otpTick) { otpTick = true; requestAnimationFrame(paintOtp); } };
      window.addEventListener("scroll", askOtp, { passive: true });
      window.addEventListener("resize", askOtp);
      paintOtp();
    }

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
      // The notes box appears once the reader has a note
      var notesBox = emptyNote.closest("[data-notes]");
      if (notesBox) notesBox.hidden = mine.length === 0;
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
    var bdShort = document.querySelector("[data-bd-short-box]");
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
      // One tab per section, so the page stays short
      var parts = html.split(/(?=<h3>)/).filter(Boolean);
      if (parts.length > 1) {
        var names = parts.map(function (h) { var m = /<h3>([^<]*)<\/h3>/.exec(h); return m ? m[1] : ""; });
        html = '<div class="bd-tabs" role="tablist" aria-label="Parts of the paper">' + names.map(function (n, i) {
          return '<button type="button" role="tab" id="bdt-' + i + '" aria-controls="bdp-' + i + '" aria-selected="' + (i === 0) + '">' + esc(n.replace(/^What they contribute$/, "Contributions").replace(/^Links in the paper$/, "Links")) + "</button>";
        }).join("") + "</div>" + parts.map(function (h, i) {
          return '<div class="bd-panel" role="tabpanel" id="bdp-' + i + '" aria-labelledby="bdt-' + i + '"' + (i ? " hidden" : "") + ">" + h + "</div>";
        }).join("");
      }
      if (b.links && b.links.length) {
        html += '<h3>Links in the paper</h3><ul class="bd-links">' + b.links.map(function (u) {
          return '<li><a href="' + esc(u) + '" rel="noopener" data-out="code">' + esc(u.replace(/^https?:\/\/(www\.)?/, "")) + "</a></li>";
        }).join("") + "</ul>";
      }
      bdOut.innerHTML = html;
      bdBtn.hidden = true;
      bdNote.textContent = html ? "Copied from the paper by our code, not written by AI. Tables may lose some formatting." :
        "We couldn’t find these sections in the paper’s web version. The PDF has everything.";
      if (d.summary && bdShort) {
        bdShort.querySelector("[data-bd-short-text]").textContent = d.summary;
        bdShort.hidden = false;
        var src = bdShort.querySelector("[data-bd-short-src]");
        if (src) src.textContent = "Written by AI from the full paper. Every number in it was checked against the paper.";
      }
    };
    var bdMake = function () {
      bdNote.textContent = "Reading the paper on arXiv. This happens once, then it’s saved for everyone.";
      bdBtn.disabled = true;
      bdBtn.textContent = "Reading the paper on arXiv…";
      track("site", "breakdown_load");
      bdCall({}).then(paintBreakdown).catch(function (e) {
        bdOut.innerHTML = "";
        bdBtn.hidden = false;
        bdBtn.disabled = false;
        bdBtn.textContent = "Try again";
        bdNote.textContent = e.fromServer && e.message ? e.message : "Couldn’t read the paper right now. Try again in a minute.";
      });
    };
    bdBtn.addEventListener("click", bdMake);
    bdOut.addEventListener("click", function (e) {
      var tab = e.target.closest('[role="tab"]');
      if (!tab) return;
      Array.prototype.forEach.call(bdOut.querySelectorAll('[role="tab"]'), function (t) {
        var on = t === tab;
        t.setAttribute("aria-selected", on ? "true" : "false");
        document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
      });
    });
    bdOut.innerHTML = '<div class="bd-skel" aria-hidden="true"><span style="width:92%"></span><span style="width:78%"></span><span style="width:85%"></span></div>';
    bdCall({ peek: true }).then(function (d) {
      // Not read yet: read it now, once for everyone (the AI summary inside is capped per day)
      if (d.status === "missing") { bdMake(); return; }
      paintBreakdown(d);
      // Saved before anyone asked for a summary: make it now (once per paper, capped per day)
      if (d.status === "ready" && d.summaryLater && bdWantSummary) bdCall({}).then(function (x) { if (x.summary) paintBreakdown(x); }).catch(function () {});
    }).catch(function () {
      if (bdLayer) bdLayer.hidden = true; // the service is down: leave the page as it was
      bdOut.innerHTML = "";
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
      goal("ask_question", "Ask this paper");
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
      // Ask sits inline on the page: bring it into view
      if (ask.scrollIntoView) ask.scrollIntoView({ behavior: "smooth", block: "center" });
      if (focus) askInput.focus({ preventScroll: true });
    };
    var closeAsk = function () {
      ask.classList.remove("is-open");
      if (askFab) { askFab.setAttribute("aria-expanded", "false"); askFab.focus(); }
    };
    if (askFab) askFab.addEventListener("click", function () { openAsk(true); });
    // Every "Ask this paper" link on the page brings the box into view and puts the cursor in it
    var jumpAsk = function () {
      openAsk(true);
      ask.classList.remove("is-flash"); void ask.offsetWidth; ask.classList.add("is-flash");
    };
    document.querySelectorAll("[data-ask-jump]").forEach(function (b) { b.addEventListener("click", jumpAsk); });
    // "a" also jumps there, unless the reader is typing somewhere
    if (document.querySelector(".rd-askbar")) document.addEventListener("keydown", function (e) {
      var t = e.target, tag = t && t.tagName;
      if (e.key !== "a" || e.metaKey || e.ctrlKey || e.altKey || tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || (t && t.isContentEditable)) return;
      e.preventDefault(); jumpAsk();
    });
    var askClose = ask.querySelector("[data-ask-close]");
    if (askClose) askClose.addEventListener("click", closeAsk);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && ask.classList.contains("is-open")) closeAsk();
    });
    window.apdAsk = function (question) { openAsk(false); askQuestion(question); };
    // "Explain this paper": a plain-words walk through the whole paper, answered from the full text
    Array.prototype.forEach.call(document.querySelectorAll("[data-explain]"), function (b) {
      b.addEventListener("click", function () {
        window.apdAsk("Explain this whole paper in plain words: the problem, the main idea, how it works and the result.");
      });
    });

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
  // Bots stay out of every count. A browser run by a script says so
  // (navigator.webdriver) or names itself in its user agent; crawlers on
  // cloud servers that look like plain Chrome never scroll, tap or press a
  // key, so visits are only counted once a person does one of those.
  var AUTOMATED = navigator.webdriver === true ||
    /HeadlessChrome|Lighthouse|PhantomJS|Puppeteer|Playwright|bot\b|crawl|spider|slurp|preview/i.test(navigator.userAgent || "") ||
    !navigator.languages || navigator.languages.length === 0;
  function whenHuman(fn) {
    if (AUTOMATED) return;
    var kinds = ["pointerdown", "pointermove", "keydown", "scroll", "wheel", "touchstart"];
    var done = false;
    function go(e) {
      // Chrome sends one still pointermove as the page loads under the mouse
      if (done || e.type === "pointermove" && !e.movementX && !e.movementY) return;
      done = true;
      kinds.forEach(function (k) { window.removeEventListener(k, go, true); });
      fn();
    }
    kinds.forEach(function (k) { window.addEventListener(k, go, { capture: true, passive: true }); });
  }
  // Site-wide actions that also show up as events in Umami
  var GOALS = /^(scout_(click|save|dismiss|more)|breakdown_load|out_(pdf|arxiv|hf|code)|subscribe_(rss|email|confirmed)|click_(pick|trending|runner_up|most_read))$/;
  function track(id, event) {
    if (AUTOMATED) return;
    if (id === "site" && GOALS.test(event)) goal(event);
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
  whenHuman(function countVisit() {
    var today = new Date().toISOString().slice(0, 10);
    var last = load("apd.lastVisit", "");
    if (last === today) return;
    store("apd.lastVisit", today);
    var gap = last ? (Date.parse(today) - Date.parse(last)) / 86400000 : -1;
    track("site", gap < 0 || isNaN(gap) ? "visit_new" : gap <= 7 ? "visit_return_7d" : "visit_return_old");
    track("site", "src_" + visitSource());
  });

  // ---- Umami: visitors, pages, sources and key actions (no cookies) ----
  // The page view is sent from here rather than by Umami on its own, with the
  // address as it arrived (?ref= and utm_ tags included), because dropRefTag()
  // below tidies the tags out of the address bar. Umami lists the tags under
  // Query parameters / UTM, and the referring site under Referrers.
  var arrivedAt = location.pathname + location.search;
  function withCounter(fn) {
    // Not id="umami": an element with that id would take over window.umami
    var script = document.getElementById("umami-script");
    if (!script || AUTOMATED) return;
    if (window.umami && window.umami.track) { fn(window.umami); return; }
    script.addEventListener("load", function () { if (window.umami && window.umami.track) fn(window.umami); });
  }
  function goal(name) {
    withCounter(function (u) { u.track(name); });
  }
  whenHuman(function () {
    withCounter(function (u) {
      u.track(function (props) { props.url = arrivedAt; props.referrer = document.referrer; return props; });
    });
  });

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
      (item.u ? '<span class="row-title"><a href="' + esc(item.u) + '" rel="noopener" target="_blank">' + esc(item.t || item.u) + "</a></span>" +
                '<span class="row-authors">Case study from ' + esc(item.c || "a company blog") + ", " + verb.toLowerCase() + " " + ago(item.at) + "</span>"
              : '<span class="row-title"><a href="paper/' + esc(item.id) + '.html">' + esc(item.t || item.id) + "</a></span>" +
                '<span class="row-authors">' + verb + " " + ago(item.at) + "</span>") +
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

  // Shared by All papers and Project Scout cards
  // Text covers: a tinted band per topic that stands in for a thumbnail, with no image to load
  var COVER_WORD = {
    "llms": "LLM", "generative-ai": "GEN AI", "computer-vision": "VISION", "audio-speech": "AUDIO",
    "alignment": "ALIGN", "reasoning-agents": "AGENTS", "ml-theory": "THEORY", "ai-science": "SCIENCE",
    "code-ai": "CODE", "safety-privacy": "SAFETY", "efficient-ai": "EFF AI", "multimodal": "MULTI", "other-ml": "ML"
  };
  // Where the lab logos live, for labMark(): its logo on its brand colour, or its initials
  var LABS_SVG = (function () {
    var css = document.querySelector('link[href*="assets/style.css"]');
    return css ? css.getAttribute("href").replace("style.css", "labs.svg") : "assets/labs.svg";
  })();
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

    // The All papers index: which papers have a page here, plus each one's lab and one-line summary for the cards
    var paperIndex = {};
    var siteIds = function () {
      if (onSiteIds) return Promise.resolve(onSiteIds);
      return fetch("data/papers.json").then(function (r) { if (!r.ok) throw new Error("index"); return r.json(); })
        .then(function (list) {
          onSiteIds = {};
          list.forEach(function (p) { paperIndex[p.i] = p; if (!p.x) onSiteIds[p.i] = true; });
          return onSiteIds;
        })
        .catch(function () {
          return fetch("data/ids.json").then(function (r) { return r.ok ? r.json() : []; }).catch(function () { return []; })
            .then(function (list) { onSiteIds = {}; list.forEach(function (id) { onSiteIds[id] = true; }); return onSiteIds; });
        });
    };

    // ---- Results: the papers most relevant to the project, best first ----
    var FIT_LABEL = { strong: "Strong match", related: "Related", unchecked: "Not checked" };
    var NEED_COLORS = ["#3B5BDB", "#B4530F", "#7C3AED", "#0E7490"];
    var STATUS_LABEL = { covered: "Covered", partial: "Partly", missing: "Gap" };
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

    // The brief as text: for the visitor's notes, or to paste into an AI assistant
    var needNum = function (data, id) {
      var i = (data.needs || []).map(function (n) { return n.id; }).indexOf(id);
      return i < 0 ? "" : (i < 9 ? "0" : "") + (i + 1);
    };
    var asMarkdown = function (data, description) {
      var lines = ["# " + (data.summary || description), "", "> " + description, ""];
      var plan = data.plan || [];
      (data.coverage || []).forEach(function (c, i) {
        lines.push("## Part " + (i + 1) + ": " + c.label + " (" + (c.status === "covered" ? "covered" : "open problem") + ")", "");
        var mine = plan.filter(function (p) { return (p.needs || [])[0] === c.need; });
        if (!mine.length) lines.push("No paper in our library covers this part yet.");
        mine.forEach(function (p) {
          lines.push("- [" + p.title + "](https://arxiv.org/abs/" + p.id + ")" + " (" + FIT_LABEL[p.fit] + (p.score != null ? ", " + p.score + "/100" : "") + ")" +
            (p.why ? "\n  " + p.why : "") + (p.code_url ? "\n  Code: " + p.code_url : ""));
        });
        lines.push("");
      });
      if ((data.cases || []).length) {
        lines.push("## Teams that built something like this", "");
        data.cases.forEach(function (c) { lines.push("- [" + c.company + ": " + c.title + "](" + c.url + ")" + (c.summary ? "\n  " + c.summary : "")); });
        lines.push("");
      }
      lines.push("Made with Project Scout, AI Papers Daily");
      return lines.join("\n");
    };
    var asPrompt = function (data, description) {
      return "I want to build this project:\n\n" + description + "\n\n" +
        "Below is a research brief for it: the parts it needs, the most relevant recent AI papers for each part, " +
        "and the parts no paper covers yet. Use it to help me design the system. Suggest an architecture, " +
        "say which paper's method to use for each part and why, and propose how to handle the open problems.\n\n" +
        asMarkdown(data, description);
    };

    // ---- Case study cards, drawn like the Case studies page (case_pages.post_card) ----
    var BRANDS = { c: {}, p: {}, svg: "data/case-brands.svg" };
    try { BRANDS = JSON.parse(scoutForm.getAttribute("data-brands")) || BRANDS; } catch (e) { /* plain initials */ }
    var caseLogo = function (company, cls) {
      var b = BRANDS.c[company] || [];
      if (b[0]) return '<svg class="' + cls + (b[3] ? " cs-ink" : "") + '" aria-hidden="true"><use href="' + esc(BRANDS.svg) + "#b-" + esc(b[0]) + '"/></svg>';
      if (b[2]) return '<img class="' + cls + ' cs-img" src="case-studies/logos/' + esc(b[2]) + '" alt="" loading="lazy" decoding="async">';
      return '<span class="' + cls + ' cs-mono" style="--b:' + esc(b[1] || "#5D5C63") + '" aria-hidden="true">' + esc((company || "?").charAt(0).toUpperCase()) + "</span>";
    };
    var BOOKMARK = '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/></svg>';
    var host = function (url) { return String(url || "").split("://").pop().split("/")[0].replace(/^www\./, ""); };
    var caseCard = function (c, data) {
      var nums = (c.needs || []).map(function (id) { return needNum(data, id); }).filter(Boolean);
      var isSaved = saved.some(function (s) { return s.id === "cs:" + c.url; });
      var tags = (c.tags || []).slice(0, 3).map(function (t) { return '<li><span class="cs-tag">' + esc(t) + "</span></li>"; }).join("");
      var body = c.issue ? '<p class="cs-issue"><b>Problem</b> ' + esc(c.issue) + "</p>" + (c.summary ? '<p class="cs-fix"><b>Solution</b> ' + esc(c.summary) + "</p>" : "")
        : (c.summary ? "<p>" + esc(c.summary) + "</p>" : "");
      var when = c.published ? '<time datetime="' + esc(c.published) + '">' + esc(longDay(c.published)) + "</time>" : "";
      return '<li class="cs-card" style="--c:var(--l-' + esc(c.problem || "llm") + ");--b:" + esc((BRANDS.c[c.company] || [])[1] || "#5D5C63") + '">' +
        '<div class="cs-cover">' + caseLogo(c.company, "cs-big") + '<span class="cs-co">' + caseLogo(c.company, "cs-badge") + esc(c.company) + "</span>" + when +
        '<span class="cs-topic">' + esc(BRANDS.p[c.problem] || "Case study") + "</span></div>" +
        '<div class="cs-body"><h3><a class="cs-link" href="' + esc(c.url) + '" rel="noopener" target="_blank" data-sb-case>' + esc(c.title) + "</a></h3>" + body +
        (tags ? '<ul class="cs-tags" aria-label="Techniques">' + tags + "</ul>" : "") +
        (nums.length ? '<p class="sb-matches">Matches part' + (nums.length > 1 ? "s " + nums.slice(0, -1).join(", ") + " and " + nums[nums.length - 1] : " " + nums[0]) + "</p>" : "") +
        '<div class="cs-foot"><span class="cs-src">Read on ' + esc(host(c.url)) + ' ↗</span><button class="cs-save" type="button" data-sb-case-save="' + esc(c.url) + '" aria-pressed="' + isSaved + '">' + BOOKMARK +
        '<span>' + (isSaved ? "Saved" : "Save") + "</span></button></div></div></li>";
    };

    // ---- Results: a build brief. The project, a map of its parts, the papers for each part, and teams that built it ----
    var ring = function (score, r) {
      var c = 2 * Math.PI * r, v = Math.max(0, Math.min(100, score || 0)) / 100 * c;
      return '<svg viewBox="0 0 ' + (2 * r + 8) + " " + (2 * r + 8) + '" aria-hidden="true"><circle class="sb-ring-bg" cx="' + (r + 4) + '" cy="' + (r + 4) + '" r="' + r + '"/>' +
        '<circle class="sb-ring-fg" cx="' + (r + 4) + '" cy="' + (r + 4) + '" r="' + r + '" stroke-dasharray="' + v.toFixed(1) + " " + c.toFixed(1) + '" transform="rotate(-90 ' + (r + 4) + " " + (r + 4) + ')"/></svg>';
    };
    var shortTitle = function (t) { var s = String(t || "").split(/:\s/)[0]; return s.length <= 48 ? s : s.slice(0, 46) + "…"; };
    var readiness = function (cov) {
      var ready = cov.filter(function (c) { return c.status === "covered"; }).length, n = cov.length;
      var head = !n ? "Searched as one part" : ready === n ? "Buildable today" : ready >= n / 2 ? "Mostly buildable" : ready ? "Early, with open problems" : "Open research";
      var sub = !n ? "" : ready === n ? "Every part has a proven paper to build on."
        : (ready ? plural(ready, "part has", "parts have") + " proven papers. " : "") +
          plural(n - ready, "part", "parts") + " you’ll build yourself or watch for.";
      // Each ring segment is one part: green when covered, orange when not
      var r = 40, circ = 2 * Math.PI * r, gap = n > 1 ? 6 : 0, seg = n ? (circ - gap * n) / n : circ;
      var segs = cov.map(function (c, i) {
        return '<circle class="' + (c.status === "covered" ? "rg-ok" : "rg-gap") + '" cx="48" cy="48" r="' + r + '" stroke-dasharray="' + seg.toFixed(1) + " " + (circ - seg).toFixed(1) +
          '" stroke-dashoffset="' + (-(i * (seg + gap))).toFixed(1) + '" transform="rotate(-90 48 48)"/>';
      }).join("");
      return '<div class="sb-ready"><div class="sb-ring-big"><svg viewBox="0 0 96 96" aria-hidden="true">' + segs + "</svg>" +
        "<b>" + ready + "/" + n + "</b><span>Ready</span></div><div><p class=\"sb-ready-h\">" + head + "</p><p>" + esc(sub) + "</p></div></div>";
    };

    var paintPlan = function (raw, description, at) {
      var data = upgrade(raw);
      siteIds().then(function (onSite) {
        var needs = (data.needs || []).filter(function (nd) { return nd.label; });
        var cov = data.coverage || [];
        var plan = data.plan || [];
        var cases = data.cases || [];
        var state = { code: false, recent: false, open: {}, dismissed: (raw.dismissed || []).slice() };
        var sixMonthsAgo = new Date(Date.now() - 182 * 864e5).toISOString().slice(0, 10);
        var hasPlan = plan.length > 0;
        var home = function (p) { return (p.needs || [])[0] || (cov[0] && cov[0].need) || ""; };
        var casesFor = function (id) { return cases.filter(function (c) { return (c.needs || []).indexOf(id) >= 0; }); };

        // One paper, drawn like an All papers card with its fit score on the cover
        var entry = function (p) {
          var local = onSite[p.id];
          var x = paperIndex[p.id] || {};
          var topic = (p.categories && p.categories[0]) || (x.c && x.c[0]) || "other-ml";
          var isSaved = saved.some(function (s) { return s.id === p.id; });
          var day = String(p.submitted || p.first_seen || x.d || "").slice(0, 10);
          var also = (p.needs || []).slice(1).map(function (id) { return needNum(data, id); }).filter(Boolean);
          var authors = (p.authors || x.a || []).slice(0, 2).map(esc).join(", ");
          var extra = (p.n_authors || x.n || 0) - Math.min(2, (p.authors || x.a || []).length);
          if (extra > 0) authors += " +" + extra;
          var chips = (p.code_url ? '<a class="sig sb-code" href="' + esc(p.code_url) + '" rel="noopener">Code</a>' : "") +
            (p.hf_upvotes ? '<span class="sig sig-up" title="Upvotes on Hugging Face">▲ ' + p.hf_upvotes + "</span>" : "") +
            (also.length ? '<span class="sig sb-also">Also helps part ' + also.join(", ") + "</span>" : "") +
            (readIds[p.id] ? '<span class="pcard-read">✓ Read</span>' : "") +
            (local ? "" : '<span class="sig sig-arxiv">On Hugging Face</span>');
          return '<article class="pcard sb-paper t-' + esc(topic) + " fit-" + esc(p.fit) + (readIds[p.id] ? " is-read" : "") + '" data-id="' + esc(p.id) + '">' +
            '<div class="pc-cover sb-cover"><div class="pc-cover-top"><a class="pc-topic" href="papers.html?cat=' + esc(topic) + '"><span class="dot"></span>' +
            esc(scoutNames[topic] || topic) + "</a></div>" +
            '<div class="pc-word" aria-hidden="true">' + esc(COVER_WORD[topic] || "ML") + "</div>" +
            '<div class="sb-score">' + (p.score != null ? ring(p.score, 26) + "<b>" + p.score + "</b>" : "<b>–</b>") + "</div>" +
            '<span class="sb-fit">' + FIT_LABEL[p.fit] + "</span></div>" +
            '<div class="pc-body">' + (x.o || authors ? '<p class="pcard-by">' + (x.o ? labMark(x) + '<span class="org-name">' + esc(x.o) + "</span>" + (authors ? '<span class="by-sep">·</span>' : "") : "") +
            '<span class="by-auth">' + authors + "</span></p>" : "") +
            '<h3 title="' + esc(p.title) + '"><a href="' + paperHref(p, onSite) + '"' + (local ? "" : ' rel="noopener"') + " data-sx-open>" + esc(p.title) + "</a></h3>" +
            (x.m ? '<p class="pcard-sum">' + esc(x.m) + "</p>" : "") +
            (p.why ? '<div class="sb-why"><span>Why it fits your project</span>' + esc(p.why) + "</div>" : "") +
            (chips ? '<div class="pcard-tags sb-tags">' + chips + "</div>" : "") +
            '<div class="pcard-foot">' + (day ? '<p class="pcard-dates"><span class="date-pill is-pub"><span class="dp-k">Published</span><time datetime="' + esc(day) + '">' + esc(longDay(day)) + "</time></span></p>" : "") +
            '<span class="sb-acts"><a class="sb-act" href="papers.html?q=' + encodeURIComponent(p.title) + '&amp;m=1" data-sx-more>More like this</a>' +
            '<button class="sb-act" type="button" data-sx-dismiss>Not relevant</button></span>' +
            '<button class="quick-save" type="button" data-sx-save aria-pressed="' + isSaved + '" aria-label="' + (isSaved ? "Saved" : "Save this paper") + '">' + (isSaved ? "✓" : "+") + "</button></div>" +
            "</div></article>";
        };

        // The build map: one card per part, in the order to build them
        var mapCard = function (c, i) {
          var mine = plan.filter(function (p) { return home(p) === c.need; });
          var best = mine.filter(function (p) { return p.fit === "strong"; })[0];
          var ok = c.status === "covered";
          var label = !ok ? "Open problem" : i === 0 ? "Start here" : "Build on";
          var segs = [0, 1, 2].map(function (k) {
            return '<i class="' + (k < c.strong ? "s-strong" : k < c.strong + c.related ? "s-rel" : "") + '"></i>';
          }).join("");
          var teams = casesFor(c.need);
          var marks = teams.slice(0, 3).map(function (t) { return caseLogo(t.company, "sb-team"); }).join("");
          var pick = best ? "Best pick: <b>" + esc(shortTitle(best.title)) + "</b>" + (best.why ? ", " + esc(best.why.charAt(0).toLowerCase() + best.why.slice(1)).replace(/\.$/, "") : "")
            : c.related ? "No strong paper yet. " + plural(c.related, "related paper is", "related papers are") + " close."
            : "No paper covers this part yet. A chance to build something new.";
          return '<li class="sb-part ' + (ok ? "is-ok" : "is-gap") + '"><a href="#sb-need-' + esc(c.need) + '">' +
            '<p class="sb-part-top"><span>' + needNum(data, c.need) + " · " + label + '</span><span class="sb-pill">' + STATUS_LABEL[c.status] + "</span></p>" +
            "<h3>" + esc(c.label) + '</h3><p class="sb-seg" aria-hidden="true">' + segs + "</p>" +
            '<p class="sb-pick">' + pick + "</p>" +
            '<p class="sb-part-foot"><span class="sb-teams">' + (teams.length ? marks + plural(teams.length, "team shipped this", "teams shipped this") : ok ? "" : "Watch this part") + "</span>" +
            "<span>" + plural(mine.length, "paper", "papers") + "</span></p></a></li>";
        };

        var gapPanel = function (c) {
          var g = (data.gaps || []).filter(function (x) { return x.need === c.need; })[0];
          var need = needs.filter(function (nd) { return nd.id === c.need; })[0];
          var tries = (g && g.try || []).map(function (t) {
            return '<a class="qchip" href="papers.html?q=' + encodeURIComponent(t) + '&amp;m=1">' + esc(t) + "</a>";
          }).join("");
          var why = c.related ? "The related papers below are the closest we have; you’ll need to adapt them."
            : c.considered ? "Scout read the " + plural(c.considered, "closest paper", "closest papers") + " for this part, and none fit your project well enough to show."
            : "Nothing in our library covers this part.";
          var scholar = need && need.query ? '<a class="sb-scholar" href="https://scholar.google.com/scholar?q=' + encodeURIComponent(need.query) + '" rel="noopener">Search all research on Google Scholar ↗</a>' : "";
          return '<div class="sb-open"><div><p class="sb-open-k">Open problem · ' + (c.related ? "no strong paper yet" : "no paper yet") + "</p>" +
            "<p class=\"sb-open-h\">" + why + "</p>" +
            (tries ? '<div class="sb-try"><span>Try searching for</span>' + tries + "</div>" : "") + scholar + "</div>" +
            (hasPlan ? '<button class="btn sb-watch-need" type="button" data-sb-watch>Watch for papers</button>' : "") + "</div>";
        };

        var scopeNote = function () {
          var lib = data.library || {};
          var n = lib.papers || data.searched;
          var range = lib.from && lib.to ? ", published between " + esc(longDay(lib.from)) + " and " + esc(longDay(lib.to)) : "";
          var sources = (lib.sources || []).length ? esc(lib.sources.join(" and ")) : "arXiv and Hugging Face Daily Papers";
          return '<p class="sx-scope"><b>A gap means nothing in our library fits, not that nobody has studied it.</b> ' +
            "Scout only searches " + (n ? Number(n).toLocaleString() + " " : "the ") + "AI papers from " + sources + range + ". " +
            "Older work, and research outside these areas, isn’t included.</p>";
        };

        var strongCount = plan.filter(function (p) { return p.fit === "strong"; }).length;
        var mins = strongCount * 8;
        var techniques = [];
        cases.forEach(function (c) { (c.tags || []).forEach(function (t) { if (techniques.indexOf(t) < 0 && techniques.length < 8) techniques.push(t); }); });
        var heading = description.length <= 170 ? description : (data.summary || description.slice(0, 160) + "…");
        var searchedLine = (data.searched ? "Searched " + Number(data.searched).toLocaleString() + " papers" : "Searched our papers") +
          (data.cases_searched ? " and " + Number(data.cases_searched).toLocaleString() + " company case studies" : "");

        out.innerHTML = '<div class="sb">' +
          '<header class="sb-hero"><div class="sb-hero-text">' +
          '<p class="sb-eyebrow"><b>/ Project Scout</b> · ' + (at ? "Your last Scout, " + esc(ago(at)) : "Build brief") + "</p>" +
          '<h2 class="sb-h">“' + esc(heading) + "”</h2>" +
          (heading !== description ? '<details class="sb-full"><summary>Your full description</summary><p>' + esc(description) + "</p></details>" : "") +
          '<p class="sb-meta">' + searchedLine + ' · <button type="button" data-sx-edit>Edit project</button> · <button type="button" data-sx-parts>Edit parts</button> · <button type="button" data-scout-new>Start over</button></p>' +
          '<div class="sb-tools">' + (hasPlan ? '<button class="btn btn-primary" type="button" data-sb-prompt><span>Copy brief for my AI assistant</span></button>' +
            '<button class="btn btn-outline" type="button" data-sb-share><span>Share link</span></button>' +
            '<button class="btn btn-outline" type="button" data-sb-md><span>Download as Markdown</span></button>' : "") + "</div></div>" +
          (cov.length ? readiness(cov) : "") + "</header>" +
          (cov.length ? '<section class="sb-map"><p class="sb-label"><span>/ Your build map</span><span>The parts of your project, in the order to build them</span></p>' +
            '<ol class="sb-parts">' + cov.map(mapCard).join("") + "</ol></section>" : "") +
          '<div class="sb-cols"><section class="sb-main">' +
          '<div class="sb-filters"><span data-sx-count></span><label><input type="checkbox" data-sx-toggle="code"> Code released</label>' +
          '<label><input type="checkbox" data-sx-toggle="recent"> Last 6 months</label></div>' +
          (data.mode === "basic" && hasPlan ? '<p class="sx-note">Relevance scoring was unavailable, so these are the closest papers by search and haven’t been checked for fit.</p>' : "") +
          ((data.expanded || []).length ? '<p class="sx-again">Searched again for: ' + data.expanded.map(function (q) { return "“" + esc(q) + "”"; }).join(", ") + ".</p>" : "") +
          '<div data-sx-list></div></section>' +
          '<aside class="sb-aside">' +
          (strongCount ? '<div class="sb-box"><p class="sb-box-k">Your reading plan</p><p class="sb-big">' + mins + " min</p>" +
            "<p>to read our summaries of the " + plural(strongCount, "strong paper", "strong papers") + ", about 8 minutes each.</p>" +
            '<p class="sb-plan-bar">' + cov.filter(function (c) { return c.strong; }).map(function (c) {
              return '<i style="flex:' + c.strong + '" title="Part ' + needNum(data, c.need) + ": " + plural(c.strong, "paper", "papers") + '"></i>';
            }).join("") + "</p></div>" : "") +
          (techniques.length ? '<div class="sb-box"><p class="sb-box-k">Techniques teams used</p><p class="sb-techs">' +
            techniques.map(function (t) { return '<a href="papers.html?q=' + encodeURIComponent(t) + '&amp;m=1">' + esc(t) + "</a>"; }).join("") + "</p></div>" : "") +
          '<div class="sb-box feedback" data-feedback="scout"><span data-feedback-q>Were these papers relevant?</span>' +
          '<button class="btn btn-outline btn-sm" type="button" data-vote="useful">Yes, relevant</button>' +
          '<button class="btn btn-outline btn-sm" type="button" data-vote="not_useful">Not really</button></div>' +
          "</aside></div>" +
          (cases.length ? '<section class="sb-cases"><p class="sb-label"><span>/ Built in production</span></p>' +
            '<div class="sb-cases-head"><div><h2>' + (cases.length === 1 ? "1 team already shipped something like this" : cases.length + " teams already shipped something like this") + "</h2>" +
            "<p>Read how they built it before you choose your design. These are real engineering write-ups from our Case studies.</p></div>" +
            '<a class="text-link" href="case-studies/index.html">See all case studies</a></div>' +
            '<ul class="cs-grid cs-plain sb-case-grid">' + cases.map(function (c) { return caseCard(c, data); }).join("") + "</ul></section>" : "") +
          (hasPlan ? '<section class="sb-watch"><div><h2>Get told when a paper fills <span>your gap.</span></h2>' +
            "<p>We check every new paper each morning against this project, and show matches on the home page. It stays in this browser.</p></div>" +
            '<button class="btn" type="button" data-scout-watch aria-pressed="false">Watch this project</button></section>' : "") +
          "</div>";

        var listEl = out.querySelector("[data-sx-list]");
        var countEl2 = out.querySelector("[data-sx-count]");
        var render = function () {
          var shown = plan.filter(function (p) {
            if (state.dismissed.indexOf(p.id) >= 0) return false;
            if (state.code && !p.code_url) return false;
            if (state.recent && String(p.submitted || p.first_seen || "") < sixMonthsAgo) return false;
            return true;
          });
          var parts = cov.length ? cov : [{ need: "", label: "Your project", status: shown.length ? "covered" : "missing", strong: 0, related: 0 }];
          var html = parts.map(function (c, i) {
            var mine = shown.filter(function (p) { return !c.need || home(p) === c.need; });
            var strong = mine.filter(function (p) { return p.fit !== "related"; });
            var related = mine.filter(function (p) { return p.fit === "related"; });
            var ok = c.status === "covered";
            var open = state.open[c.need] || !strong.length;
            var trends = (c.trends || []).map(function (t) {
              return '<span class="sb-trend ' + (t.dir === "down" ? "down" : "up") + '">' + esc(t.label) + " <b>" + esc(t.value) + "</b></span>";
            }).join("");
            return '<section class="sb-need" id="sb-need-' + esc(c.need) + '"><header><span class="sb-num' + (ok ? "" : " is-gap") + '">' + (needNum(data, c.need) || "01") + "</span>" +
              "<div><h2>" + esc(c.label) + "</h2>" + (trends ? '<p class="sb-trends">' + trends + "</p>" : "") + "</div></header>" +
              (ok ? "" : gapPanel(c)) +
              strong.map(entry).join("") +
              (related.length ? (open ? (strong.length ? '<p class="sb-split">Related <small>Close to your project, but would need adapting</small></p>' : "") + related.map(entry).join("")
                : '<button class="sb-more" type="button" data-sb-open="' + esc(c.need) + '">Show ' + plural(related.length, "related paper", "related papers") + "</button>") : "") +
              (!mine.length && ok ? '<p class="sx-empty"><b>No papers match these filters.</b>Clear a filter to see them again.</p>' : "") +
              "</section>";
          }).join("");
          if (!hasPlan) html = '<div class="sx-empty"><b>No relevant papers in our database yet.</b>Try naming the task and the data, for example “summarise legal contracts” instead of “legal AI app”.</div>' + html;
          if (cov.some(function (c) { return c.status !== "covered"; })) html += scopeNote();
          listEl.innerHTML = html;
          var nStrong = shown.filter(function (p) { return p.fit !== "related"; }).length;
          countEl2.textContent = data.mode === "basic" ? plural(shown.length, "paper", "papers") : nStrong + " strong, " + (shown.length - nStrong) + " related";
          Array.prototype.forEach.call(out.querySelectorAll("[data-sx-toggle]"), function (el) { el.checked = !!state[el.getAttribute("data-sx-toggle")]; });
        };
        var remember = function () {
          var last = load("apd.scout", null);
          if (last && last.description === description) { last.data.dismissed = state.dismissed; store("apd.scout", last); }
        };
        var watchBtn = out.querySelector("[data-scout-watch]");

        // One handler per paint (assigned, not added), so an older result's state can't answer clicks
        out.onclick = function (e) {
          var t = e.target.closest ? e.target : null;
          if (!t) return;
          var openBtn = t.closest("[data-sb-open]");
          if (openBtn) { state.open[openBtn.getAttribute("data-sb-open")] = true; render(); return; }
          if (t.closest("[data-sb-watch]") && watchBtn) {
            if (watchBtn.getAttribute("aria-pressed") !== "true") watchBtn.click();
            watchBtn.scrollIntoView({ behavior: "smooth", block: "center" });
            return;
          }
          var undo = t.closest("[data-sx-undo]");
          if (undo) { var u = undo.getAttribute("data-sx-undo"); state.dismissed = state.dismissed.filter(function (x) { return x !== u; }); remember(); render(); return; }
          var cs = t.closest("[data-sb-case-save]");
          if (cs) {
            var url = cs.getAttribute("data-sb-case-save"), cid = "cs:" + url;
            var c = cases.filter(function (x) { return x.url === url; })[0] || {};
            var was = saved.some(function (s) { return s.id === cid; });
            saved = was ? saved.filter(function (s) { return s.id !== cid; }) : [{ id: cid, t: c.title, u: url, c: c.company, at: Date.now() }].concat(saved);
            store("apd.saved", saved);
            cs.setAttribute("aria-pressed", was ? "false" : "true");
            cs.querySelector("span").textContent = was ? "Save" : "Saved";
            showSavedCount();
            return;
          }
          if (t.closest("[data-sb-case]")) { track("site", "scout_case"); return; }
          var card = t.closest(".sb-paper");
          if (!card) return;
          var pid = card.getAttribute("data-id");
          var p = plan.filter(function (x) { return x.id === pid; })[0];
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
            sv.setAttribute("aria-label", on ? "Save this paper" : "Saved");
            sv.textContent = on ? "+" : "✓";
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
        out.querySelector("[data-sx-parts]").addEventListener("click", function () {
          scoutWrap.classList.remove("has-results");
          out.onclick = null;
          paintSplit({ summary: data.summary, needs: data.needs, planned: true }, description, true);
        });
        out.querySelector("[data-sx-edit]").addEventListener("click", function () {
          scoutWrap.classList.remove("has-results");
          desc.value = description; paintCount(); desc.focus();
          scoutForm.scrollIntoView({ behavior: "smooth", block: "start" });
        });
        var copyText = function (btn, text, done) {
          if (navigator.clipboard) navigator.clipboard.writeText(text).then(function () { confirmLabel(btn, done); });
        };
        var promptBtn = out.querySelector("[data-sb-prompt]");
        if (promptBtn) promptBtn.addEventListener("click", function () { copyText(promptBtn, asPrompt(data, description), "Copied. Paste it into your AI assistant"); track("site", "scout_brief"); });
        var shareBtn = out.querySelector("[data-sb-share]");
        if (shareBtn) shareBtn.addEventListener("click", function () {
          var url = location.origin + location.pathname + "?project=" + encodeURIComponent(description);
          copyText(shareBtn, url, "Link copied");
        });
        var mdBtn = out.querySelector("[data-sb-md]");
        if (mdBtn) mdBtn.addEventListener("click", function () {
          var blob = new Blob([asMarkdown(data, description)], { type: "text/markdown" });
          var a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = "scout-brief.md";
          document.body.appendChild(a); a.click(); a.remove();
          setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
        });
        if (watchBtn && window.apdWatch) window.apdWatch.wire(watchBtn, data, description);
        scoutWrap.classList.add("has-results");
        if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitScoutChips); else fitScoutChips();
      });
    };
    // One row of chips per card, like All papers: chips that would be cut off are hidden
    var fitScoutChips = function () {
      Array.prototype.forEach.call(out.querySelectorAll(".sb-tags"), function (row) {
        var kids = row.children, right = row.getBoundingClientRect().right + 0.5, cut = false;
        for (var i = 0; i < kids.length; i++) {
          kids[i].hidden = false;
          if (cut || kids[i].getBoundingClientRect().right > right) { kids[i].hidden = true; cut = true; }
        }
      });
    };

    var scoutNames = {};
    try { scoutNames = JSON.parse(scoutForm.getAttribute("data-names")) || {}; } catch (e) { /* slugs */ }

    var LOADING = ["Reading your description…", "Searching by meaning and by keywords…", "Scoring each paper for your project…"];
    var loading = function (from, only) {
      var step = from || 0;
      out.innerHTML = '<div class="card pad scout-loading" aria-busy="true"><span class="label" data-loading-text>' + LOADING[step] + "</span>" +
        '<span class="pixbar pixbar-run" aria-hidden="true">' + new Array(9).join("<i></i>") + "</span></div>" +
        '<div class="plan-skeleton" aria-hidden="true"><i></i><i></i><i></i></div>';
      var label = out.querySelector("[data-loading-text]");
      return setInterval(function () { if (only) return; step = Math.min(step + 1, LOADING.length - 1); label.textContent = LOADING[step]; }, 2500);
    };

    var post = function (body) {
      goal("scout_search", "Scout search");
      return callApi(scoutForm.getAttribute("data-url"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      }, 90000).then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok, status: r.status, data: d }; });
      });
    };
    var failed = function (title, res) {
      out.innerHTML = '<div class="card pad empty-card"><span class="label">' + title + "</span><p>" +
        esc((res && res.data && res.data.error) || "Scout is unavailable right now. Try again in a minute.") + "</p></div>";
    };
    var offline = function () {
      out.innerHTML = '<div class="card pad empty-card"><span class="label">Couldn’t reach Scout</span><p>' +
        (navigator.onLine === false ? "You’re offline. Reconnect and try again." : "That took too long or the connection dropped. Please try again.") + "</p></div>";
    };
    var busy = function (on, label) {
      goBtn.disabled = on;
      goBtn.textContent = on ? label : "Find papers";
    };

    // ---- Step 2: show how Scout split the project, and let the visitor edit it ----
    var MAX_PARTS = 4;
    var firstWords = function (text, n) { return text.split(/\s+/).slice(0, n).join(" "); };
    var paintSplit = function (split, description, fromResults) {
      var parts = (split.needs || []).map(function (nd) { return { label: nd.label || "", query: nd.query || "" }; });
      var guessed = !parts.length;
      if (guessed) parts = [{ label: "Your project", query: firstWords(description, 12) }];
      var summary = split.summary || "";

      var row = function (p, i) {
        var n = i + 1;
        return '<li class="parts-row" style="--n:' + NEED_COLORS[i % NEED_COLORS.length] + '">' +
          '<span class="parts-n" aria-hidden="true">' + n + "</span>" +
          '<div class="parts-fields">' +
          '<label class="parts-field"><span class="parts-lab">Part ' + n + '</span>' +
          '<input class="input parts-name" type="text" maxlength="60" value="' + esc(p.label) + '" data-part-label="' + i + '" placeholder="For example: Speech to text"></label>' +
          '<label class="parts-field"><span class="parts-lab">Searches for</span>' +
          '<input class="input parts-query" type="text" maxlength="160" value="' + esc(p.query) + '" data-part-query="' + i + '" placeholder="A few words a paper on this part would use"></label>' +
          "</div>" +
          '<button class="parts-del" type="button" data-part-del="' + i + '" aria-label="Remove part ' + n + '"' + (parts.length < 2 ? " disabled" : "") + ">✕</button></li>";
      };
      var paint = function () {
        out.innerHTML = '<div class="card pad parts" data-parts>' +
          '<h2 class="parts-title">How Scout split your project</h2>' +
          (summary ? '<p class="parts-summary">' + esc(summary) + "</p>" : "") +
          '<p class="parts-help">' + (guessed
            ? "Scout couldn’t split this one automatically, so it will search your description as a single part. Add the parts your project depends on for better results."
            : "Scout searches each part on its own, then scores every paper it finds against your whole project. Rename a part, change what it searches for, remove one, or add a part it missed.") + "</p>" +
          '<ol class="parts-list">' + parts.map(row).join("") + "</ol>" +
          (parts.length < MAX_PARTS ? '<button class="parts-add" type="button" data-part-add>+ Add a part</button>' : '<p class="fine">Scout searches up to ' + MAX_PARTS + " parts.</p>") +
          '<p class="field-error parts-error" data-split-error role="alert" hidden></p>' +
          '<div class="parts-acts"><button class="btn btn-primary" type="button" data-split-go>Find papers for ' + (parts.length === 1 ? "this part" : "these " + parts.length + " parts") + "</button>" +
          '<button class="btn btn-outline" type="button" data-split-back>' + (fromResults ? "Back to results" : "Change description") + "</button></div></div>";
        wire();
      };
      var collect = function () {
        Array.prototype.forEach.call(out.querySelectorAll("[data-part-label]"), function (el) { parts[+el.getAttribute("data-part-label")].label = el.value; });
        Array.prototype.forEach.call(out.querySelectorAll("[data-part-query]"), function (el) { parts[+el.getAttribute("data-part-query")].query = el.value; });
      };
      var problemOf = function (list) {
        var filled = list.filter(function (p) { return p.query.trim(); });
        if (!filled.length) return "Add at least one part with something to search for.";
        for (var k = 0; k < list.length; k++) {
          var q = list[k].query.trim();
          if (!q && list[k].label.trim()) return "Part " + (k + 1) + " needs something to search for.";
          if (q && q.split(/\s+/).length > 14) return "Keep the search for part " + (k + 1) + " under 15 words.";
          if (looksLikeCode(list[k].query) || looksLikeCode(list[k].label)) return "Describe part " + (k + 1) + " in plain words, not code.";
        }
        return "";
      };
      var showErr = function (msg) {
        var el = out.querySelector("[data-split-error]");
        el.textContent = msg; el.hidden = !msg;
      };
      var wire = function () {
        var box = out.querySelector("[data-parts]");
        box.addEventListener("input", function () { showErr(""); });
        box.addEventListener("focusout", function (e) {
          if (e.target.matches && e.target.matches("[data-part-query]")) { collect(); var m = problemOf(parts.filter(function (p) { return p.query.trim(); })); if (m) showErr(m); }
        });
        var add = out.querySelector("[data-part-add]");
        if (add) add.addEventListener("click", function () {
          collect(); parts.push({ label: "", query: "" }); paint();
          var inputs = out.querySelectorAll("[data-part-label]");
          inputs[inputs.length - 1].focus();
        });
        Array.prototype.forEach.call(out.querySelectorAll("[data-part-del]"), function (b) {
          b.addEventListener("click", function () {
            collect(); parts.splice(+b.getAttribute("data-part-del"), 1); paint();
            var first = out.querySelector("[data-part-label]");
            if (first) first.focus();
          });
        });
        out.querySelector("[data-split-back]").addEventListener("click", function () {
          if (fromResults) { var last = load("apd.scout", null); if (last && last.data) { paintPlan(last.data, last.description || description, last.at); return; } }
          out.innerHTML = introHtml; desc.focus();
        });
        out.querySelector("[data-split-go]").addEventListener("click", function () {
          collect();
          var msg = problemOf(parts);
          if (msg) { showErr(msg); return; }
          var send = parts.filter(function (p) { return p.query.trim(); }).map(function (p) {
            return { label: p.label.trim() || p.query.trim(), query: p.query.trim() };
          });
          runSearch(description, { summary: summary, needs: send });
        });
      };
      paint();
      out.scrollIntoView({ behavior: "smooth", block: "start" });
      var firstInput = out.querySelector("[data-part-label]");
      if (firstInput && guessed) firstInput.focus();
    };

    // ---- Step 3: search with the checked parts, then show the papers ----
    var runSearch = function (text, split) {
      busy(true, "Finding papers…");
      var timer = loading(1);
      post({ description: text, summary: split.summary, needs: split.needs }).then(function (res) {
        clearInterval(timer);
        if (res.ok && !Array.isArray(res.data.plan)) res = { ok: false, status: 502, data: {} };  // a broken reply
        if (!res.ok) {
          if (res.status === 400 && /characters/.test(res.data.error || "")) showProblem(res.data.error || "");
          if (res.status === 400 && res.data.error && !/characters|looks like code/.test(res.data.error)) {
            paintSplit(split, text, false);
            var el = out.querySelector("[data-split-error]");
            el.textContent = res.data.error; el.hidden = false;
            return;
          }
          failed("Couldn’t find papers", res);
          return;
        }
        store("apd.scout", { description: text, data: res.data, at: Date.now() });
        paintPlan(res.data, text, 0);
        out.scrollIntoView({ behavior: "smooth", block: "start" });
      }).catch(function () { clearInterval(timer); offline(); }).then(function () { busy(false); });
    };

    // ---- Step 1: the description, split into parts by Scout ----
    scoutForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var text = desc.value.replace(/\s+/g, " ").trim();
      var problem = problemWith(text);
      if (problem) { showProblem(problem); desc.focus(); return; }
      showProblem("");
      busy(true, "Reading your project…");
      var timer = loading(0, true);
      post({ description: text, step: "split" }).then(function (res) {
        clearInterval(timer);
        if (!res.ok) {
          if (res.status === 400 || /code|characters/.test(res.data.error || "")) showProblem(res.data.error || "");
          failed("Couldn’t read your project", res);
          return;
        }
        paintSplit(res.data || {}, text, false);
      }).catch(function () { clearInterval(timer); offline(); }).then(function () { busy(false); });
    });

    // Bring back the last plan from this browser
    // A shared brief link (scout.html?project=...) fills in the description, ready to run
    var shared = new URLSearchParams(location.search).get("project");
    if (shared) {
      desc.value = shared.slice(0, 1000);
      paintCount();
      desc.focus();
    }
    var last = shared ? null : load("apd.scout", null);
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

  // ---- Case studies: the topic chips scroll sideways; fade the edge with more chips, arrows to scroll ----
  document.querySelectorAll("[data-cs-chipbar]").forEach(function (bar) {
    var row = bar.querySelector("[data-cs-chips]");
    var prev = bar.querySelector("[data-cs-chip-prev]");
    var next = bar.querySelector("[data-cs-chip-next]");
    if (!row) return;
    var still = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
    var how = still ? "auto" : "smooth";
    bar.setAttribute("data-js", "");
    var paint = function () {
      var max = row.scrollWidth - row.clientWidth;
      var x = Math.abs(row.scrollLeft);
      var left = max > 1 && x > 1, right = max > 1 && x < max - 1;
      bar.toggleAttribute("data-left", left);
      bar.toggleAttribute("data-right", right);
      if (prev) prev.hidden = !left;
      if (next) next.hidden = !right;
    };
    var step = function (dir) {
      row.scrollBy({ left: dir * Math.max(160, row.clientWidth * 0.7), behavior: how });
    };
    if (prev) prev.addEventListener("click", function () { step(-1); });
    if (next) next.addEventListener("click", function () { step(1); });
    row.addEventListener("scroll", paint, { passive: true });
    if (window.ResizeObserver) new ResizeObserver(paint).observe(row); else window.addEventListener("resize", paint);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(paint);  // chip widths change once the font loads
    // A chip reached with Tab scrolls fully into view, clear of the faded edge (scroll-padding in style.css)
    row.addEventListener("focusin", function (e) {
      if (e.target && e.target.scrollIntoView) e.target.scrollIntoView({ block: "nearest", inline: "nearest", behavior: how });
    });
    // On a topic page, its own chip starts in view
    var here = row.querySelector("[aria-current]");
    if (here && here.offsetLeft + here.offsetWidth > row.clientWidth) {
      row.scrollLeft = here.offsetLeft - (row.clientWidth - here.offsetWidth) / 2;
    }
    paint();
  });

  // ---- Case studies: search, company and tag filters, showing more, and Save ----
  (function () {
    // One listener for every Save button, so the cards case-finder.js draws later work too
    function paintSaves() {
      document.querySelectorAll("[data-cs-save]").forEach(function (b) {
        var on = saved.some(function (s) { return s.id === b.getAttribute("data-cs-save"); });
        b.setAttribute("aria-pressed", on ? "true" : "false");
        b.querySelector("span").textContent = on ? "Saved" : "Save";
      });
    }
    document.addEventListener("click", function (e) {
      var btn = e.target.closest && e.target.closest("[data-cs-save]");
      if (!btn) return;
      var id = btn.getAttribute("data-cs-save");
      var on = saved.some(function (s) { return s.id === id; });
      saved = on ? saved.filter(function (s) { return s.id !== id; })
                 : [{ id: id, t: btn.getAttribute("data-title"), u: btn.getAttribute("data-url"),
                      c: btn.getAttribute("data-co"), at: Date.now() }].concat(saved);
      store("apd.saved", saved);
      paintSaves();
      showSavedCount();
    });
    document.addEventListener("cs:cards", paintSaves);
    paintSaves();

    var list = document.querySelector("[data-cs-list]");
    var q = document.querySelector("[data-cs-q]");
    if (!list || !q) return;
    var company = document.querySelector("[data-cs-company]");
    var sections = document.querySelector("[data-cs-sections]");
    var results = document.querySelector("[data-cs-results]");
    var none = document.querySelector("[data-cs-none]");
    var count = document.querySelector("[data-cs-count]");
    var more = document.querySelector("[data-cs-more]");
    var active = document.querySelector("[data-cs-active]");
    var items = Array.prototype.slice.call(list.querySelectorAll("[data-cs-item]"));
    var page = parseInt(list.getAttribute("data-cs-paged") || "24", 10);
    var shown = page, tag = "";

    function apply() {
      var words = q.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
      var co = company ? company.value : "";
      var filtering = words.length > 0 || !!co || !!tag;
      // On the main page the topic sections show until someone searches or filters
      if (sections) { sections.hidden = filtering; results.hidden = !filtering; }
      var matches = 0;
      items.forEach(function (el) {
        var ok = (!co || el.getAttribute("data-co") === co) &&
          (!tag || el.getAttribute("data-tags").indexOf("|" + tag + "|") >= 0) &&
          words.every(function (w) { return el.getAttribute("data-t").indexOf(w) >= 0; });
        if (ok) matches++;
        el.hidden = !ok || matches > shown;
      });
      document.querySelectorAll("[data-cs-tag]").forEach(function (b) {
        b.setAttribute("aria-pressed", b.getAttribute("data-cs-tag") === tag ? "true" : "false");
      });
      if (active) {
        active.hidden = !tag;
        active.querySelector("[data-cs-active-name]").textContent = tag;
      }
      if (none) none.hidden = matches > 0;
      if (count) count.textContent = matches + (matches === 1 ? " write-up" : " write-ups");
      if (more) more.hidden = matches <= shown;
    }
    function reset() { shown = page; apply(); }

    q.addEventListener("input", reset);
    if (company) company.addEventListener("change", reset);
    document.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("[data-cs-tag]");
      if (!b) return;
      var t = b.getAttribute("data-cs-tag");
      tag = tag === t ? "" : t;
      reset();
      if (tag) (results || list).scrollIntoView({ behavior: "smooth", block: "start" });
    });
    var clearTag = document.querySelector("[data-cs-clear-tag]");
    if (clearTag) clearTag.addEventListener("click", function () { tag = ""; reset(); });
    var apMore = document.querySelector("[data-cs-ap-more]");
    if (apMore) apMore.addEventListener("click", function () {
      document.querySelectorAll(".cs-ap [data-cs-ap-extra]").forEach(function (b) { b.hidden = false; });
      apMore.hidden = true;
    });
    var resetAll = document.querySelector("[data-cs-reset]");
    if (resetAll) resetAll.addEventListener("click", function () {
      q.value = ""; tag = "";
      if (company) company.value = "";
      reset();
    });
    if (more) more.addEventListener("click", function () { shown += page; apply(); });
  })();

  // ---- All papers: cards, quick views and search over data/papers.json ----
  // Short keys are documented in compact() in site_builder.py.
  var results = document.getElementById("results");
  // By lab page: show companies, universities or other labs
  (function () {
    var grid = document.querySelector("[data-labs]");
    if (!grid) return;
    var kinds = Array.prototype.slice.call(document.querySelectorAll("[data-lab-kind]"));
    var count = document.querySelector("[data-lab-count]");
    var all = count.textContent;
    // Show the biggest 30 labs first; the rest wait behind "Show all labs"
    var LIMIT = 30, kind = "", open = false;
    var moreBtn = document.createElement("button");
    moreBtn.type = "button"; moreBtn.className = "btn btn-outline"; moreBtn.hidden = true;
    var moreWrap = document.createElement("div");
    moreWrap.className = "center"; moreWrap.appendChild(moreBtn);
    grid.parentNode.insertBefore(moreWrap, grid.nextSibling);
    function paint() {
      var n = 0;
      Array.prototype.forEach.call(grid.querySelectorAll(".lab-card"), function (c) {
        var fits = !kind || c.getAttribute("data-kind") === kind;
        if (fits) n++;
        c.hidden = !fits || (!open && n > LIMIT);
      });
      moreBtn.hidden = open || n <= LIMIT;
      moreBtn.textContent = "Show all " + n + " labs";
      return n;
    }
    moreBtn.addEventListener("click", function () { open = true; paint(); });
    paint();
    kinds.forEach(function (b) {
      b.addEventListener("click", function () {
        kind = b.getAttribute("data-lab-kind"); open = false;
        kinds.forEach(function (o) { o.setAttribute("aria-pressed", o === b ? "true" : "false"); });
        var n = paint();
        count.textContent = kind ? n + " " + b.textContent.toLowerCase() : all;
      });
    });
  })();

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
    "": { label: "papers, with our picks, new and trending mixed in", mix: true },
    "new": { label: "papers, newest first" },
    week: { label: "most upvoted papers of the last 7 days",
            keep: function (p) { return p.u > 0 && (p.w || p.d) >= weekAgo(); },
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
  var lab = params.get("lab") || "";  // ?lab=NVIDIA, from the By lab page and the lab names on cards

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

  // Words that can follow a number and say what it measures ("4x faster", "38% less")
  var STAT_WORDS = /^(faster|slower|less|more|fewer|smaller|larger|bigger|cheaper|better|higher|lower|speedup|speed-up|reduction|improvement|gain|memory|compute|accuracy|cost|latency|throughput|parameters|params|tokens|weights|compression|error|errors)$/i;
  var STAT_STOP = /^(with|than|on|in|for|by|and|at|to|without|of|over|while|from|across|the|a|an|vs)$/i;
  // The cover's headline number, read from the summary or title: "4×", "−38%", "2-bit"
  function coverStat(p) {
    var texts = [p.m || "", p.t || ""];
    for (var i = 0; i < texts.length; i++) {
      var m = /(^|[\s(])([−-]?\d+(?:\.\d+)?)(\s?[x×%]|-bit)(?=[\s,.;:)]|$)/i.exec(texts[i]);
      if (!m) continue;
      var unit = m[3].trim().toLowerCase();
      var value = m[2].replace("-", "−") + (unit === "x" ? "×" : unit);
      var words = texts[i].slice(m.index + m[0].length).replace(/^[\s,;:]+/, "").split(/\s+/);
      var caption = [];
      for (var w = 0; w < words.length && caption.length < 2; w++) {
        var word = words[w].replace(/[.,;:)]+$/, "");
        if (!word || STAT_STOP.test(word)) break;
        if (!caption.length && !STAT_WORDS.test(word)) break;
        caption.push(word.toLowerCase());
        if (/[.,;:)]$/.test(words[w])) break;
      }
      return { value: value, caption: caption.length ? caption.join(" ") : "key result" };
    }
    if (p.u) return { value: '<small aria-hidden="true">▲</small>' + p.u, caption: "upvotes on Hugging Face", html: true };
    if ((p.w || p.d) === newest) return { value: "New", caption: "in the latest batch" };
    return { value: esc(shortDate(p.d)), caption: "published", html: true };
  }

  // "today", "yesterday", or a short date, by the visitor's own calendar
  function relDay(iso) {
    var now = new Date(), pad = function (n) { return (n < 10 ? "0" : "") + n; };
    var key = function (d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); };
    if (iso === key(now)) return "today";
    now.setDate(now.getDate() - 1);
    if (iso === key(now)) return "yesterday";
    return shortDate(iso);
  }

  // Each card shows one row of chips; drop the ones that would be cut off at the edge
  function fitChips() {
    Array.prototype.forEach.call(results.querySelectorAll(".pcard-tags"), function (row) {
      // Measure on screen: a chip that ends past the row's right edge is hidden, and so is every chip after it
      var kids = row.children, right = row.getBoundingClientRect().right + 0.5, cut = false;
      for (var i = 0; i < kids.length; i++) {
        kids[i].hidden = false;
        if (cut || kids[i].getBoundingClientRect().right > right) { kids[i].hidden = true; cut = true; }
      }
    });
  }
  var fitTimer;
  window.addEventListener("resize", function () { clearTimeout(fitTimer); fitTimer = setTimeout(fitChips, 150); });

  // A chip with a small ⓘ that explains it on hover, focus or tap
  function infoChip(cls, label, tip) {
    return '<button class="sig sig-info ' + cls + '" type="button" aria-label="' + esc(label) + ': what this means">' + esc(label) +
      '<span class="sig-i" aria-hidden="true">i</span><span class="sig-tip" role="tooltip">' + tip + "</span></button>";
  }

  // The lab's square mark, drawn like site_builder.lab_mark (LABS_SVG is set above, before Project Scout)
  function labMark(p) {
    if (p.oi) {
      return '<span class="org-mark has-img" aria-hidden="true"><img src="' + esc(LABS_SVG.replace(/labs\.svg(\?.*)?$/, "logos/") + p.oi) +
        '" alt="" width="40" height="40" loading="lazy" decoding="async"></span>';
    }
    var c = (p.oc || "").split("/");
    var style = c[0] ? ' style="--lab:#' + esc(c[0]) + ";--lab-ink:#" + esc(c[1] || "fff") + '"' : "";
    var inner;
    if (p.ol) {
      inner = '<svg viewBox="0 0 24 24"><use href="' + esc(LABS_SVG) + "#lab-" + esc(p.ol) + '"></use></svg>';
    } else {
      var words = p.o.replace(/[^A-Za-z0-9 ]/g, "").split(" ").filter(Boolean), mark;
      if (words.length === 1 && words[0].length <= 4) mark = words[0];
      else if (words.length === 1) { var caps = words[0].replace(/[^A-Z]/g, ""); mark = caps.length >= 2 ? caps.slice(0, 2) : words[0][0].toUpperCase(); }
      else mark = (words[0][0] + words[1][0]).toUpperCase();
      inner = '<span class="lm-' + Math.min(mark.length, 4) + '">' + esc(mark) + "</span>";
    }
    return '<span class="org-mark' + (p.ol ? " has-logo" : "") + '"' + style + ' aria-hidden="true">' + inner + "</span>";
  }

  function card(p) {
    var local = onSite[p.i];
    var read = readIds[p.i];
    var href = local ? "paper/" + esc(p.i) + ".html" : "https://huggingface.co/papers/" + esc(p.i);
    var topic = (p.c && p.c[0]) || "other-ml";
    var isSaved = saved.some(function (s) { return s.id === p.i; });
    var stat = coverStat(p);
    var badge = "";
    if (p.f === 1) badge = '<span class="pc-badge pc-badge-pick">★ Our pick</span>';
    else if (p.f === 2) badge = '<span class="pc-badge pc-badge-hot">Trending</span>';
    else if (newest && (p.w || p.d) >= newest) badge = '<span class="pc-badge pc-badge-new">New</span>';
    else if (p.h) badge = '<span class="pc-badge" title="Not on the Hugging Face daily list">Not on HF yet</span>';
    var chips = "";
    if (p.u && stat.caption !== "upvotes on Hugging Face") chips += '<span class="sig sig-up" title="Upvotes on Hugging Face">▲ ' + p.u + "</span>";
    var used = [];
    if (p.um) used.push(p.um + (p.um === 1 ? " model" : " models"));
    if (p.us) used.push(p.us + (p.us === 1 ? " Space" : " Spaces"));
    if (used.length) chips += infoChip("sig-used", "Used in " + used.join(" · "),
      "<b>Models</b> are AI models shared on Hugging Face whose page links this paper, usually because they were built with its method." +
      " <b>Spaces</b> are demo apps on Hugging Face that use it. Higher numbers mean more people are building on this work.");
    if (p.gs) chips += infoChip("", "★ " + (p.gs >= 1000 ? (p.gs / 1000).toFixed(1).replace(/\.0$/, "") + "k" : p.gs),
      "Stars on the paper’s code on GitHub. Developers star a project to bookmark or follow it, so it shows how much interest the code has.");
    if (p.k) chips += '<span class="sig">Code</span>';
    if (p.l) chips += '<span class="sig">' + LEVEL[p.l] + "</span>";
    if (read) chips += '<span class="pcard-read">✓ Read</span>';
    // Other topics the paper belongs to fill the chip row when there are few signals
    (p.c || []).slice(1, 3).forEach(function (t) {
      chips += '<a class="sig sig-topic t-' + esc(t) + '" href="papers.html?cat=' + esc(t) + '"><span class="dot"></span>' + esc(names[t] || t) + "</a>";
    });
    if (!chips && p.ac) chips += '<span class="sig sig-arxiv" title="arXiv subject category">arXiv ' + esc(p.ac) + "</span>";
    var authors = (p.a || []).slice(0, 2).map(esc).join(", ");
    var extra = (p.n || 0) - Math.min(2, (p.a || []).length);
    if (extra > 0) authors += " +" + extra;
    return '<article class="pcard t-' + esc(topic) + (read ? " is-read" : "") + '" data-id="' + esc(p.i) + '">' +
      '<div class="pc-cover">' +
        '<div class="pc-cover-top"><a class="pc-topic" href="papers.html?cat=' + esc(topic) + '"><span class="dot"></span>' +
          esc(names[topic] || topic) + "</a>" + badge +
          (local ? "" : '<span class="pc-ext" title="Opens on Hugging Face">HF ↗</span>') + "</div>" +
        '<div class="pc-word" aria-hidden="true">' + esc(COVER_WORD[topic] || "ML") + "</div>" +
        '<div class="pc-stat"><b>' + (stat.html ? stat.value : esc(stat.value)) + "</b><span>" + esc(stat.caption) + "</span></div>" +
      "</div>" +
      '<div class="pc-body">' + /* display: contents, its children sit on the card's subgrid rows */
        '<p class="pcard-by">' + (p.o ? labMark(p) + '<a class="org-name" href="papers.html?lab=' + encodeURIComponent(p.o) + '" title="More papers from ' + esc(p.o) + '">' + esc(p.o) + "</a>" + (authors ? '<span class="by-sep">·</span>' : "") : "") +
          '<span class="by-auth">' + authors + "</span></p>" +
        '<h3 title="' + esc(p.t) + '"><a href="' + href + '"' + (local ? "" : ' rel="noopener"') + ">" + esc(p.t) + "</a></h3>" +
        // Fixed-size text areas (2-line title, 2-line summary, one byline, one chip row) keep every card the same shape
        '<p class="pcard-sum">' + esc(p.m || "") + "</p>" +
        '<div class="pcard-tags">' + chips + "</div>" +
        '<div class="pcard-foot"><p class="pcard-dates"><span class="date-pill is-pub"><span class="dp-k">Published</span><time datetime="' + esc(p.d) + '">' + esc(shortDate(p.d)) + "</time></span>" +
          (p.w && p.w !== p.d ? '<span class="date-pill is-added' + (relDay(p.w) === "today" ? " is-today" : "") + '"><span class="dp-k">Added</span><time datetime="' + esc(p.w) + '">' + esc(relDay(p.w)) + "</time></span>" : "") + "</p>" +

          '<button class="quick-save" type="button" data-quick-save="' + esc(p.i) + '" data-title="' + esc(p.t) +
          '" aria-pressed="' + isSaved + '" aria-label="Save this paper">' + (isSaved ? "✓" : "+") + "</button></div>" +
      "</div></article>";
  }

  // A search function result in the short form card() expects
  function fromSearch(r) {
    var authors = r.authors || [];
    var known = byId[r.id] || {};
    return { i: r.id, t: r.title, a: authors.slice(0, 3), n: authors.length,
             c: (r.categories && r.categories.length) ? r.categories : ["other-ml"],
             d: String(r.submitted || r.first_seen || "").slice(0, 10), s: 0, f: known.f || (r.featured ? 1 : 0),
             w: known.w || String(r.first_seen || "").slice(0, 10), ac: known.ac,
             m: known.m || "", u: known.u || r.hf_upvotes || 0, k: known.k, h: known.h, l: known.l, x: known.x, o: known.o, ol: known.ol, oc: known.oc, oi: known.oi };
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
      fitChips();
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitChips);
    }
    shown = Math.min(shown + PAGE, matches.length);
    more.hidden = shown >= matches.length;
    if (meaning.checked && q.value.trim().length >= 3) {
      count.textContent = matches.length + " papers closest in meaning, best match first";
    } else {
      var n = matches.length.toLocaleString();
      count.textContent = view ? n + " " + VIEWS[view].label
        : matches.length === all.length ? n + " " + VIEWS[""].label : n + " of " + all.length.toLocaleString() + " papers";
    }
    if (lab) {
      if (!(meaning.checked && q.value.trim().length >= 3)) {
        count.textContent = matches.length.toLocaleString() + (view ? " " + VIEWS[view].label : matches.length === 1 ? " paper" : " papers") + " from";
      }
      var pill = document.createElement("button");
      pill.type = "button"; pill.className = "lab-filter"; pill.setAttribute("data-clear-lab", "");
      pill.setAttribute("aria-label", "Show papers from every lab");
      pill.textContent = lab + " ×";
      count.appendChild(document.createTextNode(" "));
      count.appendChild(pill);
    }
  }

  // The default view: a steady blend, so the first screen always holds a
  // top pick, something just added, something people are upvoting, and
  // then the wider library, instead of only the newest day.
  function mix(list) {
    var day = function (p) { return p.w || p.d || ""; };
    var fresh0 = newest ? new Date(Date.parse(newest) - 2 * 864e5).toISOString().slice(0, 10) : "";
    var week = weekAgo();
    var picks = list.filter(function (p) { return p.f === 1; })
      .sort(function (a, b) { return day(b) < day(a) ? -1 : day(b) > day(a) ? 1 : 0; });
    var hot = list.filter(function (p) { return p.f === 2 || (p.u > 0 && day(p) >= week); })
      .sort(function (a, b) { return ((b.f === 2) - (a.f === 2)) || (b.u - a.u); });
    var fresh = list.filter(function (p) { return day(p) >= fresh0; })
      .sort(function (a, b) { return (b.s || 0) - (a.s || 0); });
    var queues = [picks, fresh, hot, fresh, list], at = [0, 0, 0, 0, 0];
    var seen = {}, out = [], left = true;
    while (out.length < list.length && left) {
      left = false;
      for (var k = 0; k < queues.length; k++) {
        var qu = queues[k];
        while (at[k] < qu.length && seen[qu[at[k]].i]) at[k]++;
        if (at[k] < qu.length) { seen[qu[at[k]].i] = true; out.push(qu[at[k]]); at[k]++; left = true; }
      }
    }
    return out;
  }

  function keepFiltered(list) {
    var v = VIEWS[view];
    return list.filter(function (p) {
      if (cat.value && p.c.indexOf(cat.value) < 0) return false;
      if (lab && p.o !== lab) return false;
      if (v.keep && !v.keep(p)) return false;
      return true;
    });
  }

  function searchByMeaning() {
    var token = ++searchToken;
    results.setAttribute("aria-busy", "true");
    results.innerHTML = new Array(7).join('<div class="pcard skeleton" aria-hidden="true"><span></span><span></span><span></span></div>');
    count.textContent = "Searching by meaning…";
    goal("search_meaning", "Search by meaning");
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
    else if (VIEWS[view].mix && !words.length) matches = mix(matches);
    render(true);
    syncUrl();
  }

  function syncUrl() {
    var u = new URLSearchParams();
    if (q.value) u.set("q", q.value);
    if (cat.value) u.set("cat", cat.value);
    if (view) u.set("view", view);
    if (meaning.checked) u.set("m", "1");
    if (lab) u.set("lab", lab);
    history.replaceState(null, "", u.toString() ? "?" + u : location.pathname);
  }

  var timer;
  q.addEventListener("input", function () {
    clearTimeout(timer);
    // A few words describing an idea search by meaning; a title or name searches by words
    meaning.checked = q.value.trim().split(/\s+/).length >= 4;
    timer = setTimeout(apply, meaning.checked ? 450 : 120);  // wait for a pause before asking the server
  });
  [cat, meaning].forEach(function (el) { el.addEventListener("change", apply); });
  chips.forEach(function (c) {
    c.addEventListener("click", function () { view = c.getAttribute("data-view"); apply(); });
  });
  more.addEventListener("click", function () { render(false); });
  count.addEventListener("click", function (e) {
    if (!e.target.closest || !e.target.closest("[data-clear-lab]")) return;
    lab = "";
    apply();
  });
  results.addEventListener("click", function (e) {
    if (!e.target.closest || !e.target.closest("[data-clear]")) return;
    q.value = ""; cat.value = ""; view = ""; meaning.checked = false; lab = "";
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
        if ((p.w || p.d) > newest) newest = p.w || p.d;
      });
      apply();
    })
    .catch(function () {
      results.removeAttribute("aria-busy");
      results.innerHTML = "";
      count.textContent = "We could not load the paper list. Reload the page to try again.";
    });


})();

// ---- Paper page, reading layout: the title opens large, then shrinks into the side column as you scroll ----
(function () {
  // Opening screen: the title is sized so it, the paper details and the first
  // lines of the paper all fit on the first screen. The title then scrolls
  // away normally, and only once it is gone does the short copy appear at
  // the top of the sticky details column.
  var big = document.querySelector("[data-rd-big]"), small = document.querySelector("[data-rd-small]");
  var stick = document.querySelector("[data-rd-stick]"), hero = big && big.closest(".rd-hero");
  var askbar = stick && stick.querySelector(".rd-askbar");
  if (!big || !small || !stick || !hero) return;
  var ticking = false;
  var fit = function () {
    big.style.fontSize = "";
    if (innerWidth <= 900) return;
    var max = parseFloat(getComputedStyle(big).fontSize);
    // Leave room under the title for the details and the paper's first lines
    var room = innerHeight - (big.getBoundingClientRect().top + window.scrollY) - 34 - 44 - Math.max(220, innerHeight * 0.27);
    if (big.offsetHeight <= room) return;
    var lo = 40, hi = max;
    for (var k = 0; k < 9; k++) {
      var mid = (lo + hi) / 2;
      big.style.fontSize = mid + "px";
      if (big.offsetHeight <= room) lo = mid; else hi = mid;
    }
    big.style.fontSize = Math.floor(lo) + "px";
  };
  var place = function () {
    // The short title sits just above the details, so the details line up
    // with the paper on the first screen and the title fills in above them
    var last = askbar || small;
    stick.style.setProperty("--rd-sh", innerWidth <= 900 ? "0px" :
      (last.offsetTop + last.offsetHeight + parseFloat(getComputedStyle(last).marginBottom) - small.offsetTop) + "px");
  };
  // Tied to the scroll position, so it moves exactly as fast as the reader
  // scrolls and reverses when they scroll back. The big title fades as its
  // last line rises past the short title's place; the short title and the
  // ask button then rise into it, as a crossfade rather than a jump.
  var still = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  var clamp = function (v) { return v < 0 ? 0 : v > 1 ? 1 : v; };
  var out = function (t) { return 1 - Math.pow(1 - t, 3); };
  var put = function (el, q) {
    if (!el) return;
    var e = out(q);
    el.style.opacity = e.toFixed(3);
    el.style.transform = e >= 1 ? "" : "translateY(" + ((1 - e) * 18).toFixed(2) + "px)";
    el.classList.toggle("is-on", q > .6);
  };
  var paint = function () {
    ticking = false;
    if (innerWidth <= 900) {
      big.style.opacity = ""; small.classList.remove("is-on");
      [small, askbar].forEach(function (el) { if (el) el.style.opacity = el.style.transform = ""; });
      return;
    }
    var bb = big.getBoundingClientRect(), st = small.getBoundingClientRect();
    if (still) {
      var gone = bb.bottom <= st.top + 8;
      small.classList.toggle("is-on", gone); if (askbar) askbar.classList.toggle("is-on", gone);
      return;
    }
    // Measured against where the short title will rest (the column's sticky
    // top), so the first screen is untouched and nothing moves until the
    // reader scrolls. The big title has faded out by the time its last line
    // reaches the short title, which then rises in over the next stretch.
    var rest = (parseFloat(getComputedStyle(stick).top) || 0) + st.height * .3;
    var from = Math.min(bb.bottom + window.scrollY, rest + 320);
    big.style.opacity = (.04 + .96 * clamp((bb.bottom - rest) / Math.max(1, from - rest))).toFixed(3);
    var q = clamp((rest - bb.bottom) / Math.max(120, st.height * .8));
    put(small, q);
    put(askbar, clamp(q * 1.35 - .35));
  };
  var ask = function () { if (!ticking) { ticking = true; requestAnimationFrame(paint); } };
  // The details column never scrolls on its own: if it is taller than the
  // screen, the details table is set a little smaller until it fits
  var details = stick.querySelector(".rd-details");
  var shrink = function () {
    if (!details) return;
    details.style.zoom = "";
    if (innerWidth <= 900) return;
    var room = innerHeight - (parseFloat(getComputedStyle(stick).top) || 0) - 12;
    var other = stick.scrollHeight - details.offsetHeight;
    var z = (room - other) / details.offsetHeight;
    if (z < 1) details.style.zoom = String(Math.max(.78, Math.floor(z * 100) / 100));
  };
  var redo = function () { fit(); place(); shrink(); paint(); };
  redo();
  window.addEventListener("scroll", ask, { passive: true });
  window.addEventListener("resize", redo);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(redo);
})();
