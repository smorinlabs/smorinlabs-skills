"""Optional local adapters. All subprocesses inspect state; none control agents."""
from __future__ import annotations

import concurrent.futures
import copy
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

from .state import digest, identity, now, write_json
from .projects import collect_projects


def run(argv, json_output=True, timeout=25):
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(str(exc)) from exc
    if proc.returncode:
        raise ValueError((proc.stderr or proc.stdout or "Command failed")[-1500:])
    if json_output:
        try:
            data = json.loads(proc.stdout)
        except ValueError as exc:
            raise ValueError("Invalid JSON from " + Path(argv[0]).name) from exc
        if isinstance(data, dict) and data.get("error"):
            raise ValueError(str(data["error"]))
        return data
    return proc.stdout


def tool_name(process):
    text = " ".join(str(process.get(k, "")) for k in ("path", "argv0", "name", "script")).lower()
    return next((t for t in ("claude", "codex", "muse", "opencode", "herdr") if t in text), "unknown")


def excerpt(text):
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    return "\n".join(text.splitlines()[-100:])[-12000:]


def text_excerpt(path, cached, full, metrics):
    if not path:
        return {"text": "", "basis": "No transcript file; native metadata only"}
    try:
        file = Path(path)
        stat = file.stat()
        stamp = [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]
        if not full and cached and cached.get("stamp") == stamp:
            metrics["excerpt_cache_hits"] += 1
            return cached
        with file.open("rb") as stream:
            head = stream.read(16384)
            offset = max(0, stat.st_size - 131072)
            stream.seek(offset)
            tail = stream.read(131072)
        lines = head.splitlines() + tail.splitlines()[1:] if offset else tail.splitlines()
        messages = []
        for line in lines:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            payload = item.get("payload") or item.get("message") or item
            if not isinstance(payload, dict):
                continue
            role = payload.get("role") or item.get("type")
            if role not in ("user", "assistant"):
                continue
            content = payload.get("content", "")
            if isinstance(content, list):
                content = "\n".join(b.get("text", "") for b in content if isinstance(b, dict)
                                    and isinstance(b.get("text"), str))
            if isinstance(content, str) and content:
                value = role + ": " + content[:6000]
                if value not in messages:
                    messages.append(value)
        metrics["excerpts_parsed"] += 1
        return {"stamp": stamp, "text": "\n\n".join(messages[:1] + messages[-4:])[-18000:],
                "basis": "Bounded user/assistant messages from transcript head/tail"}
    except OSError as exc:
        return {"text": "", "basis": "Transcript unavailable", "error": str(exc)}


def resolve_inventory():
    sibling = Path(__file__).resolve().parents[3] / "session-agent-list/scripts/session-inventory"
    candidates = [sibling]
    if shutil.which("session-inventory"):
        candidates.append(Path(shutil.which("session-inventory")))
    candidates += [Path.home() / p / "session-agent-list/scripts/session-inventory"
                   for p in (".agents/skills", ".claude/skills")]
    return next((p for p in candidates if p.is_file()), None)


def native(data, directory, full, metrics):
    script = resolve_inventory()
    if not script:
        failure = {"status": "unavailable", "complete": False,
                   "error": "Install session-agent-list alongside session-map"}
        return {}, {"native": failure, **{sid: dict(failure) for sid in data["sources"]
                                          if sid.startswith("native:")}}
    args = [sys.executable, str(script), "list", "--json", "--include-subagents",
            "--cache-dir", str(directory / "cache/native")]
    if full:
        args.append("--refresh-cache")
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=180)
        try:
            result = json.loads(proc.stdout)
        except ValueError as exc:
            raise ValueError("Native collector returned no valid inventory (exit " + str(proc.returncode) +
                             "): " + (proc.stderr or "empty/invalid stdout")[-1500:]) from exc
        if proc.returncode not in (0, 1) or not isinstance(result.get("sessions"), list):
            raise ValueError((proc.stderr or "Native collector failed")[-1500:])
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return {}, {"native": {"status": "error", "complete": False, "error": str(exc)},
                    **{sid: {"status": "error", "complete": False, "error": str(exc)}
                       for sid in data["sources"] if sid.startswith("native:")}}
    metrics["native_cache"] = result.get("cache", {})
    sources = {"native:" + tool: {**source, "kind": "native", "complete": source.get("status") in ("ok", "absent")}
               for tool, source in result.get("sources", {}).items()}
    sources["native"] = {"status": "ok" if proc.returncode == 0 else "partial", "complete": proc.returncode == 0,
                         "kind": "native-collector"}
    rows = {}
    for record in result["sessions"]:
        sid = "native:" + record["tool"]
        key = identity("conversation", data["machine_id"], sid, record["id"])
        rows[key] = {"id": key, "source_id": sid, "native_id": record["id"], "agent": record["tool"],
                     "title": record.get("name") or record.get("title") or record["id"],
                     "cwd": record.get("spawn_dir"), "live": record.get("live", "unknown"),
                     "live_basis": record.get("live_basis"), "pid": record.get("pid"),
                     "lineage": record.get("lineage"), "transcript": record.get("transcript"),
                     "updated": record.get("updated"), "unreadable": record.get("unreadable", False),
                     "resume_blocked": record.get("resume_blocked"), "evidence": "Native session metadata",
                     "navigation": None}
    return rows, sources


