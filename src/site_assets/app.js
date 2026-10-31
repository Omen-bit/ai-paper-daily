// AI Papers Daily: the only script on the site. No libraries.
(function () {
  "use strict";
  var root = document.documentElement;

  // ---- Theme toggle (the choice is remembered in this browser) ----
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

  // ---- Reading history stays in this browser; later it powers "For you" ----
  var article = document.querySelector("[data-paper-id]");
  if (article) {
    try {
      var reads = JSON.parse(localStorage.getItem("apd.history") || "[]");
      var id = article.getAttribute("data-paper-id");
      reads = reads.filter(function (h) { return h.id !== id; });
      reads.unshift({ id: id, at: Date.now() });
      localStorage.setItem("apd.history", JSON.stringify(reads.slice(0, 500)));
    } catch (e) { /* storage blocked: nothing to remember */ }
  }

  // ---- All papers: search, filter and sort over data/papers.json ----
  var results = document.getElementById("results");
  if (!results) return;

  var PAGE = 50;
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
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

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function shortDate(iso) {
    var p = (iso || "").split("-");
    return p.length === 3 ? MONTHS[Number(p[1]) - 1] + " " + Number(p[2]) : iso;
  }

  // Same markup as paper_row() in site_builder.py
  function row(p) {
    var authors = p.a.join(", ") + (p.n > p.a.length ? " + " + (p.n - p.a.length) + " more" : "");
    var badges = (p.f ? '<span class="badge badge-pick">Top pick</span>' : "") + p.c.map(function (c) {
      return '<a class="badge" href="papers.html?cat=' + esc(c) + '">' + esc(names[c] || c) + "</a>";
    }).join("");
    return '<li class="row"><span class="row-date mono">' + esc(shortDate(p.d)) + "</span>" +
      '<span class="row-title"><a href="paper/' + esc(p.i) + '.html">' + esc(p.t) + "</a></span>" +
      '<span class="row-authors">' + esc(authors) + "</span>" +
      '<div class="badges">' + badges + "</div></li>";
  }

  function render(reset) {
    if (reset) { results.innerHTML = ""; shown = 0; }
    if (!matches.length) {
      results.innerHTML = '<li class="empty">No papers match. Try fewer words or another topic.</li>';
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

  fetch("data/papers.json")
    .then(function (r) { return r.json(); })
    .then(function (data) { all = data; apply(); })
    .catch(function () { count.textContent = "Could not load papers. Try reloading the page."; });
})();
