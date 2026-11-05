#!/usr/bin/env python3
"""Regenerate data.json for the Corner to Super site.

Reads the game repo (read only: `git log`, docs/PROGRESS.md, docs/ECONOMY.md and data/*.json)
and merges in the hand-written events in manual.json. Run it after more work lands in the game
repo, then commit and push data.json.

    python3 update.py [--game ~/Code/corner-to-super] [--out data.json]
"""

import argparse
import json
import re
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEST_LINE = re.compile(r"(\d[\d,]*) passed, (\d+) failed")


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


def commits(repo):
    out = git(repo, "log", "main", "--reverse", "--format=%h%x1f%aI%x1f%s")
    rows = []
    for line in out.splitlines():
        sha, date, subject = line.split("\x1f", 2)
        rows.append({"sha": sha, "date": date, "subject": subject})
    return rows


def per_hour(rows):
    """Commits per clock hour (author time, the repo's own UTC offset)."""
    counts = Counter(r["date"][:13] for r in rows)
    first = datetime.fromisoformat(rows[0]["date"]).replace(minute=0, second=0)
    last = datetime.fromisoformat(rows[-1]["date"]).replace(minute=0, second=0)
    hours = []
    t = first
    while t <= last:
        key = t.isoformat()[:13]
        hours.append({"hour": t.isoformat(), "commits": counts.get(key, 0)})
        t = datetime.fromtimestamp(t.timestamp() + 3600, t.tzinfo)
    return hours


def progress_history(repo):
    """Walk every commit that touched PROGRESS.md (oldest first) and record, by commit time,
    when each `## ` section heading and each full-suite "N passed, M failed" line first appeared."""
    out = git(
        repo, "log", "main", "--reverse", "-p", "--format=@@COMMIT %h %cI", "--", "docs/PROGRESS.md"
    )
    headings, points = {}, []
    seen = set()
    sha = date = None
    for line in out.splitlines():
        if line.startswith("@@COMMIT "):
            _, sha, date = line.split(" ", 2)
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        text = line[1:]
        if text.startswith("## "):
            headings.setdefault(text[3:].strip(), {"date": date, "sha": sha})
        m = TEST_LINE.search(text)
        if m:
            passed, failed = int(m.group(1).replace(",", "")), int(m.group(2))
            if (passed, failed) not in seen:
                seen.add((passed, failed))
                points.append({
                    "date": date, "passed": passed, "failed": failed,
                    "source": f"PROGRESS.md ({sha})", "note": text.strip(" -*`")[:140],
                })
    return headings, points


def progress_sections(repo):
    """Split the current PROGRESS.md into `## ` sections; pull out each one's deferred checks."""
    text = (repo / "docs/PROGRESS.md").read_text()
    sections = []
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        title, _, body = block.partition("\n")
        deferred, collecting = [], False
        for line in body.splitlines():
            if line.startswith("**Deferred"):
                collecting = True
                # Text after the bold label, minus a "(windowed...)" note in the label itself.
                rest = re.sub(r"^\([^)]*\)", "", line.split("**", 2)[-1].strip(": ")).strip(": ")
                if rest:
                    deferred.append(rest)
                continue
            if not collecting:
                continue
            if line.startswith("**") or (not line.strip() and deferred):
                collecting = False
            elif re.match(r"^(\d+\.|-) ", line):
                deferred.append(re.sub(r"^(\d+\.|-) ", "", line))
            elif line.strip() and deferred:
                deferred[-1] += " " + line.strip()
        deferred = [d for d in deferred if not d.startswith("~~")]
        sections.append({"title": title.strip(), "deferred": deferred})
    return sections


def table_after(md, heading):
    """Rows of the first markdown table under `heading`."""
    part = md.split(heading, 1)[1]
    block = []
    for l in part.splitlines()[1:]:
        if l.startswith("|"):
            block.append(l)
        elif block:
            break
    cells = [[c.strip() for c in l.strip("|").split("|")] for l in block]
    return [c for c in cells if not set("".join(c)) <= set("-: ")]


