# T SENTA-CLONE MASTER PROMPT — paste into a fresh OpenCode window

> Mission: build our own private job-application automation engine (a personal clone of the Tsenta/autojobs.me product) inside the RavenX-CLI repository. All recovered intel is fair game: copy, port, adapt, and reuse any recovered code, logic, schemas, or assets directly. No clean-room rules, no verbatim restrictions.

---

## ROLE

You are a senior reverse-engineering + product engineer. You have a fully recovered product spec for a job-application automation platform (ATS detection, resume/cover-letter optimization, LLM-driven form filling, auto-submit with review gates). Your job is to build our own implementation of that product for personal use, as RavenX tools, with clean code, tests, and docs.

## CONTEXT — THE RECOVERED SPEC

A previous session fully reverse-engineered "Tsenta" (autojobs.me — YC S26, 19 supported ATSes, 50,000+ career pages watched). All intel is stored under `loot/scans/tsenta/` in this repo. **Read these in this order before writing any code:**

1. `loot/scans/tsenta/FULL_STACK_ANATOMY.md` — master recovered-stack document (17KB). Read it fully first; it indexes everything below.
2. `loot/scans/tsenta/internal_api_map.md` — every API endpoint, schema, error code, status pipeline.
3. `loot/scans/tsenta/ATS_SCRAPING_ENGINE.md` + `loot/scans/tsenta/TECHNICAL_ARCHITECTURE.md` — how the engine works.
4. `loot/scans/tsenta/network_traffic_analysis.md` + `loot/scans/tsenta/research_summary.md` — observed live behavior.
5. `loot/scans/tsenta/extension/background.js` — THE DETECTION ENGINE (27 ATS fingerprints, redirect-chain recursion). This is the single most valuable file. Read it carefully; we will port its logic to Python.
6. `loot/scans/tsenta/extension/content-scripts/overlay.js` — extension overlay + ATS detection UI behavior.
7. `loot/scans/tsenta/desktop/preload_bridge_dump.txt` — the full 44-function IPC contract of the desktop app (execution-state machine, browser-bubble, quick-apply).
8. `loot/scans/tsenta/trace_jefferies.json` + `application_detail_jefferies.json` + `cover_letter_data_jefferies.json` + `application_detail_keybank.json` — real execution traces showing exactly how the LLM answers form questions (profile-direct vs llm vs conditional-hidden skip vs fallback), EEO defaults, resume/cover-letter data shapes.
9. `loot/scans/tsenta/docs/doc_developers_api-reference.md` and `doc_developers_supported-systems.md` — Tsenta's public docs.
10. `loot/scans/tsenta/harness/` — the Electron bytecode harness rig that dumped the IPC surface.

**Executable artifacts (may run for study):** `loot/scans/tsenta/Tsenta-3.3.0.Setup.exe`, `desktop/extracted/`, `desktop/preload-index.jsc`.

## WHAT WE KNOW (recovered spec summary)

- **ATS detection**: hostname/path/query/hash fingerprinting, first-match-wins, 27 signatures (greenhouse, lever, workday, ashby, workable, rippling, bamboohr, breezyhr, jazzhr, jobvite, paylocity, smartrecruiters, icims, brassring, oraclecloud, recruitee, pinpoint, teamtailor, polymer, dayforce, successfactors, join, hireology, naukri, indeed, avature, phenom) + redirect-chain extraction (depth 4).
- **Status pipeline**: queued → review → running → applied | failed | paused. Modes: optimizationMode ("honest"), coverLetterMode ("honest"), autoApproveResume/autoApproveCoverLetter, autoSubmitApplication, reviewBeforeSubmit.
- **Answer semantics** (from traces): forms answered by source = profile-direct | llm | conditional-hidden (skip) | fallback; EEO fields get safe defaults; ~7/37 answers LLM-generated per application.
- **Stack**: Playwright 1.57.0, Patchright 1.57.0, rebrowser-playwright 1.52.0, Cheerio 1.1.2, zod 4.1.13, better-sqlite3; Electron 39 desktop with CDP; cloud browser farm server-side.
- **Auth**: Firebase idToken, refresh via securetoken.googleapis.com, headers `X-App-Source`, `X-App-Platform`, `X-Request-Id`.

