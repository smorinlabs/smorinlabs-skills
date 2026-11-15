"""Read project plans and local worktrees; never change repository state."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import re
import subprocess

from .state import digest, identity, now

STATE = {"x": "complete", " ": "open", "~": "in_progress", "-": "retired",
         ">": "redirected", "?": "unknown"}


def git(directory, *args):
    try:
        run = subprocess.run(["git", "--no-optional-locks", "-C", str(directory), *args],
                             capture_output=True, text=True, timeout=15,
                             env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
        return run.stdout.strip() if run.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def parse_plan(path, text):
    """Parse explicit numbered checklists without counting examples or phase headings."""
    phases = {}
    current = None
    fence = None
    for number, line in enumerate(text.splitlines(), 1):
        fenced = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fenced:
            marker = fenced[1]
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
            continue
        if fence:
            continue
        phase_match = re.search(r"\b(P\d+)(?![-\w])\s*[:—–-]?\s*(.*)", line)
        heading = line.lstrip().startswith("#")
        mark = re.search(r"\[([xX ~?\->])\]", line)
        if heading and phase_match:
            current = phase_match[1]
            title = phase_match[2].strip(" *`:-—") or current
            phases.setdefault(current, {"id": current, "title": title, "line": number,
                "state": STATE.get(mark[1].lower(), "unknown") if mark else "unknown",
                "tasks": [], "acceptance": []})
        task = re.match(r"^\s*(?:[-*+] |#{1,6} )\s*\[([xX ~?\->])\]\s*"
                        r"[\[*`]*(P\d+-(?:TS|T)\d+)\b(.*)", line)
        if task:
            phase_id = task[2].split("-")[0]
            phase = phases.setdefault(phase_id, {"id": phase_id, "title": phase_id,
                "state": "unknown", "line": number, "tasks": [], "acceptance": []})
            record = {"id": task[2], "state": STATE[task[1].lower()],
                      "title": task[3].strip(" *`]:—-"), "line": number, "source": str(path),
                      "kind": "test" if "-TS" in task[2] else "implementation"}
            previous = next((x for x in phase["tasks"] if x["id"] == record["id"]), None)
            if previous:
                previous.setdefault("duplicates", []).append(record)
                if previous["state"] != record["state"]:
                    previous["state"] = "conflict"
            else:
                phase["tasks"].append(record)
        elif current and re.match(r"^\s*[-*+] \[[xX ~?\->]\]", line):
            phases[current]["acceptance"].append({"text": line.strip(), "line": number})
    for phase in phases.values():
        phase["counts"] = {name: sum(t["state"] == name for t in phase["tasks"])
                           for name in (*STATE.values(), "conflict")}
        phase["counts"]["total"] = len(phase["tasks"])
        phase["counts"]["implementation"] = sum(t["kind"] == "implementation" for t in phase["tasks"])
        phase["counts"]["tests"] = sum(t["kind"] == "test" for t in phase["tasks"])
        phase["conflict"] = phase["state"] == "complete" and any(
            t["state"] in ("open", "in_progress", "unknown", "conflict") for t in phase["tasks"])
    return {"path": str(path), "phases": list(phases.values()), "content_hash": digest(text)}


def discover_roots(configured, cwds):
    found = {str(Path(p).expanduser().resolve()) for p in cwds if p and Path(p).is_dir()}
    for item in configured:
        root = Path(item).expanduser().resolve()
        if not root.is_dir():
            continue
        found.add(str(root))
        count = 0
        for directory, dirs, files in os.walk(root, followlinks=False):
            count += 1
            depth = len(Path(directory).relative_to(root).parts)
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in
                       {"node_modules", "vendor", "target", "build", "dist", "__pycache__"}
                       and not (Path(directory) / d).is_symlink()]
            if depth >= 3 or count >= 10000:
                dirs[:] = []
            if ".git" in files or (Path(directory) / ".git").exists() or any(
                    f in files for f in ("PROJECTS.md", "PLAN.md")):
                found.add(directory)
            if count >= 10000:
                break
    return found


def collect_projects(config, records, old, full, scope, metrics):
    projects, plans, sources = {}, {}, {}
    cwds = [r.get("cwd") for r in records]
    roots = discover_roots(config.get("roots", []), cwds)
    roots = {git(directory, "rev-parse", "--show-toplevel") or directory for directory in roots}
    roots.update(location["path"] for p in old["projects"].values()
                 for location in p.get("locations", []))
    # Worktrees can hold a newer plan than the main checkout.
    for directory in list(roots):
        if not (Path(directory) / ".git").exists():
            continue
        listing = git(directory, "worktree", "list", "--porcelain") or ""
        roots.update(line[9:] for line in listing.splitlines() if line.startswith("worktree "))
    by_root = {}
    known_paths = {location["path"]: pid for pid, project in old["projects"].items()
                   for location in project.get("locations", [])}
    for directory in sorted(roots):
        if not Path(directory).is_dir():
            sources["project:" + directory] = {"status": "absent", "complete": True, "path": directory,
                                                "kind": "project", "error": "Known project directory is missing"}
            continue
        root = git(directory, "rev-parse", "--show-toplevel")
        root = root or directory
        if root in by_root:
            continue
        common = git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
        pid = known_paths.get(root) or identity("project", old["machine_id"], common or root)
        sid = "project:" + root
        if scope and scope.get("project") and pid != scope["project"]:
            by_root[root] = pid
            continue
        paths = [Path(root) / n for n in ("PROJECTS.md", "PLAN.md") if (Path(root) / n).is_file()]
        if not common and not paths:
            continue
        sources[sid] = {"status": "ok", "complete": True, "path": root, "kind": "project"}
        project = projects.setdefault(pid, {"id": pid, "source_id": sid, "title": Path(root).name,
            "locations": [], "plan_ids": [], "evidence": "Local repository/worktree and project plans"})
        location = {"path": root, "common_dir": common, "branch": git(root, "branch", "--show-current"),
                    "head": git(root, "rev-parse", "HEAD"), "remote": git(root, "remote", "get-url", "origin"),
                    "status": git(root, "status", "--short"),
                    "ahead_behind": git(root, "rev-list", "--left-right", "--count", "HEAD...@{upstream}")}
        if common and location["status"] is None:
            sources[sid].update(status="error", complete=False, error="Cannot read worktree status")
        project["locations"].append(location)
        by_root[root] = pid
        visited = set()
        while paths:
            if len(visited) >= 500:
                sources[sid].update(status="partial", complete=False, error="Linked-plan limit of 500 files reached")
                break
            path = paths.pop(0).resolve()
            if path in visited:
                continue
            visited.add(path)
            plan_id = identity("plan", old["machine_id"], str(path))
            try:
                raw = path.read_bytes()
                if len(raw) > 5 * 1024 * 1024:
                    raise ValueError("Plan exceeds the 5 MiB parsing limit")
                text = raw.decode("utf-8", errors="replace")
                previous = old["plans"].get(plan_id)
                if not full and previous and previous.get("content_hash") == digest(text):
                    plan = {k: copy.deepcopy(v) for k, v in previous.items()
                            if k in ("path", "phases", "content_hash", "links")}
                    metrics["plan_cache_hits"] += 1
                else:
                    plan = parse_plan(path, text)
                    plan["links"] = [m[1] for m in re.finditer(r"\]\(([^)#]+\.md)(?:#[^)]*)?\)", text)
                                     if not re.match(r"^[a-zA-Z]+:", m[1])]
                    metrics["plans_parsed"] += 1
                plan.update(id=plan_id, source_id=sid, project_id=pid, observed_at=now())
                plans[plan_id] = plan
                project["plan_ids"].append(plan_id)
                for link in plan.get("links", []):
                    target = (path.parent / link).resolve()
                    if target.is_relative_to(Path(root).resolve()) and target.is_file():
                        paths.append(target)
            except (OSError, ValueError) as exc:
                sources[sid].update(status="partial", complete=False, error=str(exc))
                if plan_id in old["projects"].get(pid, {}).get("plan_ids", []):
                    project["plan_ids"].append(plan_id)
        project["plan_ids"] = sorted(set(project["plan_ids"]))
    for row in records:
        cwd = row.get("cwd")
        matches = [(root, pid) for root, pid in by_root.items()
                   if cwd and (cwd == root or cwd.startswith(root + os.sep))]
        row["project_ids"] = [max(matches, key=lambda x: len(x[0]))[1]] if matches else []
    return projects, plans, sources
