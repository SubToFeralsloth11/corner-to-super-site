#!/usr/bin/env python3
"""Record the live critique-and-fix loop into live.json and publish it.

Every action the agent takes is one CLI call; `--push` (or the `push` command) also refreshes
data.json, snapshots the machine and the game repo, commits and pushes, so the live page shows it.

  live.py status --state reviewing --round R2 --area "Checkout" --activity "Critics reading code"
  live.py round R2 "Checkout, payment, change, till"
  live.py finding R2 C1 P1 "Change is rounded twice" --file scripts/core/payment.gd:40 --detail "..."
  live.py fix R2 C1 --commit abc1234 [--status fixed|wontfix|dup] [--note "..."]
  live.py test 930 0 --note "full suite"
  live.py agent CritCheckout running "Reviewing checkout"
  live.py log "Started baseline test run" --kind action
  live.py push
"""

import argparse
import fcntl
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIVE = HERE / "live.json"
GAME = Path.home() / "Code/corner-to-super"
MAX_LOG = 2000


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load():
    if LIVE.exists():
        return json.loads(LIVE.read_text())
    return {"status": {}, "rounds": [], "log": [], "tests": [], "agents": {}, "machine": {},
            "game": {}}


def save(d):
    d["updated"] = now()
    d["log"] = d["log"][-MAX_LOG:]
    LIVE.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n")


def log(d, msg, kind="action"):
    d["log"].append({"t": now(), "kind": kind, "msg": msg})


def find_round(d, rid):
    for r in d["rounds"]:
        if r["id"] == rid:
            return r
    raise SystemExit(f"no round {rid}")


def sh(*cmd, cwd=None):
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def machine():
    free = re.search(r"free percentage: (\d+)%", sh("memory_pressure"))
    load_avg = sh("sysctl", "-n", "vm.loadavg").strip("{} \n").split()
    godot = [l for l in sh("pgrep", "-lf", "godot").splitlines() if "pgrep" not in l]
    return {
        "t": now(),
        "mem_free_pct": int(free.group(1)) if free else None,
        "load": [float(x) for x in load_avg[:3]] if load_avg else [],
        "godot_procs": len(godot),
    }


def game_snapshot():
    out = sh("git", "-C", str(GAME), "log", "main", "-60", "--format=%h%x1f%aI%x1f%s%x1f%b%x1e")
    commits = []
    for rec in out.split("\x1e"):
        parts = rec.strip("\n").split("\x1f")
        if len(parts) >= 3:
            sha, date, subj = parts[:3]
            stat = sh("git", "-C", str(GAME), "show", "--shortstat", "--format=", sha).strip()
            commits.append({"sha": sha, "date": date, "subject": subj,
                            "body": parts[3].strip() if len(parts) > 3 else "", "stat": stat})
    dirty = sh("git", "-C", str(GAME), "status", "--short").splitlines()
    return {"commits": commits, "dirty": dirty,
            "total_commits": int(sh("git", "-C", str(GAME), "rev-list", "--count", "main") or 0)}


