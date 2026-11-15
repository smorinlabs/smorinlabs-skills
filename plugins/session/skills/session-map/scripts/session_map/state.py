"""Versioned snapshots, optimistic assessment writes, and evidence dependencies."""
from __future__ import annotations

import contextlib
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid

SCHEMA = 1
KINDS = ("locations", "conversations", "projects", "plans")
VOLATILE = {"assessment", "fingerprint", "evidence_hash", "observed_at", "updated_at",
            "last_seen", "first_seen", "validated_at", "error", "assessment_needed", "review_requested"}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     separators=(",", ":")).encode()).hexdigest()


def identity(kind, *parts):
    return kind + ":" + digest(parts)


def fingerprint(row):
    def stable(value):
        if isinstance(value, dict):
            return {k: stable(v) for k, v in value.items() if k not in VOLATILE}
        if isinstance(value, list):
            return [stable(v) for v in value]
        return value
    return digest(stable(row))


def entities(data):
    return {key: row for kind in KINDS for key, row in data[kind].items()}


def new_map(config):
    return {"schema_version": SCHEMA, "map_id": str(uuid.uuid4()),
            "machine_id": str(uuid.uuid4()), "generation_id": str(uuid.uuid4()),
            "created_at": now(), "updated_at": None, "config": config,
            "sources": {}, **{k: {} for k in KINDS}, "changes": {}, "metrics": {}}


def validate(data):
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA:
        raise ValueError("Unsupported or missing inventory schema; preserve the file and migrate explicitly")
    for field in ("map_id", "machine_id", "generation_id"):
        if not isinstance(data.get(field), str) or not data[field]:
            raise ValueError("Missing " + field)
        try:
            uuid.UUID(data[field])
        except ValueError as exc:
            raise ValueError("Invalid UUID: " + field) from exc
    for kind in (*KINDS, "sources", "config"):
        if not isinstance(data.get(kind), dict):
            raise ValueError("Expected object: " + kind)
    seen = set()
    for kind in KINDS:
        for key, row in data[kind].items():
            if not isinstance(row, dict) or row.get("id") != key or key in seen:
                raise ValueError("Invalid or duplicate entity identity: " + key)
            seen.add(key)
    return data


def load(directory):
    return validate(json.loads((Path(directory) / "inventory.json").read_text()))


def atomic(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "w") as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_json(path, value):
    atomic(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


@contextlib.contextmanager
def locked(directory):
    # flock releases on process death; the harmless file can remain after a crash.
    import fcntl
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / ".writer.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another update holds this map's writer lock") from exc
        yield


def save(directory, data):
    validate(data)
    directory = Path(directory)
    previous = directory / "inventory.json"
    if previous.exists():
        old = load(directory)
        write_json(directory / "snapshots" / (old["generation_id"] + ".json"), old)
    write_json(previous, data)
    write_json(directory / "changes.json", {"generation_id": data["generation_id"],
                                           **data.get("changes", {})})
    write_json(directory / "assessment-queue.json", assessment_queue(data))


def reconcile(old, collected, sources, metrics, full=False, scope=None):
    data = copy.deepcopy(old)
    data["generation_id"] = str(uuid.uuid4())
    data["updated_at"] = now()
    data["scope"] = scope or {"mode": "full" if full else "update"}
    for sid, source in sources.items():
        previous = old["sources"].get(sid, {})
        data["sources"][sid] = {**previous, **source, "last_attempt": data["updated_at"]}
        if source["status"] == "ok":
            data["sources"][sid]["last_success"] = data["updated_at"]
            data["sources"][sid].pop("error", None)
    changes = {key: [] for key in ("added", "changed", "not_observed", "stale", "reassess")}
    for kind in KINDS:
        fresh = collected.get(kind, {})
        for key, row in fresh.items():
            before = old[kind].get(key)
            row = copy.deepcopy(row)
            if row.get("error") and before:
                row = {**copy.deepcopy(before), **row,
                       "evidence": before.get("evidence", ""), "navigation": None}
            row.update(id=key, presence="observed", last_seen=data["updated_at"],
                       observed_at=row.get("observed_at", data["updated_at"]),
                       first_seen=before.get("first_seen") if before else data["updated_at"])
            if row.get("error"):
                row["presence"] = "stale"
            row["overrides"] = before.get("overrides", {}) if before else {}
            row["assessment_needed"] = before.get("assessment_needed", False) if before else True
            row["fingerprint"] = fingerprint(row)
            row["evidence_hash"] = row["fingerprint"]
            if before:
                row["overrides"] = before.get("overrides", {})
                row["assessment"] = before.get("assessment")
                if row["fingerprint"] != before.get("fingerprint"):
                    changes["changed"].append(key)
            else:
                row["overrides"] = {}
                row["assessment"] = None
                changes["added"].append(key)
            data[kind][key] = row
        for key, before in old[kind].items():
            if key in fresh:
                continue
            sid = before.get("source_id")
            source = sources.get(sid)
            if not source:  # A scoped update did not cover this source.
                continue
            row = data[kind][key]
            if source["status"] in ("ok", "absent") and source.get("complete", True):
                if row.get("presence") != "not_observed":
                    row["presence"] = "not_observed"
                    row["navigation"] = None
                    changes["not_observed"].append(key)
            elif source["status"] != "ok":
                row["presence"] = "stale"
                row["navigation"] = None
                changes["stale"].append(key)
            if row.get("presence") != "observed" and "live" in row:
                row.setdefault("last_known_live", row.get("live"))
                row["live"] = "unknown"
            row["fingerprint"] = fingerprint(row)
            row["evidence_hash"] = row["fingerprint"]
    all_rows = entities(data)
    for key, row in all_rows.items():
        assessment = row.get("assessment")
        stale = bool(assessment) and (assessment.get("evidence_hash") != row["evidence_hash"] or
            any(all_rows.get(dep, {}).get("fingerprint") != fp
                for dep, fp in assessment.get("dependencies", {}).items()))
        if assessment:
            assessment["freshness"] = "stale" if stale else "current"
        # History remains indexed without automatically requiring deep review of all old conversations.
        relevant = (key in data["projects"] or key in data["locations"] or
                    row.get("live") in ("yes", "unknown") or row.get("review_requested") or assessment is not None)
        row["assessment_needed"] = relevant and (not assessment or stale or full or row.get("assessment_needed", False))
        if row["assessment_needed"]:
            changes["reassess"].append(key)
    data["changes"] = changes
    data["metrics"] = metrics
    return data


