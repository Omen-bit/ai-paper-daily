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

  // ---- Reading days and streak (from this browser's history only) ----
  function dayKey(ms) {
    var d = new Date(ms);
    return d.getFullYear() + "-" + (d.getMonth() + 1) + "-" + d.getDate();
  }
  function readDays() {
    var set = {};
    reads.forEach(function (h) { set[dayKey(h.at)] = true; });
    return set;
  }
  function streakLength() {
    var set = readDays(), n = 0, d = new Date();
    if (!set[dayKey(d.getTime())]) d.setDate(d.getDate() - 1);  // today not read yet: count up to yesterday
    while (set[dayKey(d.getTime())]) { n++; d.setDate(d.getDate() - 1); }
    return n;
  }
  function readToday(ids) {
    var today = dayKey(Date.now());
    return ids.filter(function (id) {
      return reads.some(function (h) { return h.id === id && dayKey(h.at) === today; });
    });
  }
  function paintStreak() {
    var el = document.querySelector("[data-streak]");
    if (!el) return;
    var n = streakLength();
    el.textContent = n;
    el.hidden = n < 1;
    el.setAttribute("aria-label", n + "-day reading streak");
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

  // ---- Home: today's reading ring, week strip, read marks, quick save ----
  var daily = document.querySelector("[data-daily]");
  if (daily) {
    var pickIds = (daily.getAttribute("data-picks") || "").split(" ").filter(Boolean);
    var done = readToday(pickIds);
    var total = pickIds.length || 1;
    daily.querySelector("[data-ring]").style.setProperty("--p", Math.round(done.length / total * 100));
    daily.querySelector("[data-ring-n]").textContent = done.length + "/" + pickIds.length;
    var title = daily.querySelector("[data-daily-title]"), sub = daily.querySelector("[data-daily-sub]");
    if (done.length >= pickIds.length && pickIds.length) {
      title.textContent = "You're done for today.";
      sub.textContent = "Both picks read. The next edition arrives tomorrow morning.";
    } else if (done.length) {
      title.textContent = (pickIds.length - done.length) === 1 ? "One pick left." : (pickIds.length - done.length) + " picks left.";
      sub.textContent = "Finish today's edition to keep your streak.";
    }
    // Last 7 days, oldest first; today is outlined until something is read
    var set = readDays(), cells = "";
    for (var i = 6; i >= 0; i--) {
      var d = new Date(); d.setDate(d.getDate() - i);
      var on = set[dayKey(d.getTime())];
      cells += '<i class="' + (on ? "on" : "") + (i === 0 && !on ? " today" : "") + '"></i>';
    }
    var streak = streakLength();
    daily.querySelector("[data-week]").innerHTML = cells + "<em>" + (streak ? streak + "-day streak" : "Read a pick to start a streak") + "</em>";
    Array.prototype.forEach.call(document.querySelectorAll(".pick[data-id]"), function (card) {
      if (done.indexOf(card.getAttribute("data-id")) >= 0 || readIds[card.getAttribute("data-id")]) {
        card.querySelector(".pick-read").hidden = false;
      }
    });
  }
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
        var meta = (date ? date.getDate() + " " + MONTHS[date.getMonth()] : "") +
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
      fetch(forYou.getAttribute("data-url"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: fyIds, limit: 6, days: 30 })
      }).then(function (r) { return r.ok ? r.json() : { results: [] }; })
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
      return fetch(watchBox.getAttribute("data-url"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ q: q, limit: 10, since: since })
      }).then(function (r) { return r.ok ? r.json() : { results: [] }; })
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

    // Remember the visit (powers the streak, Continue reading and, later, For you)
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

    // Focus mode: hides everything but the paper. F toggles, Esc leaves.
    var setFocus = function (on) { document.body.classList.toggle("focus", on); };
    document.querySelector("[data-focus]").addEventListener("click", function () { setFocus(true); });
    document.querySelector("[data-focus-exit]").addEventListener("click", function () { setFocus(false); });
    document.addEventListener("keydown", function (e) {
      var tag = (document.activeElement && document.activeElement.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "Escape") {
        if (cite && cite.open) { cite.open = false; cite.querySelector("summary").focus(); return; }
        setFocus(false);
      } else if (e.key === "f" || e.key === "F") {
        setFocus(!document.body.classList.contains("focus"));
      }
    });

    // Check yourself
    var showAnswer = document.querySelector("[data-check-show]");
    if (showAnswer) {
      showAnswer.addEventListener("click", function () {
        document.querySelector("[data-check-answer]").hidden = false;
        showAnswer.hidden = true;
      });
    }

    // Progress: the bar under the header, the pixel bar, and the section list
    var bar = document.querySelector("[data-progress]");
    var pixels = document.querySelectorAll("[data-pixbar] i");
    var left = document.querySelector("[data-left]");
    var layers = document.querySelectorAll("[data-layer]");
    var tocLinks = {};
    Array.prototype.forEach.call(document.querySelectorAll("[data-toc]"), function (a) { tocLinks[a.getAttribute("data-toc")] = a; });
    var minutes = Number((left && left.textContent.match(/\d+/) || [1])[0]);
    var ticking = false;
    var update = function () {
      var rect = article.getBoundingClientRect();
      var total = rect.height - window.innerHeight + 120;
      var done = total > 0 ? Math.min(1, Math.max(0, -rect.top / total)) : 1;
      if (bar) bar.style.transform = "scaleX(" + done + ")";
      var lit = Math.round(done * pixels.length);
      Array.prototype.forEach.call(pixels, function (p, i) { p.classList.toggle("on", i < lit); });
      if (left) left.textContent = done > 0.97 ? "Finished" : "About " + Math.max(1, Math.ceil(minutes * (1 - done))) + " min left";
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

    // Edition progress at the end of a top pick
    var doneCard = document.querySelector("[data-done]");
    if (doneCard) {
      var ids = (doneCard.getAttribute("data-picks") || "").split(" ").filter(Boolean);
      var got = readToday(ids).length;
      var leftN = ids.length - got;
      doneCard.querySelector("[data-done-title]").textContent = got + " of " + ids.length + " read." + (leftN === 1 ? " One left." : leftN > 1 ? " " + leftN + " left." : "");
      doneCard.querySelector("[data-done-sub]").textContent = leftN ? "Finish this edition to keep your streak going." : "Edition finished. See you tomorrow morning.";
    }

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
  paintStreak();

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
      fetch(ask.getAttribute("data-url"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: askPaper.getAttribute("data-paper-id"), question: question, previous: lastTurn })
      }).then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok, data: d }; });
      }).then(function (res) {
        clearTimeout(slow);
        var box = turn.querySelector(".ask-a");
        box.classList.remove("is-loading");
        if (!res.ok) {
          box.classList.add("is-error");
          box.textContent = res.data.error || "Couldn't answer that right now.";
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
        box.textContent = "Couldn't reach the server. Check your connection and try again.";
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
    var STAGE_NAMES = { start: "Start here", core: "Build on", further: "Later" };
    var STAGE_NOTES = { start: "The simplest approach that works", core: "The methods to build on", further: "Optional, once the basics work" };
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

    var FIT_NAMES = { direct: "Direct fit", partial: "Partial fit" };
    var STATUS = { covered: ["✓", "Covered"], partly: ["~", "Partly covered"], missing: ["✕", "No paper found"] };
    var VERDICT = {
      good: ["Good match", "Our papers cover every part of this project."],
      partial: ["Partly covered", "Some parts have papers that fit. The rest you’d build without one, or with a broader search."],
      none: ["No good papers yet", "Nothing in our database really fits this project, so Scout isn’t showing any. That’s an honest answer, not an error."]
    };
    var pad2 = function (n) { return String(n).padStart(2, "0"); };
    var paperHref = function (p, onSite) {
      return onSite[p.id] ? "paper/" + esc(p.id) + ".html" : "https://huggingface.co/papers/" + esc(p.id);
    };

    // One row of the reading-order panel. Which needs a paper serves is shown as
    // Harvey balls (full: direct fit, half: partial fit, empty: not this paper).
    var ballsFor = function (p, needs) {
      return needs.map(function (nd) {
        var serves = (p.needs || []).indexOf(nd.id) >= 0;
        var kind = !serves ? "none" : p.fit === "direct" ? "full" : "half";
        var words = !serves ? "not covered by this paper" : p.fit === "direct" ? "direct fit" : "partial fit";
        return '<li class="syl-ball"><span class="hb hb-' + kind + '" aria-hidden="true"></span>' +
          '<span class="syl-ball-label">' + esc(nd.label) + '</span><span class="sr-only">: ' + words + "</span></li>";
      }).join("");
    };
    var planRow = function (p, n, onSite, needs) {
      var local = onSite[p.id];
      var isSaved = saved.some(function (s) { return s.id === p.id; });
      var links = (p.code_url ? '<a class="text-link" href="' + esc(p.code_url) + '" rel="noopener">Get the code</a>' : "") +
        (local ? "" : '<span class="syl-ext">On Hugging Face</span>');
      return '<li class="syl-row" id="sp-' + pad2(n) + '" data-id="' + esc(p.id) + '">' +
        '<span class="syl-n" aria-hidden="true">' + n + "</span>" +
        '<div class="syl-paper"><a class="syl-title" href="' + paperHref(p, onSite) + '"' + (local ? "" : ' rel="noopener"') + ">" +
        '<span class="sr-only">Paper ' + n + ": </span>" + esc(p.title) + "</a>" +
        (p.reason ? '<p class="syl-reason">' + esc(p.reason) + "</p>" : "") +
        (links ? '<div class="syl-links">' + links + "</div>" : "") + "</div>" +
        (needs.length ? '<ul class="syl-needs" aria-label="What it covers">' + ballsFor(p, needs) + "</ul>" : "") +
        '<button class="quick-save" type="button" data-quick-save="' + esc(p.id) + '" data-title="' + esc(p.title) + '" aria-pressed="' + isSaved +
        '" aria-label="Save for later">' + (isSaved ? "✓" : "+") + "</button></li>";
    };

    var chipsFor = function (ids, numberOf) {
      return ids.filter(function (id) { return numberOf[id]; }).map(function (id) {
        return '<a class="pchip" href="#sp-' + pad2(numberOf[id]) + '" aria-label="Paper ' + numberOf[id] + '">' + numberOf[id] + "</a>";
      }).join("");
    };

    var tryChips = function (list) {
      if (!list || !list.length) return "";
      return '<div class="try"><span class="label">Try searching for</span>' + list.map(function (t) {
        return '<a class="qchip" href="papers.html?q=' + encodeURIComponent(t) + '&amp;m=1">' + esc(t) + "</a>";
      }).join("") + "</div>";
    };

    var verdictCard = function (data, description, at, cov) {
      var v = VERDICT[data.verdict];
      var counts = { covered: 0, partly: 0, missing: 0 };
      cov.forEach(function (c) { counts[c.status] = (counts[c.status] || 0) + 1; });
      var meter = cov.length ? '<div class="cov-meter" role="img" aria-label="' + counts.covered + " of " + cov.length + ' needs covered">' +
        cov.map(function (c) { return '<i class="s-' + esc(c.status) + '" title="' + esc(c.label) + ": " + STATUS[c.status][1] + '"></i>'; }).join("") + "</div>" +
        '<p class="cov-count"><b>' + counts.covered + " of " + cov.length + "</b> needs covered" +
        (counts.partly ? " · " + counts.partly + " partly" : "") + (counts.missing ? " · " + counts.missing + " with no paper" : "") + "</p>" : "";
      return '<div class="card pad scout-verdict' + (v ? " v-" + esc(data.verdict) : "") + '">' +
        '<div class="verdict-top"><span class="label">' + (at ? "Your last Scout, " + ago(at) : "Your project") + "</span>" +
        (v ? '<span class="verdict-pill">' + v[0] + "</span>" : "") + "</div>" +
        '<p class="verdict-summary">' + esc(data.summary || description) + "</p>" + meter +
        (v ? '<p class="verdict-note">' + v[1] + "</p>" : "") +
        (data.mode === "basic" && (data.plan || []).length ? '<p class="fine">The planner was unavailable, so these are the closest papers by meaning and haven’t been checked for fit.</p>' : "") +
        '<div class="scout-actions">' +
        ((data.plan || []).length ? '<button class="btn btn-primary btn-sm" type="button" data-scout-watch aria-pressed="false">Watch this project</button>' +
          '<button class="btn btn-outline btn-sm" type="button" data-scout-copy><span>Copy as Markdown</span></button>' : "") +
        '<button class="btn btn-outline btn-sm" type="button" data-scout-new>Start over</button></div></div>';
    };

    var coverageSection = function (cov, numberOf, plan, tries) {
      if (!cov.length) return "";
      var rows = cov.map(function (c) {
        var ids = plan.filter(function (p) { return (p.needs || []).indexOf(c.need) >= 0; }).map(function (p) { return p.id; });
        var s = STATUS[c.status] || STATUS.missing;
        return '<li class="cov s-' + esc(c.status) + '"><span class="cov-icon" aria-hidden="true">' + s[0] + "</span>" +
          '<div class="cov-body"><div class="cov-head"><b>' + esc(c.label) + '</b><span class="cov-status">' + s[1] + "</span></div>" +
          (c.note ? "<p>" + esc(c.note) + "</p>" : "") + "</div>" +
          '<span class="cov-papers">' + chipsFor(ids, numberOf) + "</span></li>";
      }).join("");
      return '<section class="scout-sec"><div class="sec-head"><h2>What your project needs</h2><span>Each part of your project, and whether a paper covers it</span></div>' +
        '<ul class="card cov-list">' + rows + "</ul>" + tryChips(tries) + "</section>";
    };

    var buildSection = function (steps, numberOf) {
      if (!steps || !steps.length) return "";
      return '<section class="scout-sec"><div class="sec-head"><h2>How to build it</h2><span>Steps in order, with the papers for each</span></div><ol class="build">' +
        steps.map(function (st, i) {
          var chips = chipsFor(st.papers || [], numberOf);
          return '<li class="build-step' + (chips ? "" : " no-paper") + '"><span class="build-n">' + (i + 1) + "</span>" +
            '<div class="build-body"><b>' + esc(st.title) + "</b><p>" + esc(st.detail) + "</p>" +
            '<div class="build-papers">' + (chips ? "<span>Papers</span>" + chips : "<span>No paper: you build this part yourself</span>") + "</div></div></li>";
        }).join("") + "</ol></section>";
    };

    var compareSection = function (plan, numberOf, needNames) {
      var useful = plan.filter(function (p) { return p.approach || p.result || p.requires || p.best_for; });
      if (plan.length < 2 || !useful.length) return "";
      var cell = function (label, text) { return '<td data-label="' + label + '">' + (text ? esc(text) : '<span class="muted">Not stated</span>') + "</td>"; };
      return '<section class="scout-sec"><div class="sec-head"><h2>Compare at a glance</h2><span>From the abstracts, and the full paper where we have it</span></div>' +
        '<div class="card compare-wrap"><table class="compare"><thead><tr><th scope="col">Paper</th><th scope="col">Approach</th><th scope="col">What it needs</th>' +
        '<th scope="col">Key result</th><th scope="col">Best for</th><th scope="col">Code</th></tr></thead><tbody>' +
        plan.map(function (p) {
          return '<tr><th scope="row"><a class="pchip" href="#sp-' + pad2(numberOf[p.id]) + '">' + numberOf[p.id] + "</a>" +
            '<span class="compare-title">' + esc(p.title) + "</span>" +
            (p.fit ? '<span class="syl-fit"><i class="hb hb-' + (p.fit === "direct" ? "full" : "half") + '" aria-hidden="true"></i>' + FIT_NAMES[p.fit] + "</span>" : "") + "</th>" +
            cell("Approach", p.approach) + cell("What it needs", p.requires) + cell("Key result", p.result) + cell("Best for", p.best_for) +
            '<td data-label="Code">' + (p.code_url ? '<a href="' + esc(p.code_url) + '" rel="noopener">Repo ↗</a>' : '<span class="muted">None yet</span>') + "</td></tr>";
        }).join("") + "</tbody></table></div></section>";
    };

    var extrasSection = function (data) {
      var need = (data.you_need || []).map(function (t) { return '<li>' + esc(t) + "</li>"; }).join("");
      var watch = (data.watch_out || []).map(function (t) { return "<li>" + esc(t) + "</li>"; }).join("");
      if (!need && !watch) return "";
      return '<section class="scout-extras">' +
        (need ? '<div class="card pad"><span class="label">You’ll need</span><ul class="need-list">' + need + "</ul></div>" : "") +
        (watch ? '<div class="card pad watch-out"><span class="label">Watch out for</span><ul>' + watch + "</ul></div>" : "") + "</section>";
    };

    var asMarkdown = function (data, description) {
      var plan = data.plan || [], lines = ["# " + (data.summary || description), ""];
      var v = VERDICT[data.verdict];
      if (v) lines.push("**" + v[0] + ".** " + v[1], "");
      if ((data.coverage || []).length) {
        lines.push("## What the project needs");
        data.coverage.forEach(function (c) { lines.push("- " + (STATUS[c.status] || STATUS.missing)[0] + " **" + c.label + "**" + (c.note ? ": " + c.note : "")); });
        lines.push("");
      }
      if ((data.steps || []).length) {
        lines.push("## How to build it");
        data.steps.forEach(function (st, i) { lines.push((i + 1) + ". **" + st.title + "**: " + st.detail); });
        lines.push("");
      }
      lines.push("## Papers");
      plan.forEach(function (p, i) {
        lines.push((i + 1) + ". [" + p.title + "](https://arxiv.org/abs/" + p.id + ")" + (p.fit ? " (" + FIT_NAMES[p.fit] + ")" : "") +
          (p.reason ? "\n   " + p.reason : "") + (p.code_url ? "\n   Code: " + p.code_url : ""));
      });
      if ((data.you_need || []).length) lines.push("", "## You’ll need", data.you_need.map(function (t) { return "- " + t; }).join("\n"));
      if ((data.watch_out || []).length) lines.push("", "## Watch out for", data.watch_out.map(function (t) { return "- " + t; }).join("\n"));
      lines.push("", "Made with Project Scout, AI Papers Daily");
      return lines.join("\n");
    };

    var paintPlan = function (data, description, at) {
      siteIds().then(function (onSite) {
        var plan = data.plan || [];
        // Plans saved before Scout rated papers have no verdict or coverage
        if (!data.version) data = Object.assign({}, data, { verdict: plan.length ? null : "none", coverage: [] });
        var cov = data.coverage || [];
        var needNames = {}, numberOf = {};
        (data.needs || []).forEach(function (n) { needNames[n.id] = n.label; });
        plan.forEach(function (p, i) { numberOf[p.id] = i + 1; });

        // Number papers in the order they're shown
        var n = 0;
        ["start", "core", "further"].forEach(function (stage) {
          plan.forEach(function (p) { if (p.stage === stage) numberOf[p.id] = ++n; });
        });
        var needs = (data.needs || []).filter(function (nd) { return nd.label; });
        var groups = "";
        ["start", "core", "further"].forEach(function (stage) {
          var items = plan.filter(function (p) { return p.stage === stage; });
          if (!items.length) return;
          groups += '<section class="syl-stage stage-' + stage + '"><h3 class="syl-stage-name">' + STAGE_NAMES[stage] +
            "<small>" + STAGE_NOTES[stage] + "</small></h3>" +
            '<ol class="syl-list">' + items.map(function (p) { return planRow(p, numberOf[p.id], onSite, needs); }).join("") + "</ol></section>";
        });
        var head = needs.length ? '<div class="syl-head" aria-hidden="true"><span>Read in this order</span><ul class="syl-needs">' +
          needs.map(function (nd) { return "<li>" + esc(nd.label) + "</li>"; }).join("") + "</ul><span></span></div>" : "";
        var key = needs.length ? '<p class="syl-key"><span><i class="hb hb-full"></i>Direct fit</span><span><i class="hb hb-half"></i>Partial fit</span>' +
          '<span><i class="hb hb-none"></i>Not covered by this paper</span></p>' : "";
        var papersSection = plan.length ? '<section class="scout-sec"><div class="sec-head"><h2>The papers</h2><span>' + plan.length +
          (plan.length === 1 ? " paper fits" : " papers fit") + ", and the needs each one covers</span></div>" +
          '<div class="card syllabus" style="--n-needs:' + needs.length + '">' + head + groups + key + "</div></section>" : "";
        var noneHelp = data.verdict === "none" && !cov.length ? '<div class="card pad empty-card"><p>Try naming the task and the data, for example “summarise legal contracts” instead of “legal AI app”.</p>' + tryChips(data.try) + "</div>" : "";

        out.innerHTML = verdictCard(data, description, at, cov) +
          coverageSection(cov, numberOf, plan, data.verdict === "good" ? [] : data.try) +
          buildSection(data.steps, numberOf) +
          papersSection +
          compareSection(plan.slice().sort(function (a, b) { return numberOf[a.id] - numberOf[b.id]; }), numberOf, needNames) +
          extrasSection(data) + noneHelp +
          '<div class="feedback" data-feedback="scout"><span data-feedback-q>Was this useful?</span>' +
          '<button class="btn btn-outline btn-sm" type="button" data-vote="useful">Yes, useful</button>' +
          '<button class="btn btn-outline btn-sm" type="button" data-vote="not_useful">Not really</button></div>';
        wireFeedback(out.querySelector("[data-feedback]"));
        out.querySelector("[data-scout-new]").addEventListener("click", function () {
          try { localStorage.removeItem("apd.scout"); } catch (e) { /* private mode */ }
          out.innerHTML = introHtml; desc.value = ""; paintCount(); desc.focus();
        });
        var copyBtn = out.querySelector("[data-scout-copy]");
        if (copyBtn) copyBtn.addEventListener("click", function () {
          if (navigator.clipboard) navigator.clipboard.writeText(asMarkdown(data, description)).then(function () { confirmLabel(copyBtn, "Copied"); });
        });
        var watchBtn = out.querySelector("[data-scout-watch]");
        if (watchBtn && window.apdWatch) window.apdWatch.wire(watchBtn, data, description);
        markRead(out);
      });
    };

    var scoutNames = {};
    try { scoutNames = JSON.parse(scoutForm.getAttribute("data-names")) || {}; } catch (e) { /* slugs */ }

    var LOADING = ["Reading your description…", "Searching papers from a few angles…", "Putting them in order…"];
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
      fetch(scoutForm.getAttribute("data-url"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description: text })
      }).then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok, status: r.status, data: d }; });
      }).then(function (res) {
        clearInterval(timer);
        if (!res.ok) {
          if (res.status === 400 || /code|characters/.test(res.data.error || "")) showProblem(res.data.error || "");
          out.innerHTML = '<div class="card pad empty-card"><span class="label">Couldn’t make a plan</span><p>' +
            esc(res.data.error || "Scout is unavailable right now. Try again in a minute.") + "</p></div>";
          return;
        }
        store("apd.scout", { description: text, data: res.data, at: Date.now() });
        paintPlan(res.data, text, 0);
        out.scrollIntoView({ behavior: "smooth", block: "start" });
      }).catch(function () {
        clearInterval(timer);
        out.innerHTML = '<div class="card pad empty-card"><span class="label">Couldn’t reach Scout</span><p>Check your connection and try again.</p></div>';
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

  // ---- All papers: search, filter and sort over data/papers.json ----
  var results = document.getElementById("results");
  if (!results) return;

  var PAGE = 50;
  var q = document.getElementById("q");
  var cat = document.getElementById("cat");
  var sort = document.getElementById("sort");
  var feat = document.getElementById("feat");
  var meaning = document.getElementById("meaning");
  var SEARCH_URL = results.getAttribute("data-search-url");
  var onSite = {};          // ids that have a page on this site
  var searchToken = 0;      // drops answers to searches the visitor has already replaced
  var more = document.getElementById("more");
  var count = document.getElementById("count");
  var all = [], matches = [], shown = 0;

  var params = new URLSearchParams(location.search);
  q.value = params.get("q") || "";
  cat.value = params.get("cat") || "";
  meaning.checked = params.get("m") === "1";

  var names = {};
  Array.prototype.forEach.call(cat.options, function (o) { if (o.value) names[o.value] = o.textContent; });

  // "Oct 31", or "4 Mar 2025" for another year
  var thisYear = String(new Date().getFullYear());
  function shortDate(iso) {
    var p = (iso || "").split("-");
    if (p.length !== 3) return iso;
    return p[0] === thisYear ? MONTHS[Number(p[1]) - 1] + " " + Number(p[2])
                             : Number(p[2]) + " " + MONTHS[Number(p[1]) - 1] + " " + p[0];
  }

  // Same markup as paper_row() in site_builder.py. Papers from the search
  // archive have no page here, so they link to Hugging Face instead.
  function row(p) {
    var local = onSite[p.i];
    var href = local ? "paper/" + esc(p.i) + ".html" : "https://huggingface.co/papers/" + esc(p.i);
    var authors = p.a.join(", ") + (p.n > p.a.length ? " + " + (p.n - p.a.length) + " more" : "");
    var badges = (p.f === 2 ? '<span class="badge badge-hot">Trending</span>' : p.f ? '<span class="badge badge-pick">Top pick</span>' : "") + p.c.map(function (c) {
      return '<a class="badge topic t-' + esc(c) + '" href="papers.html?cat=' + esc(c) + '">' + esc(names[c] || c) + "</a>";
    }).join("");
    return '<li class="row' + (readIds[p.i] ? " is-read" : "") + '" data-id="' + esc(p.i) + '">' +
      '<span class="row-date">' + esc(shortDate(p.d)) + "</span>" +
      '<span class="row-title"><a href="' + href + '"' + (local ? "" : ' rel="noopener"') + ">" + esc(p.t) + "</a></span>" +
      '<span class="row-authors">' + esc(authors) + (local ? "" : '<span class="sep"></span><span class="ext">Hugging Face ↗</span>') + "</span>" +
      '<div class="badges">' + badges + "</div></li>";
  }

  // A search function result in the short form row() expects
  function fromSearch(r) {
    var authors = r.authors || [];
    return { i: r.id, t: r.title, a: authors.slice(0, 3), n: authors.length,
             c: (r.categories && r.categories.length) ? r.categories : ["other-ml"],
             d: String(r.submitted || r.first_seen || "").slice(0, 10), s: 0, f: r.featured ? 1 : 0 };
  }

  function render(reset) {
    if (reset) { results.innerHTML = ""; shown = 0; }
    results.removeAttribute("aria-busy");
    if (!matches.length) {
      results.innerHTML = '<li class="empty"><strong>No papers match these filters.</strong>Try fewer words, or show every topic.' +
        '<div class="empty-action"><button class="btn btn-outline btn-sm" type="button" data-clear>Clear all filters</button></div></li>';
    } else {
      results.insertAdjacentHTML("beforeend", matches.slice(shown, shown + PAGE).map(row).join(""));
    }
    shown = Math.min(shown + PAGE, matches.length);
    more.hidden = shown >= matches.length;
    if (meaning.checked && q.value.trim().length >= 3) {
      count.textContent = matches.length + " papers closest in meaning, best match first";
    } else {
      count.textContent = matches.length === all.length
        ? all.length + " papers"
        : matches.length + " of " + all.length + " papers";
    }
  }

  function keepFiltered(list) {
    return list.filter(function (p) {
      if (cat.value && p.c.indexOf(cat.value) < 0) return false;
      if (feat.checked && !p.f) return false;
      return true;
    });
  }

  function searchByMeaning() {
    var token = ++searchToken;
    results.setAttribute("aria-busy", "true");
    results.innerHTML = new Array(6).join('<li class="row skeleton" aria-hidden="true"><span></span><span></span></li>');
    count.textContent = "Searching by meaning…";
    fetch(SEARCH_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ q: q.value.trim(), limit: 50 })
    })
      .then(function (r) { return r.json().then(function (body) { return { ok: r.ok, body: body }; }); })
      .then(function (res) {
        if (token !== searchToken) return;
        if (!res.ok) throw new Error(res.body.error || "Search failed");
        matches = keepFiltered(res.body.results.map(fromSearch));
        render(true);
      })
      .catch(function (err) {
        if (token !== searchToken) return;
        meaning.checked = false;
        apply();
        count.textContent = (err.message || "Search by meaning is unavailable right now.") + " Showing word matches instead.";
      });
  }

  function apply() {
    sort.disabled = meaning.checked;
    if (meaning.checked && q.value.trim().length >= 3) {
      searchByMeaning();
      syncUrl();
      return;
    }
    searchToken++;  // a word search replaces any meaning search still in flight
    var words = q.value.toLowerCase().split(/\s+/).filter(Boolean);
    matches = all.filter(function (p) {
      if (cat.value && p.c.indexOf(cat.value) < 0) return false;
      if (feat.checked && !p.f) return false;
      if (!words.length) return true;
      var hay = (p.t + " " + p.a.join(" ")).toLowerCase();
      return words.every(function (w) { return hay.indexOf(w) >= 0; });
    });
    if (sort.value === "score") matches.sort(function (a, b) { return b.s - a.s; });
    render(true);
    syncUrl();
  }

  function syncUrl() {
    var u = new URLSearchParams();
    if (q.value) u.set("q", q.value);
    if (cat.value) u.set("cat", cat.value);
    if (meaning.checked) u.set("m", "1");
    history.replaceState(null, "", u.toString() ? "?" + u : location.pathname);
  }

  var timer;
  q.addEventListener("input", function () {
    clearTimeout(timer);
    timer = setTimeout(apply, meaning.checked ? 450 : 120);  // wait for a pause before asking the server
  });
  [cat, sort, feat, meaning].forEach(function (el) { el.addEventListener("change", apply); });
  more.addEventListener("click", function () { render(false); });
  results.addEventListener("click", function (e) {
    if (!e.target.closest || !e.target.closest("[data-clear]")) return;
    q.value = ""; cat.value = ""; feat.checked = false; meaning.checked = false;
    apply();
    q.focus();
  });

  fetch("data/papers.json")
    .then(function (r) { return r.json(); })
    .then(function (data) {
      all = data;
      all.forEach(function (p) { if (!p.x) onSite[p.i] = true; });
      apply();
    })
    .catch(function () {
      results.removeAttribute("aria-busy");
      results.innerHTML = "";
      count.textContent = "We could not load the paper list. Reload the page to try again.";
    });
})();
