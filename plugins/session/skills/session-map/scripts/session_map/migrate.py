"""Explicit import of the original local prototype; never trusts its commands."""
import copy

from .state import fingerprint, identity, new_map, now
from .projects import STATE


def import_prototype(raw, config):
    if not isinstance(raw, dict) or not isinstance(raw.get("sessions"), list) or not isinstance(raw.get("projects"), list):
        raise ValueError("Expected the prototype inventory with sessions and projects arrays")
    data = new_map(config)
    data["updated_at"] = raw.get("captured_at") or raw.get("generated_at") or now()
    projects = {}
    for item in raw["projects"]:
        key = identity("project", data["machine_id"], "import", item["id"])
        projects[item["id"]] = key
        row = {"id": key, "source_id": "import", "title": item.get("name", item["id"]),
               "legacy_id": item["id"], "locations": item.get("locations", []), "plan_ids": [],
               "evidence": item.get("description", ""), "imported": True}
        data["projects"][key] = row
        for pl in item.get("plans", []):
            plan_id = identity("plan", data["machine_id"], pl["path"])
            phases = copy.deepcopy(pl.get("phases", []))
            for phase in phases:
                phase["state"] = STATE.get(phase.get("state"), phase.get("state", "unknown"))
                for task in phase.get("tasks", []):
                    task["state"] = STATE.get(task.get("state"), task.get("state", "unknown"))
                phase["counts"] = {name: sum(t["state"] == name for t in phase.get("tasks", []))
                                   for name in (*STATE.values(), "conflict")}
                phase["counts"]["total"] = len(phase.get("tasks", []))
            data["plans"][plan_id] = {"id": plan_id, "source_id": "import", "project_id": key,
                                     "path": pl["path"], "phases": phases}
            row["plan_ids"].append(plan_id)
    for item in raw.get("history", []):
        source = "native:" + item["tool"]
        key = identity("conversation", data["machine_id"], source, item["id"])
        data["conversations"][key] = {"id": key, "source_id": source, "native_id": item["id"],
            "agent": item["tool"], "title": item.get("name") or item.get("title") or item["id"],
            "cwd": item.get("spawn_dir"), "live": "unknown", "transcript": item.get("transcript"),
            "lineage": item.get("lineage"), "evidence": "Imported historical metadata; liveness requires refresh",
            "project_ids": [projects[item["project"]]] if item.get("project") in projects else []}
    for item in raw["sessions"]:
        manager = item.get("manager")
        agent = {"Claude Code": "claude", "Codex": "codex", "Muse": "muse", "OpenCode": "opencode"}.get(item.get("agent"), item.get("agent", "unknown"))
        if manager == "Rex" and all(item.get(k) for k in ("workspace_id", "window_id", "pane_id")):
            source = "rex"
            key = identity("location", data["machine_id"], source, item["workspace_id"], item["window_id"], item["pane_id"])
            kind = "locations"
        elif manager == "Herdr" and item.get("pane_id"):
            source = "herdr:default"
            key = identity("location", data["machine_id"], source, item["pane_id"], "import-unverified")
            kind = "locations"
        elif item.get("native_id"):
            source = "native:" + agent
            key = identity("conversation", data["machine_id"], source, item["native_id"])
            kind = "conversations"
        else:
            source = "import"
            key = identity("location", data["machine_id"], "unresolved-import", item["id"])
            kind = "locations"
        row = {"id": key, "source_id": source, "manager": manager, "agent": agent,
            "title": item.get("title", item["id"]), "legacy_id": item["id"], "imported": True,
            "workspace": item.get("workspace"), "workspace_id": item.get("workspace_id"),
            "tab_id": item.get("window_id"), "pane_id": item.get("pane_id"),
            "native_id": item.get("native_id"), "cwd": item.get("cwd"),
            "transcript": item.get("transcript"), "evidence": item.get("evidence", ""),
            "live": "unknown", "project_ids": [projects[item["project"]]] if item.get("project") in projects else []}
        row["assessment"] = {"status": item.get("status", "Unknown"), "summary": item.get("summary", ""),
            "next_action": item.get("next", ""), "rationale": "Imported assessment; revalidate its evidence",
            "closure": "candidate" if item.get("status") == "Close candidate" else "unknown",
            "assessed_at": item.get("captured_at", data["updated_at"]), "freshness": "stale",
            "project_ids": row["project_ids"], "evidence_ids": [key], "dependencies": {}}
        data[kind][key] = row
    for kind in ("locations", "conversations", "projects", "plans"):
        for row in data[kind].values():
            row.update(presence="stale", navigation=None, observed_at=data["updated_at"],
                       first_seen=data["updated_at"], last_seen=data["updated_at"], overrides={},
                       assessment_needed=kind != "plans")
            row["fingerprint"] = fingerprint(row)
            row["evidence_hash"] = row["fingerprint"]
            if row.get("assessment"):
                row["assessment"]["evidence_hash"] = "imported-unvalidated"
            data["sources"].setdefault(row["source_id"], {"status": "stale", "complete": False,
                "last_success": data["updated_at"], "error": "Imported evidence; not yet refreshed"})
    data["changes"] = {"imported": [r["id"] for kind in ("locations", "conversations", "projects", "plans")
                                   for r in data[kind].values()]}
    return data
