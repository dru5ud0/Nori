(function () {
  "use strict";

  var serverStatus = document.getElementById("server-status");
  var serverDetail = document.getElementById("server-detail");
  var pageStatus = document.getElementById("page-status");
  var pageDetail = document.getElementById("page-detail");
  var summary = document.getElementById("summary");
  var notice = document.getElementById("notice");
  var selectedJob = document.getElementById("selected-job");
  var refreshButton = document.getElementById("refresh-page");
  var activeTab = null;

  function setStatus(node, text, state) {
    node.textContent = text;
    node.className = state || "";
  }

  function fetchJson(url) {
    return fetch(url).then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    });
  }

  function sendToTab(type) {
    return new Promise(function (resolve) {
      if (!activeTab || activeTab.id == null) return resolve(null);
      chrome.tabs.sendMessage(activeTab.id, { type: type }, function (response) {
        if (chrome.runtime.lastError) return resolve(null);
        resolve(response || null);
      });
    });
  }

  function inspectPage(tab) {
    activeTab = tab;
    var url;
    try { url = new URL(tab.url || ""); }
    catch (_) { url = null; }
    var linkedin = Boolean(url && url.hostname.toLowerCase().endsWith("linkedin.com"));
    var jobright = Boolean(url && url.hostname.toLowerCase().endsWith("jobright.ai"));
    var profile = Boolean(linkedin && /^\/in\/[^/]+\/?$/.test(url.pathname));
    var job = Boolean((linkedin && url.pathname.indexOf("/jobs/") === 0) || jobright);

    refreshButton.disabled = !(linkedin || jobright);
    if (!profile && !job) {
      setStatus(pageStatus, "NOT ACTIVE", "warning");
      pageDetail.textContent = linkedin ? "Open a recruiter profile or job" : "Open LinkedIn or JobRight";
      summary.textContent = "The extension is loaded. Open a supported recruiter profile or selected job.";
      return Promise.resolve();
    }

    return sendToTab(profile ? "TSENTA_PROFILE_STATUS" : "TSENTA_PAGE_STATUS").then(function (result) {
      if (!result) {
        setStatus(pageStatus, "REFRESH NEEDED", "warning");
        pageDetail.textContent = "Content script is not injected yet";
        summary.textContent = "The extension is loaded, but this tab needs one normal page refresh.";
        notice.textContent = "Click Refresh current page below. Then reopen this popup.";
        return;
      }
      if (profile) {
        setStatus(pageStatus, result.controlVisible ? "RECRUITER READY" : "PROFILE FOUND", result.controlVisible ? "online" : "warning");
        pageDetail.textContent = (result.profile && result.profile.name) || "LinkedIn profile";
        summary.textContent = result.controlVisible ? "Capture recruiter is visible on this profile." : "Profile detected; waiting for the capture control.";
        return;
      }
      var selected = result.selected;
      if (selected) {
        setStatus(pageStatus, result.overlayVisible ? "JOB READY" : "JOB RESOLVED", "online");
        pageDetail.textContent = selected.company || "External application";
        selectedJob.textContent = selected.title || selected.jobTitle || "Selected job";
        summary.textContent = "The selected job is resolved and ready for explicit local preflight.";
      } else {
        setStatus(pageStatus, "SELECT A JOB", "warning");
        pageDetail.textContent = "No external apply URL resolved yet";
        summary.textContent = "Select a job and open its external Apply flow so Tsenta can resolve it.";
      }
    });
  }

  chrome.runtime.getManifest && (document.getElementById("version").textContent = "v" + chrome.runtime.getManifest().version);

  chrome.storage.local.get(["tsenta_ln_entries"], function (result) {
    document.getElementById("job-count").textContent = String((result.tsenta_ln_entries || []).length);
  });

  Promise.all([
    fetchJson("http://127.0.0.1:8000/api/applications/list/counts"),
    fetchJson("http://127.0.0.1:8000/api/networking/contacts?chicago_only=false")
  ]).then(function (results) {
    setStatus(serverStatus, "ONLINE", "online");
    serverDetail.textContent = String(results[0].all || 0) + " applications · review mode";
    document.getElementById("contact-count").textContent = String(results[1].count || 0);
  }).catch(function () {
    setStatus(serverStatus, "OFFLINE", "offline");
    serverDetail.textContent = "Start TsentaClone on port 8000";
  });

  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    if (!tabs.length) return;
    inspectPage(tabs[0]);
  });

  refreshButton.addEventListener("click", function () {
    if (activeTab && activeTab.id != null) chrome.tabs.reload(activeTab.id);
    window.close();
  });
  document.getElementById("open-control").addEventListener("click", function () {
    chrome.tabs.create({ url: "http://127.0.0.1:8000/" });
  });
  document.getElementById("open-networking").addEventListener("click", function () {
    chrome.tabs.create({ url: "http://127.0.0.1:8000/networking" });
  });
})();