def economy(repo):
    data = repo / "data"
    licences = json.loads((data / "licences.json").read_text())
    exp = json.loads((data / "expansions.json").read_text())
    settings = json.loads((data / "settings.json").read_text())
    md = (repo / "docs/ECONOMY.md").read_text()
    return {
        "start_cash": settings["start"]["money"] / 100,
        "start_rent": exp["start"]["rent"] / 100,
        "licences": [
            {"name": l["name"], "level": l["level"], "price": l["price"] / 100,
             "needs": l.get("requires_expansion", "").upper()}
            for l in licences
        ],
        "expansions": [
            {"id": e["id"].upper(), "name": e["name"], "level": e["level"],
             "price": e["price"] / 100, "rent_after": e["rent_after"] / 100}
            for e in exp["main"]
        ],
        "stockroom": [
            {"id": e["id"].upper(), "name": e["name"], "level": e["level"],
             "price": e["price"] / 100, "rent_add": e["rent_add"] / 100}
            for e in exp["stockroom"]
        ],
        "pacing": table_after(md, "## Pacing targets"),
    }


def counts(repo, rows, latest):
    def files(pattern, root="."):
        return [p for p in (repo / root).rglob(pattern) if ".godot" not in p.parts]

    gd = files("*.gd", "scripts") + files("*.gd", "tests")
    data = repo / "data"
    return {
        "commits": len(rows),
        "first_commit": rows[0]["date"],
        "last_commit": rows[-1]["date"],
        "products": len(json.loads((data / "products.json").read_text())),
        "licences": len(json.loads((data / "licences.json").read_text())),
        "fixtures": len(json.loads((data / "fixtures.json").read_text())),
        "levels": json.loads((data / "levels.json").read_text())["max_level"],
        "test_files": len(files("test_*.gd", "tests/cases")) or len(files("*.gd", "tests/cases")),
        "gd_files": len(gd),
        "gd_lines": sum(len(p.read_text(errors="ignore").splitlines()) for p in gd),
        "models": len(files("*.glb", "assets")),
        "music_tracks": len(files("*.ogg", "audio/music")),
        "sounds": len(files("*.ogg", "audio")) + len(files("*.wav", "audio")),
        "tests_passing": latest["passed"] if latest else None,
    }


def unmerged_branches(repo):
    out = git(repo, "branch", "--no-merged", "main", "--format=%(refname:short)")
    return [b for b in out.split() if b]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--game", default=str(Path.home() / "Code/corner-to-super"))
    ap.add_argument("--out", default=str(HERE / "data.json"))
    args = ap.parse_args()
    repo = Path(args.game).expanduser()
    manual = json.loads((HERE / "manual.json").read_text())

    rows = commits(repo)
    headings, points = progress_history(repo)
    # Keep only runs PROGRESS.md still reports; lines an agent later rewrote were superseded.
    current = {(int(a.replace(",", "")), int(b)) for a, b in
               TEST_LINE.findall((repo / "docs/PROGRESS.md").read_text())}
    points = [p for p in points if (p["passed"], p["failed"]) in current]
    known = {(p["passed"], p["failed"]) for p in points}
    points += [p for p in manual["test_points"] if (p["passed"], p["failed"]) not in known]
    points.sort(key=lambda p: datetime.fromisoformat(p["date"]))

    # Hand-written events, plus one event for every current PROGRESS section no manual event
    # covers, so new milestone notes (M9, the second additions batch, later review rounds) show up.
    sections = progress_sections(repo)
    events = list(manual["events"])
    covered = {e.get("progress") for e in events}
    for sec in sections:
        info = headings.get(sec["title"])
        if info and sec["title"] not in covered:
            events.append({
                "date": info["date"], "kind": "milestone", "title": sec["title"],
                "text": f"New section in PROGRESS.md ({info['sha']}).", "progress": sec["title"],
            })
    events.sort(key=lambda e: datetime.fromisoformat(e["date"]))

    passing = [p for p in points if p["failed"] == 0]
    out = {
        "generated": datetime.now().astimezone().isoformat(timespec="minutes"),
        "head": rows[-1]["sha"],
        "stats": counts(repo, rows, passing[-1] if passing else None),
        "test_points": points,
        "events": events,
        "commits": rows,
        "commits_per_hour": per_hour(rows),
        "sections": progress_sections(repo),
        "economy": economy(repo),
        "in_progress": manual["in_progress"],
        "unmerged_branches": unmerged_branches(repo),
    }
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    s = out["stats"]
    print(f"wrote {args.out}: {s['commits']} commits, {len(events)} events, "
          f"{len(points)} test runs, latest passing {s['tests_passing']}")


if __name__ == "__main__":
    main()
