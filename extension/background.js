/**
 * Tsenta Clone — Extension background service worker.
 *
 * Bridges the CLI to the content-script overlay store.
 * The CLI can connect via chrome.runtime.connectNative or
 * chrome.runtime.sendMessage with type "TSENTA_GET_ENTRIES" /
 * "TSENTA_CLEAR_ENTRIES" to query and reset the harvested entries.
 */

function updateBadge(tabId, url) {
  var value = String(url || "");
  var text = "ON";
  var color = "#625f58";
  try {
    var parsed = new URL(value);
    var linkedIn = parsed.hostname.toLowerCase().endsWith("linkedin.com");
    var jobRight = parsed.hostname.toLowerCase().endsWith("jobright.ai");
    if (linkedIn && /^\/in\/[^/]+\/?$/.test(parsed.pathname)) {
      text = "CRM";
      color = "#d99a00";
    } else if ((linkedIn && parsed.pathname.indexOf("/jobs/") === 0) || jobRight) {
      text = "JOB";
      color = "#2864dc";
    }
  } catch (_) {}
  chrome.action.setBadgeBackgroundColor({ tabId: tabId, color: color });
  chrome.action.setBadgeText({ tabId: tabId, text: text });
}

chrome.runtime.onInstalled.addListener(function () {
  chrome.action.setBadgeBackgroundColor({ color: "#625f58" });
  chrome.action.setBadgeText({ text: "ON" });
});

chrome.runtime.onStartup.addListener(function () {
  chrome.action.setBadgeBackgroundColor({ color: "#625f58" });
  chrome.action.setBadgeText({ text: "ON" });
});

chrome.tabs.onUpdated.addListener(function (tabId, changeInfo, tab) {
  if (changeInfo.url || changeInfo.status === "complete") updateBadge(tabId, changeInfo.url || tab.url);
});

chrome.tabs.onActivated.addListener(function (activeInfo) {
  chrome.tabs.get(activeInfo.tabId, function (tab) {
    if (!chrome.runtime.lastError) updateBadge(activeInfo.tabId, tab.url);
  });
});

chrome.runtime.onMessageExternal.addListener(function (msg, sender, sendResponse) {
  if (msg.type === "TSENTA_GET_ENTRIES") {
    chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
      if (!tabs.length) {
        sendResponse({ error: "no-active-tab" });
        return;
      }
      chrome.tabs.sendMessage(tabs[0].id, { type: "TSENTA_GET_ENTRIES" }, function (response) {
        sendResponse(response || { entries: [], count: 0 });
      });
    });
    return true;
  }
  if (msg.type === "TSENTA_CLEAR_ENTRIES") {
    chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
      if (!tabs.length) {
        sendResponse({ error: "no-active-tab" });
        return;
      }
      chrome.tabs.sendMessage(tabs[0].id, { type: "TSENTA_CLEAR_ENTRIES" }, function (response) {
        sendResponse(response || { ok: false });
      });
    });
    return true;
  }
});
