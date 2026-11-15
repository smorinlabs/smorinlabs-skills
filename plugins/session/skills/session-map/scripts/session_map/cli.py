"""Command entry point. Collection and semantic assessment are separate steps."""
import argparse
import json
import os
from pathlib import Path
import sys
import webbrowser

from . import VERSION
from .collect import collect
from .migrate import import_prototype
from .render import render
from .state import (annotate, apply_assessments, assessment_queue, entities, load, locked,
                    new_map, reconcile, save)


def parser():
    p = argparse.ArgumentParser(description="Build, update, or render a private local project/session map.")
    p.add_argument("mode", nargs="?", default="auto", choices=("auto", "full", "update", "render", "assess", "annotate", "import"))
    p.add_argument("--version", action="version", version=VERSION)
    default = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "session-map/maps/default"
    p.add_argument("--map-dir", type=Path, default=default)
    scope = p.add_mutually_exclusive_group()
    scope.add_argument("--project", help="Persistent project ID copied from the inventory")
    scope.add_argument("--session", help="Persistent location or conversation ID")
    p.add_argument("--root", action="append", help="Project search root; repeat to configure several")
    p.add_argument("--herdr-session", action="append", help="Explicit local Herdr instance; repeatable")
    p.add_argument("--source", choices=("native", "rex", "herdr", "agent-deck"), action="append")
    p.add_argument("--file", type=Path, help="JSON assessment, annotation, or prototype import file")
    p.add_argument("--id", help="Annotation target ID")
    p.add_argument("--generation", help="Required current generation for annotations")
    p.add_argument("--no-open", action="store_true", help="Do not open the generated HTML in a browser")
    return p


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    directory = args.map_dir.expanduser().resolve()
    try:
        with locked(directory):
            exists = (directory / "inventory.json").exists()
            if args.mode == "import" and exists:
                raise ValueError("Import requires a new map directory; existing inventory was preserved")
            data = load(directory) if exists else None
            mode = ("update" if exists else "full") if args.mode == "auto" else args.mode
            if mode not in ("full", "import") and data is None:
                raise ValueError("No saved inventory. Use full (or invoke without a mode) first")
            if mode in ("assess", "annotate", "import") and not args.file:
                raise ValueError(mode + " requires --file")
            if mode != "update" and (args.project or args.session):
                raise ValueError("Project/session scope is supported only by update")
            if mode not in ("full", "update", "import") and (args.root or args.source or args.herdr_session):
                raise ValueError("Source configuration is valid only when collecting or importing")
            if data is None and (directory / "index.html").exists():
                raise ValueError("Existing index.html without saved inventory; choose a new map directory")
            config = dict(data["config"]) if data else {"sources": ["native", "rex", "agent-deck"], "roots": [], "herdr_sessions": []}
            if args.source:
                config["sources"] = list(dict.fromkeys(args.source))
            if args.root:
                config["roots"] = [str(Path(r).expanduser().resolve()) for r in args.root]
            if args.herdr_session:
                config["herdr_sessions"] = list(dict.fromkeys(args.herdr_session))
                if "herdr" not in config["sources"]:
                    config["sources"].append("herdr")
            exit_code = 0
            if mode in ("full", "update"):
                data = data or new_map(config)
                data["config"] = config
                if args.project and args.project not in data["projects"]:
                    raise ValueError("Unknown project ID")
                if args.session and args.session not in {**data["locations"], **data["conversations"]}:
                    raise ValueError("Unknown session ID")
                scope = {"project": args.project} if args.project else {"session": args.session} if args.session else None
                fresh, sources, metrics = collect(data, directory, full=mode == "full", scope=scope)
                data = reconcile(data, fresh, sources, metrics, full=mode == "full", scope=scope)
                save(directory, data)
                exit_code = int(any(s["status"] not in ("ok", "absent") for s in sources.values()))
            elif mode in ("assess", "annotate", "import"):
                payload = json.loads(args.file.read_text())
                if mode == "assess":
                    data = apply_assessments(data, payload)
                elif mode == "annotate":
                    if not args.id or not args.generation:
                        raise ValueError("annotate requires --id and --generation")
                    data = annotate(data, args.id, payload, args.generation)
                else:
                    data = import_prototype(payload, config)
                save(directory, data)
            output = render(data, directory)
            summary = {"mode": mode, "map_dir": str(directory), "html": str(output),
                "generation_id": data["generation_id"], "locations": len(data["locations"]),
                "conversations": len(data["conversations"]), "projects": len(data["projects"]),
                "pending_assessments": len(assessment_queue(data)["items"]), "metrics": data["metrics"],
                "changes": {k: len(v) for k, v in data["changes"].items()},
                "source_errors": {k: v for k, v in data["sources"].items() if v["status"] not in ("ok", "absent")}}
        if not args.no_open:
            summary["browser_open_requested"] = webbrowser.open(output.as_uri())
        print(json.dumps(summary, ensure_ascii=False))
        return exit_code
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc), "map_dir": str(directory)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
