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
    Array.prototype.forEach.call((scope || document).querySelectorAll(".row[data-id]"), function (row) {
      if (readIds[row.getAttribute("data-id")]) row.classList.add("is-read");
    });
  }
  markRead();

  // ---- Paper page ----
  var article = document.querySelector("[data-paper-id]");
  if (article) {
    var id = article.getAttribute("data-paper-id");
    var title = article.getAttribute("data-title");

    // Remember the visit (powers "Continue reading" now and "For you" later)
    reads = reads.filter(function (h) { return h.id !== id; });
    reads.unshift({ id: id, t: title, at: Date.now() });
    store("apd.history", reads.slice(0, 500));

    // Save for later
    var saveBtn = article.querySelector("[data-save]");
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
    article.querySelector("[data-share]").addEventListener("click", function () {
      var btn = this;
      if (navigator.share) {
        navigator.share({ title: title, url: location.href }).catch(function () {});
      } else if (navigator.clipboard) {
        navigator.clipboard.writeText(location.href).then(function () { confirmLabel(btn, "Link copied"); });
      }
    });

    // Esc closes the open citation box and returns focus to its button
    var cite = article.querySelector(".cite");
    if (cite) {
      document.addEventListener("keydown", function (e) {
        if (e.key !== "Escape" || !cite.open) return;
        cite.open = false;
        cite.querySelector("summary").focus();
      });
    }

    // Copy the BibTeX entry
    var copyBtn = article.querySelector("[data-copy-bibtex]");
    copyBtn.addEventListener("click", function () {
      var text = article.querySelector("[data-bibtex]").textContent;
      if (navigator.clipboard) navigator.clipboard.writeText(text).then(function () { confirmLabel(copyBtn, "Copied"); });
    });

    // Text size, remembered across papers
    var SIZES = [0.9, 1, 1.1, 1.2, 1.32];
    var size = load("apd.textsize", 1);
    var paintSize = function () { article.style.setProperty("--reader-scale", SIZES[size]); };
    paintSize();
    Array.prototype.forEach.call(article.querySelectorAll("[data-size]"), function (b) {
      b.addEventListener("click", function () {
        size = Math.max(0, Math.min(SIZES.length - 1, size + Number(b.getAttribute("data-size"))));
        store("apd.textsize", size);
        paintSize();
      });
    });

    // Reading progress bar
    var bar = document.querySelector("[data-progress]");
    if (bar) {
      var ticking = false;
      var update = function () {
        var rect = article.getBoundingClientRect();
        var total = rect.height - window.innerHeight + 120;
        var done = total > 0 ? Math.min(1, Math.max(0, -rect.top / total)) : 1;
        bar.style.transform = "scaleX(" + done + ")";
        ticking = false;
      };
      window.addEventListener("scroll", function () {
        if (!ticking) { ticking = true; requestAnimationFrame(update); }
      }, { passive: true });
      update();
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
      reads.slice(0, 4).map(function (h) { return storedRow(h, "Opened", false); }).join("");
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

  // ---- All papers: search, filter and sort over data/papers.json ----
  var results = document.getElementById("results");
  if (!results) return;

  var PAGE = 50;
  var q = document.getElementById("q");
  var cat = document.getElementById("cat");
  var sort = document.getElementById("sort");
  var feat = document.getElementById("feat");
  var more = document.getElementById("more");
  var count = document.getElementById("count");
  var all = [], matches = [], shown = 0;

  var params = new URLSearchParams(location.search);
  q.value = params.get("q") || "";
  cat.value = params.get("cat") || "";

  var names = {};
  Array.prototype.forEach.call(cat.options, function (o) { if (o.value) names[o.value] = o.textContent; });

  function shortDate(iso) {
    var p = (iso || "").split("-");
    return p.length === 3 ? MONTHS[Number(p[1]) - 1] + " " + Number(p[2]) : iso;
  }

  // Same markup as paper_row() in site_builder.py
  function row(p) {
    var authors = p.a.join(", ") + (p.n > p.a.length ? " + " + (p.n - p.a.length) + " more" : "");
    var badges = (p.f ? '<span class="badge badge-pick">Top pick</span>' : "") + p.c.map(function (c) {
      return '<a class="badge topic t-' + esc(c) + '" href="papers.html?cat=' + esc(c) + '">' + esc(names[c] || c) + "</a>";
    }).join("");
    return '<li class="row' + (readIds[p.i] ? " is-read" : "") + '" data-id="' + esc(p.i) + '">' +
      '<span class="row-date">' + esc(shortDate(p.d)) + "</span>" +
      '<span class="row-title"><a href="paper/' + esc(p.i) + '.html">' + esc(p.t) + "</a></span>" +
      '<span class="row-authors">' + esc(authors) + "</span>" +
      '<div class="badges">' + badges + "</div></li>";
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
    count.textContent = matches.length === all.length
      ? all.length + " papers"
      : matches.length + " of " + all.length + " papers";
  }

  function apply() {
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
    var u = new URLSearchParams();
    if (q.value) u.set("q", q.value);
    if (cat.value) u.set("cat", cat.value);
    history.replaceState(null, "", u.toString() ? "?" + u : location.pathname);
  }

  var timer;
  q.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(apply, 120); });
  [cat, sort, feat].forEach(function (el) { el.addEventListener("change", apply); });
  more.addEventListener("click", function () { render(false); });
  results.addEventListener("click", function (e) {
    if (!e.target.closest || !e.target.closest("[data-clear]")) return;
    q.value = ""; cat.value = ""; feat.checked = false;
    apply();
    q.focus();
  });

  fetch("data/papers.json")
    .then(function (r) { return r.json(); })
    .then(function (data) { all = data; apply(); })
    .catch(function () {
      results.removeAttribute("aria-busy");
      results.innerHTML = "";
      count.textContent = "We could not load the paper list. Reload the page to try again.";
    });
})();