def assessment_queue(data):
    return {"generation_id": data["generation_id"], "items": [
        {"id": key, "kind": kind, "evidence_hash": row["evidence_hash"],
         "reason": "changed evidence or dependency" if row.get("assessment") else "not yet assessed",
         "record": row}
        for kind in KINDS if kind != "plans" for key, row in data[kind].items()
        if row.get("assessment_needed")]}


def apply_assessments(data, payload):
    if payload.get("generation_id") != data["generation_id"]:
        raise ValueError("Assessment generation is stale; read the latest queue")
    result = copy.deepcopy(data)
    all_rows = entities(result)
    assessments = payload.get("assessments")
    if not isinstance(assessments, list):
        raise ValueError("assessments must be an array")
    seen = set()
    for item in assessments:
        key = item.get("id")
        row = all_rows.get(key)
        if not row or key in seen or item.get("evidence_hash") != row["evidence_hash"]:
            raise ValueError("Unknown, duplicate, or changed assessment target: " + str(key))
        seen.add(key)
        for field in ("status", "summary", "next_action", "rationale"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError("Assessment requires " + field)
        if item.get("closure", "unknown") not in ("keep", "candidate", "review", "unknown"):
            raise ValueError("Invalid closure recommendation")
        deps = item.get("evidence_ids")
        if not isinstance(deps, list) or not deps or any(d not in all_rows for d in deps):
            raise ValueError("Assessment requires known evidence_ids")
        for field, allowed in (("project_ids", result["projects"]),
                               ("owner_ids", {**result["locations"], **result["conversations"]}),
                               ("related_ids", all_rows)):
            values = item.get(field, [])
            if not isinstance(values, list) or any(v not in allowed for v in values):
                raise ValueError("Invalid " + field)
        if "selected_plan" in item and item["selected_plan"] not in result["plans"]:
            raise ValueError("Unknown selected_plan")
        project_ids = set(item.get("project_ids", row.get("project_ids", [])))
        if key in result["projects"]:
            project_ids.add(key)
        plan_ids = {plan_id for pid in project_ids for plan_id in result["projects"][pid].get("plan_ids", [])}
        if item.get("selected_plan") and item["selected_plan"] not in plan_ids:
            raise ValueError("Selected plan does not belong to the assessed project")
        phases = item.get("phase_ids", [])
        known_phases = {phase["id"] for plan_id in plan_ids if plan_id in result["plans"]
                        for phase in result["plans"][plan_id].get("phases", [])}
        if not isinstance(phases, list) or any(phase not in known_phases for phase in phases):
            raise ValueError("Unknown phase in owning project plans")
        deps = set(deps) | {key} | project_ids | plan_ids
        if key in result["projects"]:
            deps.update(row.get("session_ids", []))
        deps.intersection_update(all_rows)
        row["assessment"] = {**item, "assessed_at": now(), "freshness": "current",
                             "dependencies": {d: all_rows[d]["fingerprint"] for d in sorted(deps)}}
        row["assessment_needed"] = False
    result["generation_id"] = str(uuid.uuid4())
    result["changes"]["assessed"] = sorted(seen)
    result["changes"]["reassess"] = [key for key, row in all_rows.items() if row.get("assessment_needed")]
    return result


def annotate(data, key, values, generation):
    if generation != data["generation_id"]:
        raise ValueError("Annotation generation is stale")
    result = copy.deepcopy(data)
    row = entities(result).get(key)
    allowed = {"title", "project_ids", "selected_plan", "owner_ids", "notes", "container_id"}
    if row is None or not isinstance(values, dict) or set(values) - allowed:
        raise ValueError("Unknown annotation target or field")
    all_rows = entities(result)
    for field in ("project_ids", "owner_ids"):
        if field in values:
            domain = result["projects"] if field == "project_ids" else all_rows
            if not isinstance(values[field], list) or any(v not in domain for v in values[field]):
                raise ValueError("Invalid annotation " + field)
    for field, domain in (("selected_plan", result["plans"]), ("container_id", result["locations"])):
        if field in values and values[field] is not None and values[field] not in domain:
            raise ValueError("Invalid annotation " + field)
    for field in ("title", "notes"):
        if field in values and not isinstance(values[field], str):
            raise ValueError("Invalid annotation " + field)
    row["overrides"] = {**row.get("overrides", {}), **values, "updated_at": now()}
    row["fingerprint"] = fingerprint(row)
    row["evidence_hash"] = row["fingerprint"]
    affected = {key, *row.get("project_ids", []), *values.get("project_ids", [])}
    for target, record in all_rows.items():
        if target in affected or key in (record.get("assessment") or {}).get("dependencies", {}):
            record["assessment_needed"] = True
            if record.get("assessment"):
                record["assessment"]["freshness"] = "stale"
    result["generation_id"] = str(uuid.uuid4())
    return result
