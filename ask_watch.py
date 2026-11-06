#!/usr/bin/env python3
"""Answer questions typed into the live page's question box.

The box opens a GitHub issue labelled `question`. This watcher (run 24/7 by launchd) checks for
open ones once a minute. Only when there is one does it start an answering agent (`omp -p`,
read-only tools, no game engine); the answer goes back as an issue comment, the issue is closed,
and the Q&A is added to live.json so the page shows it. Questions are also copied to
`inbox.jsonl` so the agent running the main loop sees them between steps.

Only issues opened by OWNER are answered, so strangers can't start agent runs.
"""

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = "SubToFeralsloth11/corner-to-super-site"
OWNER = "SubToFeralsloth11"
GAME = Path.home() / "Code/corner-to-super"
INBOX = HERE / "inbox.jsonl"
POLL_S = 60
ANSWER_TIMEOUT_S = 900

PROMPT = """You are answering a question the project owner typed into the live status page of
Corner to Super (a Godot 4.7 supermarket-simulator game in {game}). Another agent is running a
non-stop "critique then fix" loop on the game; its live state is in {live} (status, rounds,
findings, activity log, test runs, game commits) and the game's docs are in {game}/docs.

Rules: READ ONLY. Never edit files, never run git write commands, never launch Godot, Blender, a
browser or any test (the machine has 8 GB and another agent owns the engine). Read files and
run cheap read-only shell commands only. Answer in plain Markdown, short and direct, with
evidence (file paths, finding IDs, commit hashes) where it helps. If the question is an
instruction for the loop agent rather than a question, say it has been passed to the loop's
inbox and briefly say what you expect it to do.

Question #{num}: {title}

{body}
"""


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def gh(*args, inp=None):
    return subprocess.run(["gh", *args], input=inp, capture_output=True, text=True,
                          timeout=60).stdout


def log(msg):
    print(f"{now()} {msg}", flush=True)


def open_questions():
    out = gh("issue", "list", "-R", REPO, "--label", "question", "--state", "open",
             "--json", "number,title,body,author,createdAt", "--limit", "20")
    try:
        items = json.loads(out or "[]")
    except json.JSONDecodeError:
        return []
    return sorted((i for i in items if i["author"]["login"] == OWNER),
                  key=lambda i: i["number"])


def live(*args):
    subprocess.run([sys.executable, str(HERE / "live.py"), *args], cwd=HERE,
                   capture_output=True, text=True, timeout=180)


def status_digest():
    """What the loop is doing, the latest fixes and what is still open, from live.json."""
    try:
        d = json.loads((HERE / "live.json").read_text())
    except (OSError, json.JSONDecodeError):
        return "(live.json unreadable)"
    s = d.get("status", {})
    lines = [f"**Now:** {s.get('state', '?')}: {s.get('activity', '')} (round {s.get('round', '?')})", ""]
    fixed, open_ = [], []
    for r in d.get("rounds", []):
        for f in r.get("findings", []):
            row = f"{r['id']}/{f['id']} [{f['sev']}] {f['title']}"
            (fixed if f.get("status") == "fixed" else open_ if f.get("status") in ("open", "wip") else []).append(
                (f.get("closed") or f.get("found") or "", row + (f" ({f['commit']})" if f.get("commit") else "")))
    fixed.sort(reverse=True)
    lines.append(f"**Fixed so far:** {len(fixed)}. Latest:")
    lines += [f"- {row}" for _, row in fixed[:15]]
    lines.append("")
    lines.append(f"**Still open:** {len(open_)}. Highest first:")
    lines += [f"- {row}" for _, row in sorted(open_, key=lambda x: x[1].split('[')[1])[:15]]
    t = d.get("tests", [])
    if t:
        lines += ["", f"**Last test run:** {t[-1]['passed']} passed, {t[-1]['failed']} failed ({t[-1].get('note', '')})"]
    lines += ["", "Full detail: https://subtoferalsloth11.github.io/corner-to-super-site/live.html"]
    return "\n".join(lines)


def answer(q):
    num, title, body = q["number"], q["title"], (q["body"] or "").strip()
    log(f"question #{num}: {title}")
    with INBOX.open("a") as f:
        f.write(json.dumps({"t": now(), "num": num, "title": title, "body": body}) + "\n")
    gh("issue", "comment", str(num), "-R", REPO, "--body",
       "Got it. An agent is reading the project to answer this; it usually takes a few minutes.")
    live("qa", str(num), title, "--question", body, "--state", "answering", "--push")

    prompt = PROMPT.format(game=GAME, live=HERE / "live.json", num=num, title=title, body=body)
    try:
        r = subprocess.run(
            ["omp", "-p", "--no-session", "--no-title", "--thinking", "low",
             "--approval-mode", "yolo", "--tools", "read,grep,glob,find,bash",
             "--cwd", str(GAME), "--add-dir", str(HERE), prompt],
            capture_output=True, text=True, timeout=ANSWER_TIMEOUT_S)
        text = r.stdout.strip()
        failed = r.returncode != 0 or not text or "rate_limit_error" in text or text.startswith("Working...")
    except subprocess.TimeoutExpired:
        text, failed = "", True
    if failed:
        # No agent available (rate limit, timeout): answer from the live log instead of leaving
        # the question with an error.
        text = ("The answering agent isn't available right now (API limit), so here is the "
                "current state straight from the live log:\n\n" + status_digest())

    gh("issue", "comment", str(num), "-R", REPO, "--body-file", "-", inp=text)
    gh("issue", "close", str(num), "-R", REPO)
    live("qa", str(num), title, "--question", body, "--answer", text, "--state", "answered",
         "--push")
    log(f"answered #{num}")


def main():
    log("ask_watch started")
    while True:
        try:
            for q in open_questions():
                answer(q)
        except Exception as e:  # keep the 24/7 loop alive through network blips
            log(f"error: {e!r}")
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
