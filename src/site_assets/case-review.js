/* case-review.js
   The owner's private review page for suggested write-ups (case-studies/review.html). The page holds
   no data and no secret: it asks supabase/functions/suggest-admin for the rows with the ADMIN_TOKEN
   the owner pastes once (kept in this browser's localStorage), and sends Approve / Reject back.
   Approved write-ups go live with the next daily update (src/case_suggestions.py). */
(function () {
  "use strict";
  var root = document.querySelector("[data-rv]");
  if (!root) return;
  var endpoint = root.getAttribute("data-endpoint");
  var labels = {};
  try { labels = JSON.parse(document.getElementById("rv-labels").textContent); } catch (e) { /* plain names */ }
  var login = root.querySelector("[data-rv-login]");
  var tokenInput = root.querySelector("[data-rv-token]");
  var main = root.querySelector("[data-rv-main]");
  var list = root.querySelector("[data-rv-list]");
  var empty = root.querySelector("[data-rv-empty]");
  var errorEl = root.querySelector("[data-rv-error]");
  var tabs = Array.prototype.slice.call(root.querySelectorAll("[data-rv-tab]"));
  var KEY = "apd.adminToken";
  var rows = [], tab = "waiting";

  function getToken() { try { return localStorage.getItem(KEY) || ""; } catch (e) { return ""; } }
  function setToken(t) { try { if (t) localStorage.setItem(KEY, t); else localStorage.removeItem(KEY); } catch (e) { /* private window */ } }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function host(u) { return String(u || "").split("://").pop().split("/")[0].replace(/^www\./, ""); }
  function ago(iso) {
    var s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (!isFinite(s)) return "";
    if (s < 3600) return Math.max(1, Math.round(s / 60)) + " min ago";
    if (s < 86400) return Math.round(s / 3600) + " h ago";
    var d = Math.round(s / 86400);
    return d === 1 ? "yesterday" : d + " days ago";
  }
  function showError(text) { errorEl.textContent = text; errorEl.hidden = !text; }

  function call(body) {
    body.token = getToken();
    return fetch(endpoint, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (b) { return { status: res.status, body: b }; });
      });
  }

  function group(r) {
    if (r.status === "approved") return "approved";
    if (r.status === "rejected") return "rejected";
    return "waiting";  // new, checked, duplicate
  }

  // The pill and the buttons for one suggestion
  function verdict(r) {
    var c = r.checks || {};
    if (r.status === "duplicate") return { pill: "Already on the site", cls: "rv-grey", actions: [["duplicate", "Close as duplicate", true]] };
    if (r.status === "new") return { pill: "Being checked", cls: "rv-grey", actions: [["reject", "Reject", false]], waiting: true };
    if (r.status === "approved") return { pill: "Approved", cls: "rv-ok", actions: [["reject", "Reject", false]] };
    if (r.status === "rejected") return { pill: "Rejected", cls: "rv-grey", actions: r.title ? [["approve", "Approve anyway", true]] : [] };
    var ready = c.link_works && c.about_ai && c.not_on_site !== false && (r.build_score || 0) >= 3 && !c.announcement;
    if (ready) return { pill: "Ready to approve", cls: "rv-ok", actions: [["reject", "Reject", false], ["approve", "Approve", true]] };
    var why = !c.link_works ? "Link didn’t open" : !c.about_ai ? "Not clearly about AI"
            : c.announcement ? "Reads like an announcement" : "Light on details";
    var canApprove = !!(r.topic && r.title);
    return { pill: why, cls: "rv-warn",
             actions: [["reject", "Reject", false]].concat(canApprove ? [["approve", "Approve anyway", true]] : []) };
  }

  function checksLine(r) {
    var c = r.checks || {};
    if (r.status === "new") return '<p class="rv-checks">Checked automatically with the next daily update.</p>';
    var items = [
      [c.link_works, "Link works", "Link didn’t open"],
      [c.about_ai, "About an AI system", "Doesn’t look like it’s about AI"],
      [c.not_on_site !== false, "Not on the site yet", "Already on the site"],
      [c.has_build_details, "Has build details", "Few build details"]
    ];
    var out = items.map(function (i) {
      return '<span class="' + (i[0] ? "rv-yes" : "rv-no") + '">' + (i[0] ? "✓ " + esc(i[1]) : "⚠ " + esc(i[2])) + "</span>";
    });
    if (c.announcement) out.push('<span class="rv-no">⚠ Reads like a product announcement</span>');
    return '<p class="rv-checks">' + out.join("") + "</p>";
  }

  function chips(r) {
    var out = [];
    if (r.topic) out.push((labels.topics || {})[r.topic] || r.topic);
    (r.techniques || []).forEach(function (t) { out.push(((labels.x || {})[t]) || t); });
    if (r.industry) out.push(((labels.n || {})[r.industry]) || r.industry);
    if (!out.length && r.build_score == null) return "";
    var bd = r.build_score != null ? '<li class="rv-bd ' + (r.build_score >= 4 ? "rv-bd-hi" : r.build_score >= 2 ? "rv-bd-mid" : "rv-bd-lo") +
      '">' + (r.build_score >= 2 ? "✓ " : "") + "Build details " + esc(r.build_score) + "/5</li>" : "";
    return '<p class="rv-label">Filled in automatically</p><ul class="rv-chips">' +
      out.map(function (t) { return "<li>" + esc(t) + "</li>"; }).join("") + bd + "</ul>" +
      (r.problem ? '<p class="rv-ps"><b>Problem</b> ' + esc(r.problem) + "</p>" : "") +
      (r.solution ? '<p class="rv-ps"><b>Solution</b> ' + esc(r.solution) + "</p>" : "");
  }

  var EXT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>';

  function item(r) {
    var v = verdict(r);
    var company = r.company || host(r.url);
    var colour = (labels.brands || {})[company] || "#5D5C63";
    var who = r.credit ? "Suggested by " + esc(r.credit) : "Suggested anonymously";
    var actions = v.actions.map(function (a) {
      return '<button type="button" class="' + (a[2] ? "rv-primary" : "rv-secondary") + '" data-rv-act="' + a[0] + '" data-id="' +
        esc(r.id) + '">' + esc(a[1]) + "</button>";
    }).join("");
    return '<li class="rv-item">' +
      '<div class="rv-head"><span class="rv-logo cs-mono" style="--b:' + esc(colour) + '" aria-hidden="true">' + esc(company.charAt(0).toUpperCase()) + "</span>" +
      '<div class="rv-headtext"><p class="rv-meta"><span class="rv-pill ' + v.cls + '">' + esc(v.pill) + "</span><span>" + who + " · " + esc(ago(r.created_at)) + "</span></p>" +
      "<h3>" + esc(r.title || r.url) + "</h3>" +
      '<a class="rv-domain" href="' + esc(r.url) + '" target="_blank" rel="noopener noreferrer">' + esc(company !== host(r.url) ? company + " · " : "") + esc(host(r.url)) + EXT + "</a></div></div>" +
      (r.note ? '<blockquote class="rv-note">' + esc(r.note) + "</blockquote>" : "") +
      chips(r) + checksLine(r) +
      (actions ? '<div class="rv-actions">' + actions + "</div>" : "") + "</li>";
  }

  function draw() {
    var counts = { waiting: 0, approved: 0, rejected: 0 };
    rows.forEach(function (r) { counts[group(r)]++; });
    Object.keys(counts).forEach(function (k) { root.querySelector('[data-rv-count="' + k + '"]').textContent = counts[k]; });
    tabs.forEach(function (t) { t.setAttribute("aria-selected", t.getAttribute("data-rv-tab") === tab ? "true" : "false"); });
    var these = rows.filter(function (r) { return group(r) === tab; });
    list.innerHTML = these.map(item).join("");
    empty.hidden = these.length > 0;
  }

  function load() {
    showError("");
    call({ action: "list" }).then(function (r) {
      if (r.status === 401) { setToken(""); login.hidden = false; main.hidden = true; showError("That token didn’t work. Paste it again."); return; }
      if (!r.body.ok) { showError(r.body.error || "Couldn’t load the suggestions. Try again in a minute."); return; }
      rows = r.body.rows || [];
      login.hidden = true;
      main.hidden = false;
      draw();
    }).catch(function () { showError("Couldn’t reach the server. Try again in a minute."); });
  }

  login.addEventListener("submit", function (e) {
    e.preventDefault();
    var t = tokenInput.value.trim();
    if (!t) { showError("Paste the admin token to open the review."); return; }
    setToken(t);
    tokenInput.value = "";
    load();
  });
  tabs.forEach(function (t) {
    t.addEventListener("click", function () { tab = t.getAttribute("data-rv-tab"); draw(); });
    t.addEventListener("keydown", function (e) {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      var i = tabs.indexOf(t) + (e.key === "ArrowRight" ? 1 : -1);
      var next = tabs[(i + tabs.length) % tabs.length];
      next.focus(); next.click();
    });
  });
  list.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-rv-act]");
    if (!b) return;
    var id = Number(b.getAttribute("data-id")), decision = b.getAttribute("data-rv-act");
    b.disabled = true;
    call({ action: "review", id: id, decision: decision }).then(function (r) {
      if (!r.body.ok) { b.disabled = false; showError(r.body.error || "Couldn’t save that. Try again."); return; }
      rows.forEach(function (row) { if (row.id === id) row.status = r.body.status; });
      draw();
    }).catch(function () { b.disabled = false; showError("Couldn’t reach the server. Try again in a minute."); });
  });
  root.querySelector("[data-rv-forget]").addEventListener("click", function () {
    setToken(""); rows = []; main.hidden = true; login.hidden = false; tokenInput.focus();
  });

  if (getToken()) load(); else login.hidden = false;
})();
