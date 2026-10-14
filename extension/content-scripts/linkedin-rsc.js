/**
 * Tsenta Clone — LinkedIn RSC Flight Harvester
 *
 * Ported verbatim from the recovered Tsenta extension (linkedin-rsc.js).
 * Injected at document_start, world MAIN — hooks fetch + XMLHttpRequest
 * to scan every response body for safety/go URLs in the RSC flight data.
 *
 * Algorithm:
 * 1. Hook fetch + XHR — intercept every response body
 * 2. Unescape up to 3 passes (\\u0026 -> &, \\/ -> /, \\\" -> ")
 * 3. Extract JobCardFrameworkImpl*State_<id> markers (job IDs)
 * 4. Extract safety/go/?url=... markers, decode via URL searchParams
 * 5. Discard internal linkedin.com targets
 * 6. Pair each URL with nearest preceding job ID marker
 * 7. Extract title from "text":"..." strings (heuristic filter)
 * 8. Ship via window.postMessage({type:"TSENTA_LN_RSC_ENTRIES", entries})
 */

(function () {
  "use strict";

  function decodeSafetyGo(url) {
    try {
      var parsed = new URL(url);
      if (
        parsed.hostname.toLowerCase().endsWith("linkedin.com") &&
        parsed.pathname.startsWith("/safety/go")
      ) {
        var target = parsed.searchParams.get("url");
        if (target) return target;
      }
      return url;
    } catch (_) {
      return url;
    }
  }

  function looksLikeTitle(text) {
    var title = text.replace(/\s+/g, " ").trim();
    if (title.length < 8 || title.length > 150 || !title.includes(" ")) return false;
    if (/^(viewed|saved|easy apply|posted|promoted|be an early|company alumni|featured|new$)/i.test(title))
      return false;
    if (/^\$/.test(title)) return false;
    if (/^\d+\s+(days?|hours?|weeks?|months?|year|min)/i.test(title)) return false;
    if (title.includes("proto.sdui") || title.includes("JobCardFramework")) return false;
    if (/^[\w$]+\.[\w$]+(\.[\w$]+)+/.test(title)) return false;
    return true;
  }

  function setDataAttr(key, val) {
    try {
      document.documentElement.setAttribute("data-tsenta-" + key, val);
    } catch (_) {}
  }

  var rscFound = 0;
  var rscPosted = 0;

  setDataAttr("fetch-hooked", "1");

  function scanBody(url, bodyText) {
    if (!bodyText || bodyText.length < 50) return;
    if (bodyText.indexOf("safety/go") === -1) return;

    rscFound++;
    setDataAttr("rsc-found", String(rscFound));

    var entries = parseFlight(bodyText);
    if (entries.length === 0) return;

    rscPosted += entries.length;
    setDataAttr("rsc-posted", String(rscPosted));

    window.postMessage(
      { type: "TSENTA_LN_RSC_ENTRIES", entries: entries, url: url },
      window.location.origin
    );
  }

  function parseFlight(raw) {
    if (!raw || raw.length < 100) return [];
    if (raw.indexOf("safety/go") === -1) return [];

    var text = raw;
    for (var i = 0; i < 3; i++) {
      var repaired = text
        .replace(/\\u0026/g, "&")
        .replace(/\\u0025/g, "%")
        .replace(/\\\//g, "/")
        .replace(/\\"/g, '"');
      if (repaired === text) break;
      text = repaired;
    }

    var markers = [];
    var markerRe = /JobCardFrameworkImpl(?:Footer|Saved|Tracking|Logo|Insights|Top)?State_(\d+)/g;
    var markerMatch;
    while ((markerMatch = markerRe.exec(text)) !== null) {
      markers.push({ pos: markerMatch.index, id: markerMatch[1] });
    }

    var entries = [];
    var urlRe = /https:\/\/www\.linkedin\.com\/safety\/go\/\?url=[^"\\\s]+/g;
    var urlMatch;
    while ((urlMatch = urlRe.exec(text)) !== null) {
      var rawUrl = urlMatch[0];
      var decoded = decodeSafetyGo(rawUrl);
      if (!decoded || decoded === rawUrl) continue;
      try {
        if (new URL(decoded).hostname.toLowerCase().endsWith("linkedin.com")) continue;
      } catch (_) {
        continue;
      }

      var bestPos = -1;
      var bestId = null;
      for (var j = 0; j < markers.length; j++) {
        if (markers[j].pos < urlMatch.index && markers[j].pos > bestPos) {
          bestPos = markers[j].pos;
          bestId = markers[j].id;
        }
      }

      var windowStart = bestPos >= 0 ? bestPos : Math.max(0, urlMatch.index - 5000);
      var title = null;
      var titleRe = /"text":"([^"\\]{5,200})"/g;
      var titleChunk = text.slice(windowStart, urlMatch.index);
      var titleMatches = [];
      var titleMatch;
      while ((titleMatch = titleRe.exec(titleChunk)) !== null) {
        titleMatches.push(titleMatch[1]);
      }
      for (var k = titleMatches.length - 1; k >= 0; k--) {
        if (looksLikeTitle(titleMatches[k])) {
          title = titleMatches[k].replace(/\s+/g, " ").trim();
          break;
        }
      }

      entries.push({ jobId: bestId, title: title, url: decoded });
    }
    return entries;
  }

  // --- Hook fetch ---
  if (typeof window.fetch !== "undefined") {
    var origFetch = window.fetch;
    window.fetch = function (input, init) {
      var url = typeof input === "string" ? input : input && input.url;
      return origFetch
        .call(window, input, init)
        .then(function (response) {
          var contentType = (response.headers && response.headers.get("content-type")) || "";
          if (contentType.indexOf("image/") === 0 || contentType.indexOf("font/") === 0 ||
              contentType.indexOf("video/") === 0 || contentType.indexOf("audio/") === 0) {
            return response;
          }
          var cloned = response.clone();
          cloned
            .text()
            .then(function (body) { scanBody(url, body); })
            .catch(function () {});
          return response;
        })
        .catch(function (err) { return Promise.reject(err); });
    };
  }

  // --- Hook XMLHttpRequest ---
  if (typeof XMLHttpRequest !== "undefined") {
    var OrigXHR = XMLHttpRequest;
    window.XMLHttpRequest = function () {
      var xhr = new OrigXHR();
      var _url = "";
      var origOpen = xhr.open;
      xhr.open = function (method, url) {
        _url = url;
        return origOpen.apply(xhr, arguments);
      };
      var origSend = xhr.send;
      xhr.send = function (body) {
        var url = _url;
        xhr.addEventListener("load", function () {
          var ct = xhr.getResponseHeader("content-type") || "";
          if (ct.indexOf("image/") === 0 || ct.indexOf("font/") === 0 ||
              ct.indexOf("video/") === 0 || ct.indexOf("audio/") === 0) return;
          scanBody(url, xhr.responseText);
        });
        return origSend.apply(xhr, arguments);
      };
      return xhr;
    };
    window.XMLHttpRequest.prototype = OrigXHR.prototype;
  }
})();