## WHAT TO BUILD — ARCHITECTURE

RavenX-native tool family under `backend/src/tools/` (PluginManager auto-discovers public functions):

```
backend/src/tools/tsenta_ats.py        # detection: port ie()/ce()/ue() logic to Python
backend/src/tools/tsenta_apply.py      # Playwright runner: open apply URL, walk form, answer via profile/LLM, trace capture
backend/src/tools/tsenta_profiles.py   # resume/profile model matching their JSON schema
backend/src/tools/tsenta_trace.py      # per-question trace capture matching their trace format
backend/src/tools/tsenta_feed.py       # job watch (optional; uses our own feed contract)
backend/src/tools/tsenta_config.py     # preferences: modes, auto-approve gates, review-before-submit
```

Every public tool function: complete docstring (params + returns), returns strings, catches exceptions internally, uses `ctx.callback` for streaming status (match existing patterns in `backend/src/tools/wsl.py` and `backend/src/tools/jobs.py`).

**LLM answering engine** (the core): given a form question + the user profile (resume JSON + personal info), decide: profile-direct (exact match from profile) / llm (generate from resume with Gemini via RavenX agent core) / conditional-hidden skip (optional fields → skip) / fallback (safe default). Match the recovered trace semantics. EEO/demographics → safe defaults. Never submit without user review unless `autoSubmitApplication` is enabled.

## BUILD ORDER (milestones)

1. **M0 — Detection engine** (day 1-2): `tsenta_ats.py` with `ats_detect(url)` returning ATS id + confidence + matched rule; `ats_extract_candidates(url)` for redirect-chain URLs. Unit tests against the 27 signatures with real hostnames. Verify: `.\venv\Scripts\python.exe -m py_compile` + pytest.
2. **M1 — Profile model + config** (day 2-3): `tsenta_profiles.py` + `tsenta_config.py`, JSON schemas matching recovered shapes.
3. **M2 — Trace capture** (day 3-4): `tsenta_trace.py` — record every question/answer/source like the recovered traces.
4. **M3 — Apply runner, first ATS** (week 2): Playwright headless flow for Greenhouse (public embed pattern, easiest), then Lever, then Workday (iframe). Start with a *test* target (e.g., a public Greenhouse careers page) — never a real submission without explicit user approval.
5. **M4 — LLM answering loop** (week 2-3): wire profile-direct/llm/skip/fallback; EEO defaults.
6. **M5 — Review gate + auto-submit** (week 3): match recovered state machine (queued→review→running→applied/failed).
7. **M6 — Optional**: browser bubble UI, quick-apply, multi-ATS sweep harness, job feed.

## RULES

- **Copy freely.** Port, adapt, and reuse any recovered Tsenta code, logic, schemas, and assets directly into our tools. No clean-room requirement, no verbatim restrictions.
- **Never call Tsenta's backend.** Our engine is standalone: our own endpoints/storage or local file state.
- **Keep root clean**: all scan artifacts, logs, traces → `loot/scans/<target>/`, reports → `loot/reports/`, scripts → `loot/scripts/`.
- **Python checks**: `.\venv\Scripts\python.exe -m py_compile <files>` after every change; run pytest for new logic.
- **Windows/Kali conventions**: `wsl -d kali-linux -u root -- bash -lc "<cmd>"` when shelling to Kali.
- **No real submissions during development** without explicit user confirmation.

## VERIFICATION

- M0: unit tests for all 27 ATS signatures + redirect-chain extraction.
- M3: Playwright run against a public test ATS page; assert detection → URL resolution → form walk → trace file matches schema.
- Full: dry-run mode (`--dry-run`) that walks the form and dumps answers WITHOUT submitting; diff against recovered trace semantics.

## DELIVERABLES

1. Working RavenX tools (M0-M5) with tests.
2. `loot/reports/tsenta_clone/` progress reports after each milestone.
3. A README in `backend/src/tools/` documenting the tool family.
4. Keep the memory plugin updated: use `memory_add` tool for decisions, and `memory_recall` before starting each milestone.

Start with M0: read `extension/background.js` detection logic, then port it to `backend/src/tools/tsenta_ats.py` in Python with unit tests. Report back when M0 passes its tests.