def rex(data, deep):
    exe = shutil.which("rex")
    if not exe:
        return {}, {"rex": {"status": "absent", "complete": False, "kind": "rex"}}
    prefix = [exe, "--autostart=false"]
    source = {"status": "ok", "complete": True, "kind": "rex"}
    rows = {}
    try:
        listing = run(prefix + ["ls", "--json"])
        clients = run(prefix + ["client", "ls", "--json"])
        apps = [c for c in clients.get("clients", []) if c.get("info", {}).get("kind") == "app"]
        client = apps[0]["client_id"] if len(apps) == 1 else None
        can_select = False
        if client:
            try:
                actions = run(prefix + ["-C", client, "actions", "--json"])
                actions = actions.get("actions", []) if isinstance(actions, dict) else actions
                can_select = any(a.get("name", a.get("id")) == "session.select" and
                    "window_id" in a.get("args", {}).get("properties", {}) for a in actions)
            except (ValueError, TypeError):
                pass
        for workspace in listing["sessions"]:
            sid = workspace["session_id"]
            try:
                details = run(prefix + ["session", "inspect", sid, "--json"])
            except ValueError as exc:
                source.update(status="partial", complete=False, error=str(exc))
                continue
            for window in details.get("windows", []):
                for layer in window.get("layers", []):
                    for block in layer.get("blocks", []):
                        bid = block["block_id"]
                        key = identity("location", data["machine_id"], "rex", sid, window["window_id"], bid)
                        row = {"id": key, "source_id": "rex", "manager": "Rex", "workspace_id": sid,
                               "tab_id": window["window_id"], "pane_id": bid, "workspace": details.get("label", sid),
                               "title": window.get("label", bid), "navigation": None, "evidence": ""}
                        try:
                            process = run(prefix + ["block", "call", "-s", sid, "-b", bid, "process"])
                            foreground = process.get("foreground") or process.get("child") or {}
                            row.update(cwd=foreground.get("cwd"), pid=foreground.get("pid"),
                                       agent=tool_name(foreground), process=foreground)
                            if deep(row):
                                # Rex has no line-limit option. Retain a bounded tail, never persist its full scrollback.
                                row["evidence"] = excerpt(run(prefix + ["capture", "-s", sid, "-b", bid,
                                                                    "--trim", "--unwrap"], False))
                            else:
                                prior = data["locations"].get(key, {})
                                row.update(evidence=prior.get("evidence", ""),
                                           observed_at=prior.get("observed_at", now()))
                            if can_select:
                                argv = prefix + ["-C", client, "do", "session.select",
                                    "session_id=" + sid, "window_id=" + window["window_id"]]
                                row["navigation"] = {"argv": argv, "command": shlex.join(argv),
                                    "cwd": "any directory", "validated_at": now(), "kind": "select-tab"}
                        except ValueError as exc:
                            row["error"] = str(exc)
                            source.update(status="partial", complete=False)
                        rows[key] = row
    except (ValueError, KeyError, TypeError) as exc:
        source.update(status="error", complete=False, error=str(exc))
    return rows, {"rex": source}


