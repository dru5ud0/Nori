/** Capture JobRight recommendation responses from the authenticated page session. */
(function () {
  "use strict";
  var LIST_PATH = "/swan/recommend/list/jobs";
  var FOCUS_PATHS = ["/swan/recommend/similar/jobs", "/swan/recommend/job/custom-questions", "/swan/job/like", "/swan/job/unlike", "/swan/job/apply", "/swan/job/direct-apply-v2", "/swan/share/job/link"];

  function text(value) {
    if (value == null) return null;
    if (typeof value === "string") return value || null;
    if (Array.isArray(value)) return value.map(text).filter(Boolean).join("\n") || null;
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  }

  function mapRow(row) {
    var job = row && row.jobResult;
    if (!job || !job.jobId || !(job.applyLink || job.originalUrl)) return null;
    return {
      jobId: job.jobId,
      applyLink: job.applyLink || job.originalUrl,
      title: job.jobTitle || job.jobNlpTitle || null,
      company: row.companyResult && row.companyResult.companyName || null,
      companyURL: row.companyResult && row.companyResult.companyURL || null,
      jobLocation: job.jobLocation || null,
      jobSummary: job.jobSummary || null,
      coreResponsibilities: text(job.coreResponsibilities),
      qualifications: text(job.qualifications) || text(job.detailQualifications),
      salaryDesc: job.salaryDesc || null,
      workModel: job.workModel || null,
      isRemote: Boolean(job.isRemote),
      publishTime: job.publishTime || null,
      source: typeof job.source === "number" ? job.source : null,
      jdLogo: job.jdLogo || null
    };
  }

  function focus(url, body) {
    if (!FOCUS_PATHS.some(function (path) { return url.indexOf(path) !== -1; })) return;
    var id = null;
    try { var parsed = new URL(url, location.origin); id = parsed.searchParams.get("jobId") || parsed.searchParams.get("id"); } catch (_) {}
    if (!id && typeof body === "string") { try { id = JSON.parse(body).jobId || null; } catch (_) {} }
    if (id) window.postMessage({ type: "TSENTA_JOBRIGHT_FOCUS", jobId: id, at: Date.now() }, location.origin);
  }

  function scan(url, body) {
    focus(url, null);
    if (url.indexOf(LIST_PATH) === -1 || !body) return;
    try {
      var payload = JSON.parse(body);
      var rows = payload && payload.result && payload.result.jobList || [];
      var jobs = rows.map(mapRow).filter(Boolean);
      if (jobs.length) window.postMessage({ type: "TSENTA_JOBRIGHT_JOBS", jobs: jobs, url: url }, location.origin);
    } catch (_) {}
  }

  var originalFetch = window.fetch;
  window.fetch = function (input, init) {
    var url = typeof input === "string" ? input : input && input.url || "";
    focus(url, init && init.body);
    return originalFetch.apply(this, arguments).then(function (response) {
      response.clone().text().then(function (body) { scan(url, body); }).catch(function () {});
      return response;
    });
  };

  var OriginalXHR = window.XMLHttpRequest;
  window.XMLHttpRequest = function () {
    var xhr = new OriginalXHR();
    var url = "";
    var open = xhr.open;
    xhr.open = function () { url = arguments[1] || ""; return open.apply(xhr, arguments); };
    var send = xhr.send;
    xhr.send = function (body) { focus(url, body); xhr.addEventListener("load", function () { scan(url, xhr.responseText); }); return send.apply(xhr, arguments); };
    return xhr;
  };
  window.XMLHttpRequest.prototype = OriginalXHR.prototype;
})();
