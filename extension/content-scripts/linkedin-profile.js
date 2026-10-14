/**
 * TsentaClone recruiter/vendor capture for authenticated LinkedIn profiles.
 *
 * Runs only on /in/ profile pages. A user click captures public professional
 * profile text into the local Mission Control networking store. It does not
 * connect, follow, message, or perform any LinkedIn account action.
 */
(function () {
  "use strict";

  var host = null;

  function isProfilePage() {
    return /^\/in\/[^/]+\/?$/.test(window.location.pathname);
  }

  function clean(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function canonicalUrl() {
    var canonical = document.querySelector('link[rel="canonical"]');
    var value = canonical && canonical.href ? canonical.href : window.location.href;
    try {
      var parsed = new URL(value);
      return parsed.origin + parsed.pathname.replace(/\/$/, "");
    } catch (_) {
      return window.location.href.split(/[?#]/)[0].replace(/\/$/, "");
    }
  }

  function sectionText(label) {
    var headings = Array.from(document.querySelectorAll("main h1, main h2, main h3"));
    var heading = headings.find(function (node) {
      return clean(node.textContent).toLowerCase() === label.toLowerCase();
    });
    if (!heading) return "";
    var section = heading.closest("section") || heading.parentElement;
    return clean(section ? section.innerText : "").slice(0, 12000);
  }

  function profileData() {
    var main = document.querySelector("main") || document.body;
    var fullText = clean(main.innerText).slice(0, 50000);
    var titleName = clean(document.title.replace(/\s*\|\s*LinkedIn.*$/i, ""));
    var headings = Array.from(main.querySelectorAll("h1, h2"));
    var heading = headings.find(function (node) { return clean(node.textContent) === titleName; }) || headings[0];
    var name = titleName || clean(heading && heading.textContent);
    var allLines = String(main.innerText || "").split(/\r?\n/).map(clean).filter(Boolean);
    var nameIndex = allLines.findIndex(function (line) {
      return line === name || line.indexOf(name + " ·") === 0;
    });
    var headerLines = allLines.slice(Math.max(0, nameIndex), nameIndex >= 0 ? nameIndex + 20 : 30);
    var topText = headerLines.join(" ");
    var headline = "";
    var location = "";
    var company = "";

    headerLines.forEach(function (line) {
      if (!headline && line !== name && line.length > 8 && line.length < 220 &&
          !/^(message|connect|follow|more|contact info|\d+ connections?)$/i.test(line) &&
          !/\b(?:united states|india|illinois|georgia|chicago|atlanta|village)\b/i.test(line) &&
          !/(?:^|\s)[·•]\s*(?:1st|2nd|3rd)/i.test(line) &&
          !/^(highlights|about|activity|get introduced)/i.test(line)) {
        headline = line;
      }
      if (!location && /\b(?:united states|india|illinois|georgia|chicago|atlanta|village|california|texas|new york)\b/i.test(line)) {
        location = line;
      }
    });

    var organizationTexts = Array.from(main.querySelectorAll("button, a")).map(function (node) {
      return clean(node.textContent);
    }).filter(function (line) { return line && line.length < 160; });
    company = organizationTexts.find(function (line) {
      return /\b(?:consulting|staffing|rpo|solutions|technologies|systems|group|inc|llc|limited)\b/i.test(line) || line.toLowerCase() === "sayers";
    }) || "";

    var about = sectionText("About");
    var degree = "";
    var degreeMatch = topText.match(/[·•]\s*(1st|2nd|3rd\+?)/i) || fullText.slice(0, 1500).match(/[·•]\s*(1st|2nd|3rd\+?)/i);
    if (degreeMatch) degree = degreeMatch[1];

    var emailMatch = fullText.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
    var url = canonicalUrl();
    return {
      name: name,
      linkedinUrl: url,
      headline: headline,
      location: location,
      company: company,
      connectionDegree: degree,
      email: emailMatch ? emailMatch[0] : "",
      about: about,
      rawText: fullText,
      status: "discovered",
      tags: ["linkedin", "recruiter-vendor"],
      evidence: [{
        sourceUrl: url,
        kind: "linkedin-profile",
        text: (about || fullText).slice(0, 12000),
        capturedAt: Date.now()
      }]
    };
  }

  function setState(state, detail) {
    if (!host || !host.shadowRoot) return;
    var button = host.shadowRoot.querySelector("button");
    var status = host.shadowRoot.querySelector("small");
    if (button) button.disabled = state === "saving";
    if (status) status.textContent = detail || state;
  }

  function capture() {
    if (!isProfilePage()) {
      setState("blocked", "open a profile first");
      return;
    }
    setState("saving", "saving locally…");
    fetch("http://127.0.0.1:8000/api/networking/contacts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contact: profileData() })
    }).then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    }).then(function (result) {
      var score = result.contact && result.contact.score;
      setState("saved", "saved · score " + String(score == null ? "?" : score));
    }).catch(function () {
      setState("offline", "Mission Control offline");
    });
  }

  function mount() {
    if (host || !document.documentElement || !isProfilePage()) return;
    host = document.createElement("div");
    host.id = "tsenta-network-capture";
    host.style.cssText = "position:fixed;right:18px;bottom:18px;z-index:2147483647";
    var shadow = host.attachShadow({ mode: "open" });
    shadow.innerHTML = [
      "<style>",
      "button{all:unset;display:flex;align-items:center;gap:8px;cursor:pointer;background:#fffdf6;color:#111;border:2px solid #111;border-radius:6px;padding:10px 13px;font:700 12px Manrope,system-ui;box-shadow:4px 4px 0 #111}",
      "button:disabled{cursor:wait;opacity:.75}",
      "b{background:#ffd447;color:#111;padding:2px 5px;border:1px solid #111}small{color:#625f58;font-size:10px;font-weight:600}",
      "</style>",
      "<button title='Save this public professional profile locally'><b>tsenta</b><span>Capture recruiter</span><small>ready</small></button>"
    ].join("");
    shadow.querySelector("button").addEventListener("click", capture);
    document.documentElement.appendChild(host);
  }

  function syncRoute() {
    if (isProfilePage()) mount();
    else if (host) { host.remove(); host = null; }
  }

  chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (message.type !== "TSENTA_PROFILE_STATUS") return false;
    var isProfile = isProfilePage();
    sendResponse({
      ok: true,
      profilePage: isProfile,
      controlVisible: Boolean(host && host.isConnected),
      profile: isProfile ? profileData() : null
    });
    return false;
  });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", syncRoute, { once: true });
  else syncRoute();
  setInterval(syncRoute, 700);
})();
