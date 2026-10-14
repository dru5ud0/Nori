# Nori AI — Local Job-Application Copilot

A standalone job-application engine with a Nori AI frontend: ATS detection → apply-URL
resolution → Playwright form walking → LLM-driven answering → EEO safe defaults
→ review gate → auto-submit → trace capture. Personal use, fully standalone
(no calls to Tsenta's backend).

## Webapp (primary interface)

Run `start-nori-ai.cmd`, then open `http://localhost:8000`. The local
React 19 Nori AI workspace includes Dashboard, HiringCafe Browse jobs, Automation,
Applications, Inbox, Tracker, Networking, Resume, Profile, Research, Settings,
and LinkedIn harvest surfaces. FastAPI serves both the SPA and the local API.

Frontend stack: React 19, Vite 8, TypeScript 6, Tailwind CSS 4, TanStack Query,
Radix primitives, Framer Motion, Lucide, Sonner, and Zustand.

The browser companion under `extension/` captures authenticated LinkedIn RSC
apply URLs and JobRight recommendation rows and queues them locally. See
`extension/README.md` for unpacked installation.

## Tool family (`backend/src/tools/`)

| Module | Milestone | Purpose |
|---|---|---|
| `tsenta_ats.py` | M0 | Python port of the recovered detection engine: `ats_detect(url)` (ATS id + confidence + rule), `ats_extract_candidates(url)` (redirect-chain extraction, depth 4), `ats_display_name()`. 34 ATS signatures, first-match-wins, plus normalized exact-feed hints for branded ATS domains. |
| `tsenta_capabilities.py` | Safety | Honest per-ATS execution registry. Detection, preparation, manual submit, and unattended-submit certification are separate capabilities. |
| `tsenta_answer_policy.py` | Safety | Shared country-scoped work-authorization and consent/attestation review policy. |
| `tsenta_greenhouse.py` | Adapter | Greenhouse URL normalization, application-form signatures, and structured ATS confirmation receipts. |
| `tsenta_lever.py` | Adapter | Lever/Lever EU canonical apply URLs, exact form signatures, and Lever-owned confirmation receipts. |
| `tsenta_workday.py` | Adapter | Workday posting/apply URL resolution, apply-flow scoping, custom dropdown and wizard navigation, login gates, and Workday-owned confirmation receipts. |
| `tsenta_ashby.py` | Adapter | Ashby posting/application URL resolution, exact `_systemfield_*` form signatures, and Ashby-specific confirmation receipts. |
| `tsenta_smartrecruiters.py` | Adapter | SmartRecruiters OneClick apply-link resolution, closed-job detection, DataDome challenge detection, and strict confirmation receipts. |
| `tsenta_icims.py` | Adapter | iCIMS content-iframe and employer apply-link resolution, privacy/CAPTCHA gate handling, and cross-frame confirmation receipts. |
| `tsenta_jazzhr.py` | Adapter | JazzHR/Resumator URL normalization, exact form signatures, starred required fields, and ATS-specific confirmation receipts. |
| `tsenta_jobvite.py` | Adapter | Jobvite URL resolution, closed-job handling, explicit Data Consent pause, and ATS-specific confirmation receipts. |
| `tsenta_breezyhr.py` | Adapter | Breezy HR canonical `/apply` resolution, public-form detection, closed-job handling, and strict confirmation receipts. |
| `tsenta_recruitee.py` | Adapter | Recruitee documented `/c/new` routing, hydrated React-form handling, closed-job detection, and strict confirmation receipts. |
| `tsenta_teamtailor.py` | Adapter | Teamtailor application-overlay opening/scoping, closed-job detection, privacy-review preservation, and strict confirmation receipts. |
| `tsenta_dayforce.py` | Adapter | Live dry-run-verified Dayforce guest routing, current compact field IDs, focused form preprocessing, employer privacy/CAPTCHA review handoff, closed-job detection, and strict confirmation receipts. |
| `tsenta_paylocity.py` | Adapter | Live dry-run-verified Paylocity direct routing, upload-first résumé parsing, labeled screening questions, controlled four-step walking, user-reviewed attestations, and strict confirmation receipts. |
| `tsenta_brassring.py` | Adapter | BrassRing job-detail normalization, external-applicant/account routing, explicit employer privacy-review handoff, and strict confirmation receipts. |
| `tsenta_adp.py` | Adapter | ADP Workforce Now and MyJobs routing, closed-posting detection, candidate-account checkpoints, conservative cookie handling, and strict confirmation receipts. |
| `tsenta_paycom.py` | Adapter | Paycom legacy-to-modern job routing, guest identity preflight, multi-step continuation, closed-posting detection, and strict confirmation receipts. |
| `tsenta_successfactors.py` | Adapter | SAP SuccessFactors classic and branded-career routing, tenant account checkpoints, closed-posting detection, and strict confirmation receipts. |
| `tsenta_zohorecruit.py` | Adapter | Zoho Recruit public-form routing, non-essential-cookie decline, custom-control label/required normalization, consent-safe review fields, and strict confirmation receipts. |
| `tsenta_ultipro.py` | Adapter | UKG Pro/UltiPro legacy and current opportunity routing, candidate sign-in checkpoints, closed-posting detection, and strict confirmation receipts. |
| `tsenta_avature.py` | Adapter | Avature branded-career routing, guest résumé-first flow handling, cross-ATS redirect handoff, candidate credential checkpoints, and strict confirmation receipts. |
| `tsenta_pinpoint.py` | Adapter | Pinpoint public apply routing, lazy React-select handling, exact radio/question labeling, non-essential-cookie rejection, and strict confirmation receipts. |
| `tsenta_phenom.py` | Adapter | Phenom branded-job routing, native multi-stage form normalization, exact country/state/source selection, non-essential-cookie denial, CAPTCHA review gates, and strict confirmation receipts. |
| `tsenta_hireology.py` | Adapter | Hireology accountless form opening, label/required normalization, résumé and cover-letter handling, privacy-safe SMS defaults, EEO review semantics, and strict confirmation receipts. |
| `tsenta_join.py` | Adapter | JOIN public-job routing, hidden-form discrimination, email/magic-link checkpoint handoff, persistent-session continuation, closed-job detection, and strict confirmation receipts. |
| `tsenta_dover.py` | Adapter | Dover public-form routing, UUID-question labeling, parser-versus-attachment résumé handling, work-authorization mapping, Turnstile review gating, and strict confirmation receipts. |
| `tsenta_gem.py` | Adapter | Gem hosted-form routing, nameless React-field normalization, sponsorship grouping, voluntary-EEO preservation, and strict confirmation receipts. |
| `tsenta_polymer.py` | Adapter | Polymer inline-form routing, direct-field and custom-question normalization, reCAPTCHA exclusion, Cloudflare checkpoint handling, and strict confirmation receipts. |
| `tsenta_indeed.py` | Adapter | Indeed job canonicalization, hosted-versus-employer apply routing, account/phone/browser checkpoints, hosted-form normalization, and strict Indeed-owned receipts. |
| `tsenta_naukri.py` | Safety adapter | Naukri closed/challenge/account detection and one-click submission protection. Nori intentionally does not click a possibly immediate Apply action during draft preparation. |
| `tsenta_bullhorn.py` | API adapter | Bullhorn Public REST job identity validation, read-only open/public preflight, reviewable candidate fields, guarded raw-résumé application transport, and structured response receipts. |
| `tsenta_workable.py` | Adapter | Workable `/apply/` routing, current identity-form signatures, closed-job detection, and strict Workable confirmation receipts. |
| `tsenta_bamboohr.py` | Adapter | BambooHR posting/modal resolution, custom State/Country menus, closed-job detection, and strict BambooHR confirmation receipts. |
| `tsenta_rippling.py` | Adapter | Rippling `/apply` URL normalization, delayed location autocomplete handling, closed-job detection, and strict Rippling confirmation receipts. |
| `tsenta_oraclecloud.py` | Adapter | Oracle Candidate Experience URL normalization, email-first application preflight, explicit consent gate, closed-job detection, and strict receipt helpers. |
| `tsenta_generic_ats.py` | Adapter | Conservative extension point for future ordinary-HTML ATS hosts that do not yet have a dedicated adapter. |
| `tsenta_profiles.py` | M1 | Candidate profile model (18 sections, recovered schema), `profile_get()` dotted paths, `validate_profile()` missingFields gate, `EEO_SAFE_DEFAULTS`, `safe_eeo_profile()`. |
| `tsenta_config.py` | M1 | Recovered config surfaces: extension apply prefs, POST /applications body, desktop auto-apply-config payload. |
| `tsenta_trace.py` | M2 | Per-question trace recorder matching the recovered shape: `{meta{ats,outcome,startedAt,durationMs}, answers[], timeline[], derivedMissingFields[]}`. Verbatim FALLBACK_TEXT + skip/fallback reasons. |
| `tsenta_apply.py` | M3 | Playwright runner: `apply_job(url, profile, config, dry_run, resume_path, answerer, headless, confirmed)` — detect → open form (page/iframe/link) → collect visible fields → answer → trace → dry-run dump. Submit guard: real submit requires dry_run=False AND confirmed=True. M8: per-ATS walker registry (`_ATS_WALKERS` + `register_ats_walker()`/`unregister_ats_walker()`/`ats_walker()`) — 33 dry-run verified ATS walker profiles with explicit multi-step advancement and human checkpoint safety. |
| `tsenta_llm.py` | M4 | LLM answer engine (yunwu OpenAI-compatible endpoint): `make_llm_answerer()` drop-in for the answerer seam, `chat_completion()` stdlib-urllib transport, EEO-safe option picks tagged llm, honest-mode fallback. |
| `tsenta_pipeline.py` | M5 | Review gate + auto-submit state machine (queued→review→running→applied|failed|paused), receipt/manual/legacy evidence separation, reversible application archiving, JSON store, and CLI controls. |
| `tsenta_feed.py` | M6 | Job watch: public Greenhouse boards API / Lever postings API / URL lists → normalized feed, dedup vs the job store. |
| `tsenta_hiringcafe.py` | Nori upgrade | Live HiringCafe discovery, direct apply-URL normalization, deduplication, explainable profile matching, and penalties/warnings for unverified clearance, citizenship, experience, and certification requirements. |
| `nori_monitor.py` | Nori upgrade | Persistent overnight settings, Windows keep-awake support, run history, seven-day workload preview, and private Telegram alerts/actions. |
| `tsenta_documents.py` | M7+M9 | Resume and cover-letter engine with ChatGPT OAuth support, job-keyword targeting, unsupported-claim checks, employer-scoped fact validation, and deterministic safety fallback when an LLM draft crosses evidence boundaries. |
| `tsenta_cli.py` | M6 | Full CLI: `feed`, `quick` (one-shot apply), `sweep` (feed → pipeline), plus run/approve/reject/status/report/list/summary. Installed as the `tsenta-cli` console script. |

## Setup

```
python -m venv .venv
    .venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m playwright install chromium
.venv\Scripts\python -m pip install -e .      # optional: installs the tsenta-cli command
```

`tsenta-cli` (or `python -m backend.src.tools.tsenta_cli`) is the single entry
point for everything:

```
tsenta-cli feed greenhouse:mozilla --save           # fetch job feed (public APIs)
tsenta-cli quick <job-url>                           # one-shot: walk + answer + docs, stops at review
tsenta-cli sweep loot/state/feed.json --limit 5      # quick-apply over a feed
tsenta-cli approve <id>                              # the ONLY explicit real-submit path
tsenta-cli report <id>                               # full record: trace + sources + documents
tsenta-cli list | summary | status | reject
```

## Nori AI workflow

- **Browse jobs** searches HiringCafe and ranks results against the local profile. The saved ranking powers Dashboard **Top job matches**. Requirement warnings call out unconfirmed clearance, citizenship, experience, and certification constraints instead of presenting them as clean matches.
- **Review & apply** runs the browser walker immediately in dry-run mode and stops at **Needs you**.
- In an application's **Form answers** tab, expand a question, change its reviewed value, and save. User overrides take priority during the approved final run.
- **Automation** can repeat the HiringCafe search every 15 minutes to 24 hours. It supports multiple search lanes, per-cycle limits, a shared 1–150 daily application budget, recent run history, and a seven-day activity projection. When enabled, Windows is kept awake while the Nori server window remains open; the display may still turn off.
- Telegram is optional. Add a BotFather token and chat ID under **Automation**, save, and use **Send test**. Secrets remain in `loot/state/nori-monitor.json` and are masked from browser responses. Environment variables `NORI_TELEGRAM_BOT_TOKEN` and `NORI_TELEGRAM_CHAT_ID` are also supported.

Automation has three saved modes: Notify, Prepare, and Request auto-submit on certified ATSes. No adapter is currently certified for unattended submission, so the last mode safely stops at review today. A private Telegram Submit button or the in-app approval is explicit user authorization. The default remains Notify with monitoring disabled. Keep the local server running for scheduled work.

Paste an actual HiringCafe filtered search URL into Automation to preserve its native experience, salary, sponsorship, and other filters. Excluded titles and strict-location filtering also apply to Browse Jobs and Dashboard Top Matches. Scores are ranking heuristics, not hiring probabilities. Unlisted salaries remain eligible for the local minimum-salary check.

Telegram uses private-chat callbacks, not localhost links. Tap Prepare application, then Submit this application on a ready draft; unresolved applications need editing in the local UI. Only the configured private chat/user may control applications. Use a dedicated bot; do not run another poller/webhook on the same bot. Live Telegram operation requires a configured bot token and chat ID.

### ChatGPT sign-in

Under Automation → AI provider connection, select **ChatGPT sign-in (local Codex)**. Install Codex and run `codex login` once if needed. Nori calls the installed CLI with managed authentication in ephemeral read-only text runs; it never copies OAuth tokens. This uses your ChatGPT/Codex allowance. Leave Model ID blank for the CLI default, or choose an accessible Codex model. Use **Test saved connection** to verify actual access.

API-key providers remain available as an alternative with a Windows-DPAPI-encrypted key. Provider failures are shown explicitly; basic fallback documents are labelled and do not pass unattended-application quality checks. The old Yunwu endpoint currently reports migrated accounts must use OpenLux; Nori does not forward old credentials to a new endpoint automatically.

Reviewed documents and generated answers are reused on final approval. Profile-direct facts use the current profile; explicitly edited answers have highest priority. Work authorization is country-scoped, and unknown eligibility, consent, attestations, health/military status, and unresolved choices are not guessed. No document can guarantee an interview or selection.

Real browser runs preserve per-ATS cookies and local storage under `loot/state/browser-sessions/`. If Nori is restarted while an application is marked running, startup recovery changes it to paused with `interrupted-run-recovered`, allowing a deliberate retry instead of leaving it stuck. Greenhouse, Lever, Workday, Ashby, iCIMS, JazzHR, Workable, BambooHR, Rippling, Jobvite, Breezy HR, Recruitee, Teamtailor, Dayforce, Paylocity, BrassRing, ADP, Paycom, SuccessFactors, Zoho Recruit, UKG Pro/UltiPro, Avature, Pinpoint, Phenom, Hireology, JOIN, Dover, Gem, Polymer, Indeed, Naukri, and Bullhorn have dedicated behavior; only adapters backed by captured submission evidence advertise `receiptEvidence`. Bullhorn uses its official public API: dry-run performs a read-only open/public check and prepares the documented identity fields plus résumé locally, while an exact explicit approval is required before candidate data is posted. A bare “thank you” is not confirmation. Workday, BrassRing, ADP, SuccessFactors, UKG, Avature, JOIN, Indeed, and Naukri account/identity gates pause for the user and never cause Nori to store or invent credentials or accept legal terms. Nori does not click Naukri’s potentially immediate one-click Apply action while drafting. Recruitee, Teamtailor, Dayforce, BrassRing, Zoho Recruit, Avature, and Pinpoint privacy/terms choices remain user-reviewed answers. Paylocity legal acknowledgments and employer-specific questions likewise stop for review. Gem leaves voluntary EEO menus blank unless the candidate explicitly supplies an answer. A hidden CAPTCHA enclave is not mistaken for an active challenge, while a visible challenge—including Dover Turnstile or employer-enabled Gem CAPTCHA—remains a submission blocker. When a branded career site redirects into a different supported ATS, Nori re-detects the destination and hands the run to the correct engine while retaining the application trace.

Profile lives at `loot/state/profile.json` (CLI default) — see
`backend/src/tools/tsenta_profiles.py` for the full 18-section schema.

## Usage (dry-run is the default and the only safe path during dev)

```python
import json
from backend.src.tools.tsenta_apply import apply_job
from backend.src.tools.tsenta_profiles import profile_from_json
from backend.src.tools.tsenta_config import default_config
from backend.src.tools.tsenta_llm import make_llm_answerer

profile = profile_from_json(open("profile.json", encoding="utf-8").read())
result = json.loads(apply_job(
    "https://boards.greenhouse.io/mozilla/jobs/123",
    profile, default_config(), dry_run=True,
    answerer=make_llm_answerer(profile),
))
print(result["trace"])
```

### Review-gated pipeline (never submits without explicit approval)

```python
from backend.src.tools.tsenta_pipeline import create_job, run_job, review_approve

job = json.loads(create_job(url, profile))            # -> queued
run_job(job["applicationId"], profile)                # -> review (dry-run walk)
review_approve(job["applicationId"], profile)         # the ONLY path that submits
```

### Feed → sweep → review (CLI)

```
python -m backend.src.tools.tsenta_cli feed greenhouse:mozilla --save
python -m backend.src.tools.tsenta_cli sweep loot/state/feed.json --limit 5
python -m backend.src.tools.tsenta_cli status <id>       # -> review (dry-run)
python -m backend.src.tools.tsenta_cli approve <id>      # explicit real submit
```

`--approve` is the only way to enable real submission; without it every job
stops at the review gate with a dry-run trace.

## Answer sources (recovered semantics)

- `profile-direct`: name/email/phone/address/LinkedIn and country-matched eligibility pulled straight from the profile
- `llm`: open-ended questions and option picks supported by the candidate profile
- `skip`: hidden/conditional fields, consent or attestations, unknown country eligibility, and choices with no safe answer
- `fallback`: verbatim "Please refer to my resume…" text (required questions the LLM cannot answer)

## Tests

```
.venv\Scripts\python -m pytest backend\tests          # fully offline unit/API suite
$env:LIVE = "1"; .venv\Scripts\python -m pytest backend\tests -m live   # live ATS/API smoke tests
```

Live tests hit public ATS career pages (Greenhouse boards API, Lever
leverdemo board, Ashby boards, Workday boards — auto-skips when every public
tenant is unavailable), the configured LLM endpoint, and the public feed
APIs. Default suite is fully offline.

## Configuration

- LLM: `YUNWU_API_KEY`, `YUNWU_BASE_URL` (default `https://yunwu.ai/v1`),
  `YUNWU_MODEL` (default `deepseek-v4-flash`)
- Apply modes live in `tsenta_config.default_config()`:
  `optimizationMode`/`coverLetterMode` (honest), `autoApproveResume`,
  `autoSubmitApplication` (default False — review gate), `reviewBeforeSubmit`.

## Reports & artifacts

Milestone reports: `loot/reports/M0_ats_detection.md` … `M6_feed_sweep_cli.md`,
plus `FIXES_round1.md` / `FIXES_round2.md` (resume-upload guard, no-"Other"
fallback, option-specificity matching, JSON store locking, custom ATS registry,
live-trace answer quality).
Job store: `loot/state/applications.json` (thread-safe via sidecar `.lock`).

## Extending the ATS catalog

`tsenta_ats.register_ats_signature(ats_id, name, url_patterns, predicate)`
registers a custom detection rule checked AFTER the 34 built-ins (never
shadows them); `unregister_ats_signature(ats_id)` removes it again.

Per-ATS form behavior lives in the walker registry:
`tsenta_apply.register_ats_walker(ats_id, submit_selectors=...,
confirm_selectors=..., open=...)` — selectors are tried before the generic
ones, and a custom `open(page, url, timeout_ms)` overrides the form opener.
Dedicated execution paths now cover 33 of the 34 detected ATSes. Naukri remains
detect-only for automatic preparation because its visible Apply action can be an
immediate stored-profile submission. Bullhorn uses a guarded API path; the other
supported systems use ATS-specific browser adapters or conservative form profiles.
