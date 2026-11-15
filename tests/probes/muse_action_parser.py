#!/usr/bin/env python3
"""Exercise an externally supplied, pinned Action parser on the workflow templates."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import yaml

EXPECTED_SHA256 = "196a29836e99e5137a58348c77949f4a62724afdec0c5afa6c02a33e7e461045"
ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parser", type=Path, required=True,
                        help="Pinned parse-sdk-options.ts with shell-quote@1.8.4 available beside it")
    args = parser.parse_args()
    source = args.parser.resolve(strict=True)
    if hashlib.sha256(source.read_bytes()).hexdigest() != EXPECTED_SHA256:
        parser.error("Action parser does not match the verified pinned SHA-256")
    version = subprocess.check_output(["node", "-e", "const p=require.resolve('shell-quote/package.json',{paths:[process.argv[1]]});process.stdout.write(require(p).version)", str(source.parent)], text=True)
    if version != "1.8.4":
        parser.error(f"Expected shell-quote 1.8.4; found {version}")
    directory = ROOT / "plugins/muse-github/skills/muse-github-setup/templates/.github/workflows"
    cases = {}
    for name in ("muse-pr-review.yml", "muse-followup.yml"):
        workflow = yaml.safe_load((directory / name).read_text())
        for job in workflow["jobs"].values():
            for step in job["steps"]:
                if str(step.get("uses", "")).startswith("anthropics/claude-code-action@"):
                    cases[name] = step["with"]["claude_args"]
    if len(cases) != 2:
        raise ValueError("Expected one Claude Action in each workflow")
    with tempfile.TemporaryDirectory(prefix="muse-parser-cases-") as tmp:
        fixture = Path(tmp) / "cases.json"
        fixture.write_text(json.dumps(cases))
        subprocess.run(["bun", str(ROOT / "tests/probes/muse_action_parser.ts"), str(source), str(fixture)], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
