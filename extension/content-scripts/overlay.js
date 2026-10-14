/**
 * TsentaClone selected-job overlay and explicit local queue.
 *
 * Captures LinkedIn/JobRight discoveries but never creates an application just
 * because a job was viewed. The selected job must pass localhost preflight and
 * the user must click "Prepare locally". The application then enters the local
 * queued/review pipeline; this extension never runs or approves it.
 */
(function () {
  "use strict";

  var BY_JOB_ID = new Map();
  var BY_TITLE = new Map();
  var BY_URL = new Map();
  var totalEntries = 0;
  var focusJobId = "";
  var currentEntry = null;
  var rail = null;
  var preparing = false;

  function normalizeTitle(title) {
    if (!title) return null;
    return String(title).toLowerCase().replace(/[^a-z0-9\s]/g, "").replace(/\s+/g, " ").trim();
  }

  function normalizeUrl(url) {
    try {
      var parsed = new URL(url);
      parsed.hash = "";
      ["trk", "trackingId", "refId", "position", "pageNum"].forEach(function (key) {
        parsed.searchParams.delete(key);
      });
      return parsed.toString().replace(/\/$/, "");
    } catch (_) {
      return "";
    }
  }

  function isExternal(url) {
    try { return Boolean(url) && !new URL(url).hostname.toLowerCase().endsWith("linkedin.com"); }
    catch (_) { return false; }
  }

  function isJobContext() {
    var host = location.hostname.toLowerCase();
    if (host.endsWith("jobright.ai")) return true;
    if (host.endsWith("linkedin.com")) return /^\/jobs(?:\/|$)/.test(location.pathname);
    return false;
  }

  function currentLinkedInJobId() {
    try {
      var url = new URL(location.href);
      var queryId = url.searchParams.get("currentJobId") || url.searchParams.get("jobId");
      if (queryId) return queryId;
      var match = url.pathname.match(/\/jobs\/view\/(\d+)/);
      return match ? match[1] : "";
    } catch (_) { return ""; }
  }

  function selectedFromState() {
    var host = location.hostname.toLowerCase();
    if (host.endsWith("linkedin.com")) {
      var linkedInId = currentLinkedInJobId();
      return linkedInId && BY_JOB_ID.has(String(linkedInId)) ? enrichFromDom(BY_JOB_ID.get(String(linkedInId))) : null;
    }
    var id = focusJobId;
    if (id && BY_JOB_ID.has(String(id))) return BY_JOB_ID.get(String(id));
    return host.endsWith("jobright.ai") ? currentEntry : null;
  }

  function firstText(selectors) {
    for (var i = 0; i < selectors.length; i += 1) {
      var node = document.querySelector(selectors[i]);
      var value = node && String(node.textContent || "").replace(/\s+/g, " ").trim();
      if (value) return value;
    }
    return "";
  }

  function enrichFromDom(entry) {
    if (!entry || !location.hostname.toLowerCase().endsWith("linkedin.com")) return entry;
    var title = firstText([
      ".job-details-jobs-unified-top-card__job-title h1",
      ".job-details-jobs-unified-top-card__job-title",
      ".jobs-unified-top-card__job-title",
      "main h1"
    ]);
    var company = firstText([
      ".job-details-jobs-unified-top-card__company-name a",
      ".job-details-jobs-unified-top-card__company-name",
      ".jobs-unified-top-card__company-name a",
      ".jobs-unified-top-card__company-name"
    ]);
    var locationText = firstText([
      ".job-details-jobs-unified-top-card__primary-description-container",
      ".jobs-unified-top-card__primary-description",
      ".jobs-unified-top-card__bullet"
    ]);
    var enriched = Object.assign({}, entry);
    if (title) enriched.title = title;
    if (company) enriched.company = company;
    if (locationText) enriched.location = locationText;
    var id = String(enriched.jobId || "");
    if (id) BY_JOB_ID.set(id, enriched);
    if (enriched.url) BY_URL.set(enriched.url, enriched);
    currentEntry = enriched;
    return enriched;
  }

  function persist(accepted) {
    if (!accepted.length) return;
    try {
      chrome.storage.local.get(["tsenta_ln_entries"], function (result) {
        var existing = result.tsenta_ln_entries || [];
        var byUrl = new Map();
        existing.concat(accepted).forEach(function (entry) {
          var key = normalizeUrl(entry.url) || String(entry.jobId || normalizeTitle(entry.title) || "");
          if (key) byUrl.set(key, entry);
        });
        var merged = Array.from(byUrl.values()).slice(-500);
        chrome.storage.local.set({ tsenta_ln_entries: merged, tsenta_ln_count: merged.length });
      });
    } catch (_) {}
  }

  function storeEntries(entries) {
    var accepted = [];
    (entries || []).forEach(function (source) {
      var entry = Object.assign({}, source);
      entry.url = normalizeUrl(entry.url || entry.applyLink || entry.originalUrl || "");
      var jobId = String(entry.jobId || "");
      var title = normalizeTitle(entry.title);
      var url = entry.url;
      if (!url) return;

      var previous = (jobId && BY_JOB_ID.get(jobId)) || BY_URL.get(url) || (title && BY_TITLE.get(title));
      if (previous) {
        var enriched = Object.assign({}, previous, entry);
        if (jobId) BY_JOB_ID.set(jobId, enriched);
        if (title) BY_TITLE.set(title, enriched);
        BY_URL.set(url, enriched);
        if (currentEntry === previous || focusJobId === jobId) currentEntry = enriched;
        return;
      }

      if (jobId) BY_JOB_ID.set(jobId, entry);
      if (title) BY_TITLE.set(title, entry);
      BY_URL.set(url, entry);
      accepted.push(entry);
    });

    if (accepted.length) {
      totalEntries += accepted.length;
      persist(accepted);
      var selectedId = focusJobId || currentLinkedInJobId();
      currentEntry = (selectedId && BY_JOB_ID.get(String(selectedId))) || accepted[accepted.length - 1];
      renderRail("captured");
    }
  }

  function shortHost(url) {
    try { return new URL(url).hostname.replace(/^www\./, ""); }
    catch (_) { return "unresolved destination"; }
  }

  function escapeText(value) {
    return String(value || "").replace(/[&<>"']/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
  }

  function ensureRail() {
    if (rail || !isJobContext()) return;
    rail = document.createElement("div");
    rail.id = "tsenta-job-overlay";
    rail.style.cssText = "position:fixed;right:18px;bottom:18px;z-index:2147483646";
    var shadow = rail.attachShadow({ mode: "open" });
    shadow.innerHTML = [
      "<style>",
      ":host{all:initial}.card{width:320px;background:#fffdf6;color:#111;border:2px solid #111;border-radius:8px;padding:14px;font:12px Manrope,system-ui;box-shadow:6px 6px 0 #111}",
      ".top{display:flex;align-items:center;justify-content:space-between}.brand{background:#ffd447;border:1px solid #111;color:#111;font-weight:900;padding:2px 6px}.count{color:#625f58;font:600 10px ui-monospace,monospace}",
      "strong{display:block;margin-top:11px;font-size:14px;line-height:1.35;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.meta{display:block;color:#625f58;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}",
      ".state{margin-top:8px;color:#2864dc;font-size:10px;font-weight:700}.actions{display:flex;gap:7px;margin-top:11px}",
      "button{all:unset;cursor:pointer;border:2px solid #111;border-radius:4px;padding:8px 10px;font-weight:800;text-align:center;box-sizing:border-box}.prepare{flex:1;background:#2864dc;color:white}.prepare:hover{background:#1f51b5}.prepare:disabled{opacity:.45;cursor:not-allowed}.open{background:#e4dfd3;color:#111}",
      "</style><div class='card'><div class='top'><span class='brand'>tsenta local</span><span class='count'></span></div><strong></strong><span class='meta'></span><div class='state'></div><div class='actions'><button class='prepare'>Prepare locally</button><button class='open'>Open</button></div></div>"
    ].join("");
    shadow.querySelector(".prepare").addEventListener("click", prepareSelected);
    shadow.querySelector(".open").addEventListener("click", function () {
      window.open("http://localhost:8000/linkedin", "_blank");
    });
    document.documentElement.appendChild(rail);
  }

  function renderRail(state, detail) {
    var entry = selectedFromState();
    if (!isJobContext() || !entry) {
      if (rail) { rail.remove(); rail = null; }
      return;
    }
    ensureRail();
    if (!rail) return;
    var shadow = rail.shadowRoot;
    var title = entry.title || entry.jobTitle || "Selected job";
    var company = entry.company || "External application";
    var url = entry.url || "";
    shadow.querySelector(".count").textContent = totalEntries + " seen";
    shadow.querySelector("strong").innerHTML = escapeText(title);
    shadow.querySelector(".meta").innerHTML = escapeText(company + (url ? " · " + shortHost(url) : ""));
    shadow.querySelector(".state").textContent = detail || state || "Explicit review required";
    var button = shadow.querySelector(".prepare");
    button.disabled = preparing || Boolean(entry.queued) || !entry || !isExternal(url);
    button.textContent = preparing ? "Checking…" : entry.queued ? "Already queued" : "Prepare locally";
  }

  function firstBlocker(result) {
    var labels = {
      "invalid-url": "Invalid destination URL",
      "linkedin-apply-url-unresolved": "External apply URL is still hidden",
      "unsupported-ats": "Unsupported application system",
      "duplicate-application": "Already queued in Mission Control",
      "profile-incomplete": "Complete your local profile first",
      "test-profile-active": "Replace the demo profile first"
    };
    var blocker = result && result.blockers && result.blockers[0];
    return labels[blocker] || blocker || "Preflight blocked this job";
  }

  function domainFromUrl(value) {
    try { return new URL(value).hostname.replace(/^www\./, ""); }
    catch (_) { return ""; }
  }

  function markQueued(entry) {
    var updated = Object.assign({}, entry, { queued: true });
    var id = String(updated.jobId || "");
    var title = normalizeTitle(updated.title || updated.jobTitle);
    if (id) BY_JOB_ID.set(id, updated);
    if (title) BY_TITLE.set(title, updated);
    if (updated.url) BY_URL.set(updated.url, updated);
    currentEntry = updated;
    return updated;
  }

  function prepareSelected() {
    var entry = selectedFromState();
    if (!entry || preparing || !isExternal(entry.url)) return;
    preparing = true;
    renderRail("checking", "Running local preflight…");
    fetch("http://127.0.0.1:8000/api/preflight?url=" + encodeURIComponent(entry.url))
      .then(function (response) {
        if (!response.ok) throw new Error("preflight-http-" + response.status);
        return response.json();
      })
      .then(function (preflight) {
        if (!preflight.canQueue) {
          if ((preflight.blockers || []).indexOf("duplicate-application") !== -1) {
            entry = markQueued(entry);
            preparing = false;
            renderRail("duplicate", "Already tracked in Mission Control");
            var handled = new Error("already-queued");
            handled.handled = true;
            throw handled;
          }
          throw new Error(firstBlocker(preflight));
        }
        return fetch("http://127.0.0.1:8000/api/applications", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            url: preflight.url,
            company_name: entry.company || "",
            company_domain: domainFromUrl(entry.companyURL || ""),
            logo_url: entry.jdLogo || "",
            job_title: entry.title || entry.jobTitle || ""
          })
        });
      })
      .then(function (response) {
        return response.json().then(function (body) {
          if (!response.ok || !body.ok) throw new Error(body.detail || body.error || "queue-failed");
          return body;
        });
      })
      .then(function (created) {
        preparing = false;
        entry = markQueued(entry);
        renderRail("queued", "Queued for preparation + review");
        rail.shadowRoot.querySelector(".open").onclick = function () {
          window.open("http://localhost:8000/applications/" + encodeURIComponent(created.applicationId), "_blank");
        };
      })
      .catch(function (error) {
        if (error && error.handled) return;
        preparing = false;
        renderRail("blocked", String(error && error.message || error));
      });
  }

  window.addEventListener("message", function (event) {
    if (event.source !== window) return;
    var data = event.data;
    if (!data || data.type !== "TSENTA_LN_RSC_ENTRIES") return;
    storeEntries(data.entries || []);
  });

  window.addEventListener("message", function (event) {
    if (event.source !== window) return;
    var data = event.data;
    if (!data || data.type !== "TSENTA_JOBRIGHT_JOBS") return;
    storeEntries((data.jobs || []).map(function (job) {
      return Object.assign({}, job, {
        url: job.applyLink || job.originalUrl,
        location: job.jobLocation
      });
    }));
  });

  window.addEventListener("message", function (event) {
    if (event.source !== window) return;
    var data = event.data;
    if (!data || data.type !== "TSENTA_JOBRIGHT_FOCUS") return;
    focusJobId = String(data.jobId || "");
    if (BY_JOB_ID.has(focusJobId)) currentEntry = BY_JOB_ID.get(focusJobId);
    renderRail("selected", "Selected job ready for preflight");
  });

  chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
    if (msg.type === "TSENTA_PAGE_STATUS") {
      var selected = selectedFromState();
      sendResponse({
        ok: true,
        jobContext: isJobContext(),
        selected: selected || null,
        overlayVisible: Boolean(rail && rail.isConnected),
        count: totalEntries
      });
      return false;
    }
    if (msg.type === "TSENTA_GET_ENTRIES") {
      chrome.storage.local.get(["tsenta_ln_entries"], function (result) {
        sendResponse({
          entries: result.tsenta_ln_entries || [],
          count: totalEntries,
          selected: selectedFromState() || null,
          jobContext: isJobContext()
        });
      });
      return true;
    }
    if (msg.type === "TSENTA_CLEAR_ENTRIES") {
      BY_JOB_ID.clear(); BY_TITLE.clear(); BY_URL.clear();
      totalEntries = 0; focusJobId = ""; currentEntry = null;
      chrome.storage.local.set({ tsenta_ln_entries: [], tsenta_ln_count: 0 }, function () {
        renderRail("cleared", "Capture history cleared");
        sendResponse({ ok: true });
      });
      return true;
    }
  });

  try {
    chrome.storage.local.get(["tsenta_ln_entries"], function (result) {
      var saved = result.tsenta_ln_entries || [];
      saved.forEach(function (entry) {
        var url = normalizeUrl(entry.url || entry.applyLink || entry.originalUrl || "");
        if (!url) return;
        entry.url = url;
        var id = String(entry.jobId || "");
        var title = normalizeTitle(entry.title);
        if (id) BY_JOB_ID.set(id, entry);
        if (title) BY_TITLE.set(title, entry);
        BY_URL.set(url, entry);
      });
      totalEntries = saved.length;
      var selected = selectedFromState();
      if (selected) currentEntry = selected;
      renderRail("restored", "Selected job restored locally");
    });
  } catch (_) {}

  setInterval(function () {
    if (!isJobContext()) {
      if (rail) { rail.remove(); rail = null; }
      return;
    }
    var id = currentLinkedInJobId();
    if (id && id !== focusJobId && BY_JOB_ID.has(id)) {
      focusJobId = id;
      currentEntry = BY_JOB_ID.get(id);
      renderRail("selected", "Selected job ready for preflight");
    }
  }, 1200);
})();
