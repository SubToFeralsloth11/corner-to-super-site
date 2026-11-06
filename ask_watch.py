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
        text = r.stdout.strip() or ("The answering agent failed:\n```\n" + r.stderr[-1500:] + "\n```")
    except subprocess.TimeoutExpired:
        text = "The answering agent ran out of time. Ask again, or ask something narrower."

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
