#!/usr/bin/env python3
"""
runstats.py — health, cost and backlog trend from the two run logs.

Reads runs.jsonl (the Plaud sync watcher) and planner-runs.jsonl (planner runs and
email/voice command runs). Both are git-ignored, so this only produces numbers on the
service host; elsewhere it says so rather than reporting an empty history as healthy.

Replaces the ad-hoc python one-liners that /sync-health used to inline, and recomputes
the cost baseline instead of quoting a figure from a doc (the last quoted one went stale
by 3x before anyone noticed).

Usage:
    runstats.py [--days N] [--json] [--repo PATH]
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

REPO_DEFAULT = os.environ.get("WORKDIR", "/home/robert/plaud-sync")


def load(path):
    """Read a JSON Lines file, skipping unparseable lines rather than dying on one."""
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return None
    return rows


def is_service_host():
    """True when the plaud-sync unit exists and is active here."""
    try:
        out = subprocess.run(["systemctl", "is-active", "plaud-sync"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() == "active"
    except (OSError, subprocess.SubprocessError):
        return False


def parse_time(row):
    try:
        return datetime.fromisoformat((row.get("time") or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def money(values):
    # Skip None *and* 0.0: a run whose cost is zero is one whose result envelope never
    # parsed (usually a timeout), not a run that was free. Averaging those in understates
    # the real cost per run by ~12%, and this is the number everything else compares to.
    vals = [v for v in values if isinstance(v, (int, float)) and v > 0]
    if not vals:
        return {}
    return {
        "n": len(vals),
        "mean": round(statistics.mean(vals), 3),
        "median": round(statistics.median(vals), 3),
        "total": round(sum(vals), 2),
        "max": round(max(vals), 3),
    }


def sync_stats(rows, since):
    recent = [r for r in rows if (parse_time(r) or datetime.min.replace(tzinfo=timezone.utc)) >= since]
    # A uid can appear twice (the one automatic retry). Judge outcome per uid, not per record.
    by_uid = defaultdict(list)
    for r in rows:
        by_uid[r.get("uid")].append(r)
    unsynced = sorted(
        uid for uid, rs in by_uid.items() if not any(r.get("ok") for r in rs)
    )
    return {
        "records": len(rows),
        "recordings": len(by_uid),
        "ok_records": sum(1 for r in rows if r.get("ok")),
        "unsynced_uids": unsynced,
        "cost_all": money(r.get("cost_usd") for r in rows),
        "cost_last10": money(r.get("cost_usd") for r in rows[-10:]),
        "cost_window": money(r.get("cost_usd") for r in recent),
        "duration_s_all": round(
            statistics.mean([r["duration_ms"] / 1000 for r in rows
                             if isinstance(r.get("duration_ms"), (int, float))]), 1)
        if any(isinstance(r.get("duration_ms"), (int, float)) for r in rows) else None,
        "first": (rows[0].get("time") or "")[:10] if rows else None,
        "last": (rows[-1].get("time") or "")[:10] if rows else None,
    }


def planner_stats(rows, since):
    kinds = Counter(r.get("kind") for r in rows)
    plans = [r for r in rows if r.get("kind") == "plan"]
    cmds = [r for r in rows if r.get("kind") == "command"]
    trend = []
    for r in plans[-14:]:
        t = ((r.get("report") or {}) or {}).get("tasks") or {}
        trend.append({
            "time": (r.get("time") or "")[:16],
            "mode": r.get("mode"),
            "open": t.get("open"), "overdue": t.get("overdue"), "inbox": t.get("inbox"),
            "created": t.get("created"), "completed": t.get("completed"),
            "cost": r.get("cost_usd"),
        })
    return {
        "kinds": dict(kinds),
        "ok": sum(1 for r in rows if r.get("ok")),
        "failed": [f"{(r.get('time') or '')[:16]} {r.get('kind')} {r.get('mode') or r.get('channel')}"
                   for r in rows if not r.get("ok")],
        "cost_plan": money(r.get("cost_usd") for r in plans),
        "cost_command": money(r.get("cost_usd") for r in cmds),
        "trend": trend,
    }


def daily_burn(sync_rows, planner_rows, days):
    per_day = defaultdict(float)
    for r in list(sync_rows) + list(planner_rows):
        c = r.get("cost_usd")
        if isinstance(c, (int, float)):
            per_day[(r.get("time") or "")[:10]] += c
    recent = sorted(per_day)[-days:]
    return {
        "days": {d: round(per_day[d], 2) for d in recent},
        "mean": round(sum(per_day[d] for d in recent) / len(recent), 2) if recent else None,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=7, help="window for the burn rate (default 7)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--repo", default=REPO_DEFAULT)
    args = ap.parse_args()

    sync = load(os.path.join(args.repo, "runs.jsonl"))
    plan = load(os.path.join(args.repo, "planner-runs.jsonl"))

    if sync is None and plan is None:
        host = os.uname().nodename
        msg = (f"No run logs on this machine ({host}).\n"
               "runs.jsonl and planner-runs.jsonl are git-ignored and exist only on the service "
               "host — bg-pc, whose hostname is lark-server. Cost and health cannot be computed "
               "here; prompt edits and drift checks work fine on any clone.")
        print(json.dumps({"error": "no-run-logs", "host": host}) if args.json else msg)
        return 2

    sync, plan = sync or [], plan or []
    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    out = {
        "host": os.uname().nodename,
        "is_service_host": is_service_host(),
        "window_days": args.days,
        "sync": sync_stats(sync, since) if sync else None,
        "planner": planner_stats(plan, since) if plan else None,
        "burn": daily_burn(sync, plan, args.days),
    }

    if args.json:
        print(json.dumps(out, indent=2))
        return 0

    s, p = out["sync"], out["planner"]
    print(f"host {out['host']}  service-host={out['is_service_host']}")
    if s:
        rate = 100 * s["ok_records"] / s["records"] if s["records"] else 0
        print(f"\nSYNC  {s['records']} runs over {s['recordings']} recordings "
              f"({s['first']} → {s['last']}), {rate:.0f}% of runs ok")
        for label, key in (("all", "cost_all"), ("last 10", "cost_last10"),
                           (f"last {args.days}d", "cost_window")):
            c = s[key]
            if c:
                print(f"  cost {label:>8}: mean ${c['mean']:.2f}  median ${c['median']:.2f}  "
                      f"max ${c['max']:.2f}  total ${c['total']:.2f}  (n={c['n']})")
        if s["duration_s_all"]:
            print(f"  mean duration: {s['duration_s_all']:.0f}s")
        if s["unsynced_uids"]:
            print(f"  !! NEVER SYNCED (need /replay-note): uid " +
                  ", ".join(str(u) for u in s["unsynced_uids"]))
        else:
            print("  every recording synced on some attempt")
    if p:
        print(f"\nPLANNER  {p['kinds']}  ok={p['ok']}")
        for label, key in (("plan", "cost_plan"), ("command", "cost_command")):
            c = p[key]
            if c:
                print(f"  cost {label:>7}: mean ${c['mean']:.2f}  total ${c['total']:.2f} (n={c['n']})")
        if p["failed"]:
            print("  failed runs: " + "; ".join(p["failed"]))
        if p["trend"]:
            print("\n  backlog trend (open / overdue / inbox, +created -completed):")
            for t in p["trend"]:
                print(f"    {t['time']} {(t['mode'] or ''):8} open={t['open']:<4} "
                      f"overdue={t['overdue']:<3} inbox={t['inbox']:<3} "
                      f"+{t['created']} -{t['completed']}  ${t['cost'] or 0:.2f}")
            first, last = p["trend"][0], p["trend"][-1]
            if isinstance(first["open"], int) and isinstance(last["open"], int):
                delta = last["open"] - first["open"]
                print(f"    → open {first['open']} → {last['open']} ({delta:+d}) over "
                      f"{len(p['trend'])} runs")

    b = out["burn"]
    if b["mean"] is not None:
        print(f"\nBURN  last {args.days} days, ${b['mean']:.2f}/day")
        for d, v in b["days"].items():
            print(f"    {d}  ${v:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
