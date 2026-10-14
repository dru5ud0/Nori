"""tsenta_cli — quick-apply, sweep harness, and the tool-family CLI (M6).

Brings M0-M5 together as one surface:

    python -m backend.src.tools.tsenta_cli feed  greenhouse:mozilla [--save]
    python -m backend.src.tools.tsenta_cli quick <url> [--approve] [--profile p.json]
    python -m backend.src.tools.tsenta_cli sweep <feed.json|urls.txt> [--approve] [--limit N]
    python -m backend.src.tools.tsenta_cli run|approve|reject|status|report|list|summary ...

Safety: WITHOUT --approve every run stops at the review gate (dry-run, never
submits). --approve is the explicit user confirmation that enables real
submission through review_approve() only.

Public functions return JSON strings and never raise.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

try:
    from backend.src.tools.tsenta_config import default_config
    from backend.src.tools.tsenta_feed import (
        fetch_feed, jobs_to_urls, load_feed, load_urls, new_feed_jobs,
        save_feed,
    )
    from backend.src.tools.tsenta_pipeline import (
        create_job, default_store_path, job_report, job_status, jobs_summary,
        list_jobs, review_approve, review_reject, run_job,
    )
    from backend.src.tools.tsenta_profiles import profile_from_json
    from backend.src.tools.tsenta_resume import resume_import, resume_import_to_file
    from backend.src.tools.tsenta_linkedin import (
        linkedin_guest_search, linkedin_guest_detail, linkedin_resolve_apply_url,
    )
except ImportError:
    from tsenta_config import default_config
    from tsenta_feed import (
        fetch_feed, jobs_to_urls, load_feed, load_urls, new_feed_jobs,
        save_feed,
    )
    from tsenta_pipeline import (
        create_job, default_store_path, job_report, job_status, jobs_summary,
        list_jobs, review_approve, review_reject, run_job,
    )
    from tsenta_profiles import profile_from_json
    from tsenta_resume import resume_import, resume_import_to_file
    from tsenta_linkedin import (
        linkedin_guest_search, linkedin_guest_detail, linkedin_resolve_apply_url,
    )

_DEFAULT_PROFILE = os.path.join(os.path.dirname(default_store_path()), "profile.json")


def _load_profile(path: str | None) -> dict:
    """Load a candidate profile from a JSON file (default loot/state/profile.json)."""
    path = path or _DEFAULT_PROFILE
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {}


def quick_apply(url: str, profile: dict, config: dict | None = None,
                approve: bool = False, answerer=None, resume_path: str | None = None,
                store_path: str | None = None, _page_provider=None,
                stealth: bool = True) -> str:
    """One-shot apply: create job -> run (stops at review) -> approve if asked.

    Args:
        url: job/apply URL.
        profile: candidate profile dict.
        config: apply config dict (defaults).
        approve: explicit confirmation; when True the job is submitted for real
            through review_approve().
        answerer: answerer callable (defaults to the LLM answerer).
        resume_path: local resume file for file inputs.
        store_path: pipeline store path.
        _page_provider: test hook.

    Returns:
        str: JSON of {"ok", "applicationId", "status", "submitted", "error"}.
        Never raises.
    """
    try:
        created = json.loads(create_job(url, profile, config,
                                        store_path=store_path))
        if not created.get("ok"):
            return json.dumps(created)
        job_id = created["applicationId"]
        ran = json.loads(run_job(job_id, profile, config, confirmed=False,
                                 answerer=answerer, resume_path=resume_path,
                                 store_path=store_path, _page_provider=_page_provider,
                                 stealth=stealth))
        if approve and ran.get("status") == "review":
            approved = json.loads(review_approve(job_id, profile,
                                                 answerer=answerer,
                                                 resume_path=resume_path,
                                                 store_path=store_path,
                                                 _page_provider=_page_provider,
                                                 stealth=stealth))
            return json.dumps(approved)
        return json.dumps(ran)
    except Exception as exc:
        return json.dumps({"ok": False, "status": "failed",
                           "submitted": False,
                           "error": str(exc) or "quick-apply-failed"})


def sweep_jobs(feed, profile: dict, config: dict | None = None,
               approve: bool = False, limit: int = 0, answerer=None,
               resume_path: str | None = None, store_path: str | None = None,
               _page_provider=None, stealth: bool = True) -> str:
    """Run quick-apply over a feed of jobs.

    Args:
        feed: list of feed entries {url, ...} OR a path to a feed JSON / urls
            file. Feed entries already tracked in the store are skipped.
        profile: candidate profile dict.
        config: apply config dict (defaults).
        approve: explicit confirmation enabling real submission.
        limit: max jobs to process (0 = all).
        answerer: answerer callable (defaults to the LLM answerer).
        resume_path: local resume file for file inputs.
        store_path: pipeline store path.
        _page_provider: test hook.

    Returns:
        str: JSON of {"ok", "total", "new", "skipped", "applied", "reviewed",
        "failed", "errors", "results": [{url, applicationId, status,
        submitted, error}]}. Never raises.
    """
    summary = {"ok": True, "total": 0, "new": 0, "skipped": 0, "applied": 0,
               "reviewed": 0, "failed": 0, "errors": [], "results": []}
    try:
        if isinstance(feed, str) and os.path.exists(feed):
            try:
                feed = load_feed(feed)
            except Exception:
                feed = load_urls(feed)
        if not isinstance(feed, list):
            return json.dumps({**summary, "ok": False, "error": "invalid-feed"})
        fresh = new_feed_jobs(feed, store_path)
        urls = jobs_to_urls(fresh)
        tracked_skipped = max(0, len(feed) - len(fresh))
        limit_skipped = 0
        if limit and limit > 0:
            limit_skipped = max(0, len(urls) - limit)
            urls = urls[:limit]
        summary["total"] = len(urls)
        summary["skipped"] = tracked_skipped + limit_skipped
        for url in urls:
            result = json.loads(quick_apply(url, profile, config, approve=approve,
                                            answerer=answerer,
                                            resume_path=resume_path,
                                            store_path=store_path,
                                            _page_provider=_page_provider,
                                            stealth=stealth))
            status = result.get("status")
            summary["results"].append({
                "url": url,
                "applicationId": result.get("applicationId"),
                "status": status,
                "submitted": bool(result.get("submitted")),
                "error": result.get("error"),
            })
            summary["new"] += 1
            if status == "applied":
                summary["applied"] += 1
            elif status == "review":
                summary["reviewed"] += 1
            elif status == "failed":
                summary["failed"] += 1
                if result.get("error"):
                    summary["errors"].append(url)
    except Exception as exc:
        summary["ok"] = False
        summary["error"] = str(exc) or "sweep-failed"
    return json.dumps(summary)


def _add_shared_args(parser) -> None:
    parser.add_argument("--profile", default=None,
                        help="candidate profile JSON (default loot/state/profile.json)")
    parser.add_argument("--store", default=None,
                        help="pipeline store path (default loot/state/applications.json)")
    parser.add_argument("--resume", default=None, help="resume file for uploads")
    parser.add_argument("--no-stealth", dest="stealth", action="store_false",
                        help="disable anti-bot stealth patches")
    parser.set_defaults(stealth=True)


def _cmd_feed(args) -> int:
    jobs = fetch_feed(args.source, limit=args.limit)
    if not jobs:
        print(json.dumps({"ok": False, "error": "fetch-failed", "source": args.source}))
        return 1
    if args.save:
        print(save_feed(jobs))
    else:
        print(json.dumps({"ok": True, "count": len(jobs),
                          "jobs": jobs[: args.show]}))
    return 0


def _cmd_quick(args) -> int:
    profile = _load_profile(args.profile)
    if not profile:
        print(json.dumps({"ok": False, "error": "profile-not-found",
                          "hint": _DEFAULT_PROFILE}))
        return 1
    result = quick_apply(args.url, profile, approve=args.approve,
                         resume_path=args.resume, store_path=args.store,
                         stealth=args.stealth)
    print(result)
    return 0 if json.loads(result).get("ok") else 1


def _cmd_sweep(args) -> int:
    profile = _load_profile(args.profile)
    if not profile:
        print(json.dumps({"ok": False, "error": "profile-not-found",
                          "hint": _DEFAULT_PROFILE}))
        return 1
    result = sweep_jobs(args.feed, profile, approve=args.approve,
                        limit=args.limit, resume_path=args.resume,
                        store_path=args.store, stealth=args.stealth)
    print(result)
    return 0 if json.loads(result).get("ok") else 1


def _cmd_import_resume(args) -> int:
    if args.output:
        result = resume_import_to_file(args.pdf, args.output)
    else:
        result = resume_import(args.pdf)
    print(result)
    return 0 if json.loads(result).get("ok") else 1


def _cmd_ln_harvest(args) -> int:
    result = linkedin_guest_search(args.keywords, args.location or "",
                                   pages=args.pages, delay=args.delay)
    parsed = json.loads(result)
    if not parsed.get("ok"):
        print(result)
        return 1
    cards = parsed.get("cards", [])
    if args.detail:
        for i, card in enumerate(cards[:args.detail]):
            try:
                detail = json.loads(linkedin_guest_detail(card["jobId"]))
                if detail.get("ok"):
                    card.update(detail.get("job", {}))
            except Exception:
                pass
            cards[i] = card
    print(json.dumps({"ok": True, "count": len(cards), "cards": cards}))
    return 0


def _cmd_ln_resolve(args) -> int:
    job_id = args.job_id
    if "/jobs/view/" in job_id or "currentJobId=" in job_id:
        from tsenta_linkedin import linkedin_resolve_from_url
        result = linkedin_resolve_from_url(job_id, cookies=args.cookies)
    else:
        result = linkedin_resolve_apply_url(job_id, cookies=args.cookies)
    print(result)
    return 0 if json.loads(result).get("ok") else 1


def main(argv=None) -> int:
    """CLI entrypoint. Returns the process exit code."""
    parser = argparse.ArgumentParser(
        prog="tsenta_cli",
        description="TsentaClone job-application automation tool family.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_feed = sub.add_parser("feed", help="fetch a job feed")
    p_feed.add_argument("source", help="greenhouse:<token> | lever:<company> | urls:<path>")
    p_feed.add_argument("--limit", type=int, default=100)
    p_feed.add_argument("--show", type=int, default=10)
    p_feed.add_argument("--save", action="store_true", help="persist feed to loot/state/feed.json")
    p_feed.set_defaults(func=_cmd_feed)

    p_quick = sub.add_parser("quick", help="one-shot apply (stops at review without --approve)")
    p_quick.add_argument("url")
    p_quick.add_argument("--approve", action="store_true",
                         help="EXPLICIT confirmation: submit for real")
    _add_shared_args(p_quick)
    p_quick.set_defaults(func=_cmd_quick)

    p_sweep = sub.add_parser("sweep", help="run quick-apply over a feed")
    p_sweep.add_argument("feed", help="feed JSON or urls file (skips already-tracked)")
    p_sweep.add_argument("--approve", action="store_true",
                         help="EXPLICIT confirmation: submit for real")
    p_sweep.add_argument("--limit", type=int, default=0)
    _add_shared_args(p_sweep)
    p_sweep.set_defaults(func=_cmd_sweep)

    p_run = sub.add_parser("run", help="run an existing job")
    p_run.add_argument("id")
    p_run.add_argument("--confirmed", action="store_true")
    _add_shared_args(p_run)
    p_run.set_defaults(func=lambda a: _echo(run_job(
        a.id, _load_profile(a.profile), confirmed=a.confirmed,
        resume_path=a.resume, store_path=a.store)))

    p_approve = sub.add_parser("approve", help="submit a reviewed job for real")
    p_approve.add_argument("id")
    _add_shared_args(p_approve)
    p_approve.set_defaults(func=lambda a: _echo(review_approve(
        a.id, _load_profile(a.profile), resume_path=a.resume,
        store_path=a.store)))

    def _with_store(func):
        def run(args):
            return _echo(func(args.id, args.store))
        return run

    p_reject = sub.add_parser("reject", help="pause a reviewed job")
    p_reject.add_argument("id")
    p_reject.add_argument("--store", default=None)
    p_reject.set_defaults(func=_with_store(review_reject))

    p_status = sub.add_parser("status", help="job status")
    p_status.add_argument("id")
    p_status.add_argument("--store", default=None)
    p_status.set_defaults(func=_with_store(job_status))

    p_report = sub.add_parser("report", help="full job record incl. trace")
    p_report.add_argument("id")
    p_report.add_argument("--store", default=None)
    p_report.set_defaults(func=_with_store(job_report))

    p_list = sub.add_parser("list", help="list jobs")
    p_list.add_argument("--store", default=None)
    p_list.set_defaults(func=lambda a: _echo(list_jobs(a.store)))

    p_summary = sub.add_parser("summary", help="per-status counts")
    p_summary.add_argument("--store", default=None)
    p_summary.set_defaults(func=lambda a: _echo(jobs_summary(a.store)))

    p_import = sub.add_parser("import-resume", help="import a PDF resume to profile JSON")
    p_import.add_argument("pdf", help="path to the PDF resume file")
    p_import.add_argument("--output", default=None,
                          help="output path for the profile JSON (default loot/state/profile.json)")
    p_import.set_defaults(func=_cmd_import_resume)

    p_ln_harvest = sub.add_parser("ln-harvest", help="LinkedIn guest-mode job search")
    p_ln_harvest.add_argument("keywords")
    p_ln_harvest.add_argument("location", nargs="?", default="")
    p_ln_harvest.add_argument("--pages", type=int, default=1)
    p_ln_harvest.add_argument("--detail", type=int, default=0,
                              help="enrich first N cards with detail page")
    p_ln_harvest.add_argument("--delay", type=float, default=2.0)
    p_ln_harvest.set_defaults(func=_cmd_ln_harvest)

    p_ln_resolve = sub.add_parser("ln-resolve", help="resolve a LinkedIn job to its apply URL")
    p_ln_resolve.add_argument("job_id", help="LinkedIn job id or full URL")
    p_ln_resolve.add_argument("--cookies", default=None, help="li_at=...; JSESSIONID=...")
    p_ln_resolve.set_defaults(func=_cmd_ln_resolve)

    args = parser.parse_args(argv)
    return args.func(args)


def _echo(text: str) -> int:
    print(text)
    try:
        return 0 if json.loads(text).get("ok", True) else 1
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