def herdr(data, names, deep):
    exe = shutil.which("herdr")
    rows, sources = {}, {}
    for name in names:
        sid = "herdr:" + name
        source = {"status": "ok", "complete": True, "kind": "herdr", "instance": name}
        sources[sid] = source
        if not exe:
            source.update(status="absent", complete=False)
            continue
        prefix = [exe, "--session", name]
        try:
            snap = run(prefix + ["api", "snapshot"])["result"]["snapshot"]
            workspaces = {w["workspace_id"]: w for w in snap["workspaces"]}
            tabs = {t["tab_id"]: t for t in snap["tabs"]}
            for pane in snap["panes"]:
                # terminal_id distinguishes a recreated pane even when display handles repeat.
                incarnation = pane.get("terminal_id")
                if not incarnation:
                    source.update(status="partial", complete=False, error="Missing terminal incarnation")
                    continue
                reported = (pane.get("agent_session") or {}).get("value")
                key = identity("location", data["machine_id"], sid, pane["pane_id"], incarnation)
                previous_locations = [r for r in data["locations"].values() if
                    r.get("source_id") == sid and r.get("pane_id") == pane["pane_id"] and
                    (r.get("incarnation") == incarnation or (r.get("imported") and
                     r.get("native_id") and r.get("native_id") == reported))]
                if len(previous_locations) == 1:
                    key = previous_locations[0]["id"]
                row = {"id": key, "source_id": sid, "manager": "Herdr", "instance": name,
                    "workspace_id": pane["workspace_id"], "tab_id": pane["tab_id"], "pane_id": pane["pane_id"],
                    "incarnation": incarnation, "workspace": workspaces[pane["workspace_id"]].get("label"),
                    "title": tabs[pane["tab_id"]].get("label"), "agent": pane.get("agent", "unknown"),
                    "cwd": pane.get("foreground_cwd") or pane.get("cwd"), "reported_native_id": reported,
                    "native_id": reported, "manager_status": pane.get("agent_status"), "evidence": "",
                    "identity_basis": "Manager metadata; process corroboration pending", "navigation": None}
                try:
                    info = run(prefix + ["pane", "process-info", "--pane", pane["pane_id"]])["result"]["process_info"]
                    row["pid"] = info.get("foreground_process_group_id")
                    row["processes"] = info.get("foreground_processes", [])
                    for proc in row["processes"]:
                        argv = proc.get("argv", [])
                        for flag in ("resume", "--resume", "--session"):
                            if flag in argv and len(argv) > argv.index(flag) + 1:
                                actual = argv[argv.index(flag) + 1]
                                if any(c["native_id"] == actual for c in data["conversations"].values()):
                                    row.update(native_id=actual, identity_basis="Observed process resume argument",
                                               identity_conflict=actual != reported)
                    if deep(row):
                        row["evidence"] = excerpt(run(prefix + ["pane", "read", pane["pane_id"],
                                                              "--source", "recent-unwrapped", "--lines", "100"], False))
                    else:
                        previous = data["locations"].get(key, {})
                        row.update(evidence=previous.get("evidence", ""), observed_at=previous.get("observed_at", now()))
                    argv = prefix + ["tab", "focus", pane["tab_id"]]
                    row["navigation"] = {"argv": argv, "command": shlex.join(argv), "kind": "select-tab",
                                         "cwd": "any directory", "validated_at": now()}
                except (ValueError, KeyError) as exc:
                    row["error"] = str(exc)
                    source.update(status="partial", complete=False)
                rows[key] = row
        except (ValueError, KeyError, TypeError) as exc:
            source.update(status="error", complete=False, error=str(exc))
    return rows, sources


def agent_deck(data):
    exe = shutil.which("agent-deck")
    source = {"status": "ok", "complete": True, "kind": "agent-deck"}
    if not exe:
        return {}, {"agent-deck": {**source, "status": "absent", "complete": False}}
    try:
        records = run([exe, "list", "--json"])
        if isinstance(records, dict):
            records = records.get("sessions", [])
        rows = {}
        for item in records:
            key = identity("location", data["machine_id"], "agent-deck", item.get("profile"), item["id"])
            rows[key] = {"id": key, "source_id": "agent-deck", "manager": "Agent Deck",
                "title": item.get("title", item["id"]), "workspace": item.get("group"),
                "cwd": item.get("path"), "agent": item.get("tool"), "registry_id": item["id"],
                "native_id": item.get("claude_session_id"), "navigation": None,
                "evidence": "Retained registry entry; registry membership is not running-process evidence",
                "registry_only": True}
        return rows, {"agent-deck": source}
    except (ValueError, KeyError, TypeError) as exc:
        return {}, {"agent-deck": {**source, "status": "error", "complete": False, "error": str(exc)}}


