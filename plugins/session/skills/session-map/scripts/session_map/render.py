"""Render saved JSON only. No environment discovery occurs here."""
import copy
import json
from pathlib import Path
import shlex
import sys

from .state import atomic, now, validate


def render(data, directory):
    validate(data)
    directory = Path(directory).resolve()
    embedded = copy.deepcopy(data)
    script = Path(__file__).resolve().parents[1] / "session-map"
    embedded["render"] = {"at": now(), "map_dir": str(directory),
        "update_prompt": "/session-map update --map-dir " + shlex.quote(str(directory)),
        "render_command": shlex.join([sys.executable, str(script), "render", "--map-dir", str(directory)])}
    payload = json.dumps(embedded, ensure_ascii=True, separators=(",", ":"))
    payload = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    template = Path(__file__).resolve().parents[2] / "templates/index.html"
    text = template.read_text()
    if text.count("__INVENTORY_JSON__") != 1:
        raise ValueError("Invalid HTML template: expected one inventory marker")
    html = text.replace("__INVENTORY_JSON__", payload)
    if 'id="inventory"' not in html:
        raise ValueError("HTML lacks the saved inventory")
    atomic(directory / "index.html", html)
    return directory / "index.html"