def push(d, msg):
    d["machine"] = machine()
    d["game"] = game_snapshot()
    save(d)
    sh("python3", str(HERE / "update.py"))
    sh("git", "add", "-A", cwd=HERE)
    sh("git", "commit", "-q", "-m", msg, cwd=HERE)
    for _ in range(3):
        r = subprocess.run(["git", "push", "-q", "origin", "main"], cwd=HERE,
                           capture_output=True, text=True)
        if r.returncode == 0:
            return
        sh("git", "pull", "-q", "--rebase", "origin", "main", cwd=HERE)
    raise SystemExit("push failed: " + r.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status")
    for k in ("state", "round", "area", "activity", "cycle"):
        s.add_argument("--" + k)

    r = sub.add_parser("round")
    r.add_argument("id"); r.add_argument("area")
    r.add_argument("--close", action="store_true")

    f = sub.add_parser("finding")
    f.add_argument("round"); f.add_argument("id"); f.add_argument("sev"); f.add_argument("title")
    f.add_argument("--file", default=""); f.add_argument("--detail", default="")
    f.add_argument("--by", default="")

    x = sub.add_parser("fix")
    x.add_argument("round"); x.add_argument("id")
    x.add_argument("--commit", default=""); x.add_argument("--status", default="fixed")
    x.add_argument("--note", default="")

    t = sub.add_parser("test")
    t.add_argument("passed", type=int); t.add_argument("failed", type=int)
    t.add_argument("--note", default="")

    a = sub.add_parser("agent")
    a.add_argument("name"); a.add_argument("state"); a.add_argument("task", nargs="?", default="")

    lg = sub.add_parser("log")
    lg.add_argument("msg"); lg.add_argument("--kind", default="action")

    q = sub.add_parser("qa")
    q.add_argument("num", type=int); q.add_argument("title")
    q.add_argument("--question", default=""); q.add_argument("--answer", default="")
    q.add_argument("--state", default="answering")

    sh_ = sub.add_parser("shots")
    sh_.add_argument("dir"); sh_.add_argument("--note", default="")

    sub.add_parser("push")
    # `--push` may come anywhere on the line, so pull it out before argparse sees the subcommand.
    argv = sys.argv[1:]
    want_push = "--push" in argv
    args = ap.parse_args([a for a in argv if a != "--push"])
    args.push = want_push
    # The loop agent and ask_watch.py both write live.json and push; serialize them.
    lock = open(HERE / ".live.lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX)
    d = load()
    d.setdefault("qa", [])

    if args.cmd == "status":
        for k in ("state", "round", "area", "activity", "cycle"):
            v = getattr(args, k)
            if v is not None:
                d["status"][k] = v
        d["status"]["since"] = now()
        log(d, f"Status: {d['status'].get('state', '')} - {d['status'].get('activity', '')}",
            "status")
    elif args.cmd == "round":
        if args.close:
            rd = find_round(d, args.id)
            rd["finished"] = now()
            log(d, f"Round {args.id} closed", "round")
        else:
            d["rounds"].append({"id": args.id, "area": args.area, "started": now(),
                                "finished": None, "findings": []})
            log(d, f"Round {args.id} started: {args.area}", "round")
    elif args.cmd == "finding":
        rd = find_round(d, args.round)
        rd["findings"] = [x for x in rd["findings"] if x["id"] != args.id]
        rd["findings"].append({"id": args.id, "sev": args.sev.upper(), "title": args.title,
                               "file": args.file, "detail": args.detail, "by": args.by,
                               "status": "open", "found": now(), "commit": "", "note": ""})
        log(d, f"{args.round}/{args.id} [{args.sev.upper()}] {args.title}", "finding")
    elif args.cmd == "fix":
        rd = find_round(d, args.round)
        for x in rd["findings"]:
            if x["id"] == args.id:
                x.update(status=args.status, commit=args.commit, note=args.note, closed=now())
                break
        else:
            raise SystemExit(f"no finding {args.id}")
        log(d, f"{args.round}/{args.id} {args.status} {args.commit} {args.note}".strip(), "fix")
    elif args.cmd == "test":
        d["tests"].append({"t": now(), "passed": args.passed, "failed": args.failed,
                           "note": args.note})
        log(d, f"Tests: {args.passed} passed, {args.failed} failed {args.note}".strip(), "test")
    elif args.cmd == "agent":
        d["agents"][args.name] = {"state": args.state, "task": args.task, "t": now()}
        log(d, f"Agent {args.name}: {args.state} {args.task}".strip(), "agent")

    elif args.cmd == "log":
        log(d, args.msg, args.kind)
    elif args.cmd == "qa":
        d["qa"] = [x for x in d["qa"] if x["num"] != args.num]
        d["qa"].append({"num": args.num, "title": args.title, "question": args.question,
                        "answer": args.answer, "state": args.state, "t": now()})
        log(d, f"Question #{args.num} {args.state}: {args.title}", "question")
    elif args.cmd == "shots":
        # In-game screenshots from a tour, shrunk to 960 px JPEGs (same names overwrite, so the
        # repo holds one set).
        out = HERE / "shots"
        out.mkdir(exist_ok=True)
        files = []
        for png in sorted(Path(args.dir).glob("*.png")):
            jpg = out / (png.stem + ".jpg")
            subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "70",
                            "-Z", "960", str(png), "--out", str(jpg)], capture_output=True)
            if jpg.exists():
                files.append(jpg.name)
        d["shots"] = {"t": now(), "note": args.note, "files": files}
        log(d, f"Screenshots refreshed: {len(files)} images {args.note}".strip(), "shots")

    if args.cmd == "push" or args.push:
        push(d, "Live: " + (d["log"][-1]["msg"][:60] if d["log"] else "update"))
    else:
        save(d)


if __name__ == "__main__":
    main()
