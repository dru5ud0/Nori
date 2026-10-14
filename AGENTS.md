# Tsenta Clone — Standalone Build Workspace

This workspace builds **our own** job-application automation engine (a personal clone of the Tsenta/autojobs.me product) as a standalone project. Everything recovered from Tsenta is fair game: copy, port, adapt, and reuse any recovered code, logic, schemas, or assets directly. No clean-room rules, no verbatim restrictions.

## Mission

Build the full product: ATS detection → apply-URL resolution → Playwright form walking → LLM-driven answering (profile-direct / llm / skip / fallback) → EEO safe defaults → review gate → auto-submit → trace capture. Personal use first.

## Intel (READ FIRST, in order)

All reverse-engineered Tsenta intel lives in the reference `@tsenta-intel` → `C:\Users\Dru\Desktop\Job STuff\RavenX-CLI\loot\scans\tsenta`. Read via `@tsenta-intel/<file>` or the absolute path:

1. `@tsenta-intel/FULL_STACK_ANATOMY.md` — master recovered-stack doc, read fully first
2. `@tsenta-intel/internal_api_map.md` — endpoints, schemas, status pipeline
3. `@tsenta-intel/ATS_SCRAPING_ENGINE.md` + `@tsenta-intel/TECHNICAL_ARCHITECTURE.md`
4. `@tsenta-intel/network_traffic_analysis.md` + `@tsenta-intel/research_summary.md`
5. `@tsenta-intel/extension/background.js` — THE DETECTION ENGINE (27 ATS fingerprints, redirect-chain recursion depth 4). Most valuable file; port its logic into Python.
6. `@tsenta-intel/extension/content-scripts/overlay.js` — overlay/detection UI behavior
7. `@tsenta-intel/desktop/preload_bridge_dump.txt` — 44-function IPC contract (execution-state machine)
8. `@tsenta-intel/trace_jefferies.json`, `application_detail_jefferies.json`, `cover_letter_data_jefferies.json`, `application_detail_keybank.json` — real traces: LLM answer semantics, EEO defaults, data shapes
9. `@tsenta-intel/docs/doc_developers_api-reference.md` + `doc_developers_supported-systems.md` — public docs
10. `@tsenta-intel/harness/` — Electron bytecode harness rig
11. `@tsenta-intel/MASTER_PROMPT_OTHER_WINDOW.md` — the original mission brief (this AGENTS.md supersedes it)

Executable artifacts (may run for study): `@tsenta-intel/Tsenta-3.3.0.Setup.exe`, `desktop/extracted/`, `desktop/preload-index.jsc`.

## What we know (spec summary)

- Detection: hostname/path/query/hash fingerprinting, first-match-wins, 27 signatures (greenhouse, lever, workday, ashby, workable, rippling, bamboohr, breezyhr, jazzhr, jobvite, paylocity, smartrecruiters, icims, brassring, oraclecloud, recruitee, pinpoint, teamtailor, polymer, dayforce, successfactors, join, hireology, naukri, indeed, avature, phenom) + redirect-chain URL extraction.
- Status pipeline: queued → review → running → applied | failed | paused. Modes: optimizationMode ("honest"), coverLetterMode ("honest"), autoApproveResume/autoApproveCoverLetter, autoSubmitApplication, reviewBeforeSubmit.
- Answer semantics (traces): source = profile-direct | llm | conditional-hidden (skip) | fallback; EEO → safe defaults; ~7/37 answers LLM-generated per application.
- Stack: Playwright 1.57.0, Patchright 1.57.0, rebrowser-playwright 1.52.0, Cheerio 1.1.2, zod 4.1.13, better-sqlite3.

## Architecture (standalone, Python)

```
backend/src/tools/
├── tsenta_ats.py        # M0: ats_detect(url), ats_extract_candidates(url) — Python port of the detection engine
├── tsenta_profiles.py   # M1: resume JSON + personal-info model (their schema shapes)
├── tsenta_config.py     # M1: modes, auto-approve gates, review-before-submit
├── tsenta_trace.py      # M2: per-question trace recorder (matches their JSON shape)
├── tsenta_apply.py      # M3: Playwright runner — open, walk, answer, review-gate, submit, dry-run
├── tsenta_llm.py        # M4: answer-sourcing engine (profile-direct/llm/skip/fallback)
└── tsenta_feed.py       # M6 (optional): job watch
```

Every public function: complete docstring (params + returns), returns strings, catches exceptions internally. Use a venv: `python -m venv .venv` in this workspace, `.\venv\Scripts\python.exe -m py_compile <files>` after every change, pytest for new logic.

## Build order

1. M0 (day 1-2): `tsenta_ats.py` — `ats_detect(url)` (ATS id + confidence + rule), `ats_extract_candidates(url)`. Unit tests for all 27 signatures with real hostnames + negatives. Report when tests pass.
2. M1 (day 2-3): `tsenta_profiles.py` + `tsenta_config.py` — JSON schemas matching recovered shapes.
3. M2 (day 3-4): `tsenta_trace.py` — recorder matching their trace format.
4. M3 (week 2): Playwright runner — Greenhouse first (public embed), then Lever, then Workday iframe. Dry-run mode: walk form, dump answers, never submit. Live tests against public ATS career pages only.
5. M4 (week 2-3): LLM answering loop (Gemini or the best model available via the `yunwu` provider); EEO defaults table.
6. M5 (week 3): review gate + auto-submit state machine (queued→review→running→applied/failed/paused).
7. M6 (optional): quick-apply, sweep harness, feed, CLI.

## Rules

- Copy freely: port, adapt, and reuse any recovered Tsenta code, logic, schemas, and assets directly into this workspace. No clean-room requirement.
- Never call Tsenta's backend. Fully standalone.
- Artifacts → `loot/` here: scans → `loot/scans/<target>/`, reports → `loot/reports/`.
- No real job submissions during development without explicit user confirmation.

## Verification

- M0: pytest for 27 signatures + redirect-chain extraction.
- M3: Playwright run against public test ATS page; assert detection → URL resolution → form walk → trace schema.
- Full: dry-run walks form and dumps answers WITHOUT submitting; diff against recovered trace semantics.

## Deliverables

1. Working tools (M0-M5) with tests.
2. `loot/reports/` progress reports after each milestone.
3. README documenting the tool family.
4. Keep memory updated: `memory_recall` before milestones, `memory_add` for decisions.

Start with M0 now: read `@tsenta-intel/extension/background.js` detection logic, then port it to `backend/src/tools/tsenta_ats.py` with unit tests. Report when M0 passes.