def collect(data, directory, full=False, scope=None):
    directory = Path(directory)
    config = data["config"]
    metrics = {"excerpts_parsed": 0, "excerpt_cache_hits": 0, "plans_parsed": 0, "plan_cache_hits": 0}
    sources, locations, conversations = {}, {}, {}
    if "native" in config["sources"]:
        conversations, src = native(data, directory, full, metrics)
        sources.update(src)
    context = {**data, "conversations": {**data["conversations"], **conversations}}
    selected_projects = set()
    if scope and scope.get("project"):
        selected_projects.add(scope["project"])
    if scope and scope.get("session"):
        target = data["locations"].get(scope["session"]) or data["conversations"].get(scope["session"], {})
        selected_projects.update(target.get("overrides", {}).get("project_ids", target.get("project_ids", [])))

    def deep(row):
        if not scope or full:
            return True
        prior = data["locations"].get(row["id"], {})
        return row["id"] == scope.get("session") or bool(selected_projects.intersection(
            prior.get("overrides", {}).get("project_ids", prior.get("project_ids", [])))) or not prior

    adapters = []
    if "rex" in config["sources"]:
        adapters.append(lambda: rex(context, deep))
    if "herdr" in config["sources"]:
        adapters.append(lambda: herdr(context, config.get("herdr_sessions", []), deep))
        if not config.get("herdr_sessions"):
            sources["herdr"] = {"status": "unconfigured", "complete": False,
                                "error": "Select a named instance with --herdr-session"}
    if "agent-deck" in config["sources"]:
        adapters.append(lambda: agent_deck(context))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for rows, src in pool.map(lambda fn: fn(), adapters):
            locations.update(rows)
            sources.update(src)
    for row in locations.values():
        matches = [c for c in conversations.values() if
            (row.get("native_id") and c["native_id"] == row["native_id"] and c["agent"] == row.get("agent")) or
            (row.get("pid") and c.get("pid") == row["pid"] and c.get("live") == "yes")]
        row["conversation_id"] = matches[0]["id"] if len(matches) == 1 else None
        if row.get("registry_only") and len(matches) == 1:
            row["corroboration"] = {"live": matches[0].get("live"), "basis": matches[0].get("live_basis"),
                                    "conversation_id": matches[0]["id"]}
        if len(matches) > 1:
            row["identity_conflict"] = True
    cache_path = directory / "cache/excerpts.json"
    try:
        cache = json.loads(cache_path.read_text()) if not full else {}
    except (OSError, ValueError):
        cache = {}
    for key, row in conversations.items():
        prior = data["conversations"].get(key, {})
        related = any(loc.get("conversation_id") == key and deep(loc) for loc in locations.values())
        membership = prior.get("overrides", {}).get("project_ids", (prior.get("assessment") or {}).get(
            "project_ids", prior.get("project_ids", [])))
        scoped = bool(scope and (key == scope.get("session") or selected_projects.intersection(membership)))
        should_read = related or scoped or (not scope and
            (row["live"] in ("yes", "unknown") or bool(prior.get("assessment"))))
        if should_read:
            result = text_excerpt(row.get("transcript"), cache.get(key), full, metrics)
            cache[key] = result
            row["evidence"] = result["text"] or result["basis"]
            if result.get("error"):
                row["evidence_error"] = result["error"]
        else:
            row["evidence"] = prior.get("evidence", row["evidence"])
        row["review_requested"] = scoped
    write_json(cache_path, cache)
    records = list(locations.values()) + list(conversations.values())
    project_scope = {"project": next(iter(selected_projects))} if scope and len(selected_projects) == 1 else None
    projects, plans, src = collect_projects(config, records, data, full, project_scope, metrics)
    sources.update(src)
    for row in records:
        for pid in row.get("project_ids", []):
            if pid in projects:
                projects[pid].setdefault("session_ids", []).append(row["id"])
    for project in projects.values():
        project["session_ids"] = sorted(project.get("session_ids", []))
    return {"locations": locations, "conversations": conversations, "projects": projects, "plans": plans}, sources, metrics
