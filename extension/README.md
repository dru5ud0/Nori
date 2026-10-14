# TsentaClone Browser Companion

The unpacked Manifest V3 extension captures external apply URLs exposed inside
authenticated LinkedIn RSC responses, rich JobRight recommendation rows, and
reviewed recruiter/vendor profiles. It never calls Tsenta or AutoJobs. Captured
jobs remain in local extension storage until the user explicitly prepares one;
clicking **Capture recruiter** on a LinkedIn profile stores its public
professional evidence in the local `/api/networking/contacts` CRM.

## Install

1. Start TsentaClone with `start-tsenta-clone.cmd`.
2. Open `chrome://extensions` or `brave://extensions`.
3. Enable **Developer mode**.
4. Choose **Load unpacked** and select this `extension` directory.
5. Pin **Tsenta Local Companion** from Brave's extensions menu. Its popup shows
   Mission Control status, the active page state, captured-job count, CRM count,
   and the currently selected job.
6. Open an authenticated LinkedIn job search, JobRight feed, or LinkedIn
   recruiter profile. Reload the extension after updating its files.

The toolbar badge displays **CRM** on recruiter profiles, **JOB** on supported
job pages, and **ON** elsewhere. Clicking the icon always opens a visible status
popup, even when the current page is unsupported.

The floating job card reports the selected job and captured count. Jobs stay in
`chrome.storage.local` until the user clicks **Prepare locally**. That click runs
Mission Control preflight (ATS, duplicate, profile, and review-mode checks) and
creates one queued application. Merely viewing a job never queues it.

The recruiter control appears only on LinkedIn `/in/...` profile routes. The job
card appears only on LinkedIn job routes or JobRight and only after the selected
job has a resolved external application URL. Both controls follow LinkedIn SPA
navigation and remove themselves when their route is no longer active.

## Troubleshooting

- After changing extension files, click **Reload** on the unpacked extension and
  refresh the LinkedIn or JobRight tab.
- **Mission Control offline** means `http://127.0.0.1:8000` is not running or
  Brave has not allowed localhost/local-network access for the page.
- **Already queued** means duplicate preflight succeeded and no second
  application was created.
- The recruiter score is a qualification score, not a capture-success count.
- Run the Brave regression check with
  `.\.venv\Scripts\python.exe loot\scripts\verify_extension_runtime.py`.

## Safety

- The extension reads only responses made by LinkedIn or JobRight tabs.
- External URLs are queued only after the explicit **Prepare locally** click.
- The extension never runs or approves an application; review gates remain in
  Mission Control.
- Recruiter profiles are captured only when the user clicks the capture button.
- Profile capture never connects, follows, messages, or changes LinkedIn.
- Real application submission remains protected by the explicit review gate.
