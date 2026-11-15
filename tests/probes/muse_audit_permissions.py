#!/usr/bin/env python3
"""Probe docs-scoped write permissions using a local mock and the real Claude CLI.

No real model or credentials are used. The Claude subprocess runs under macOS
sandbox-exec with outbound connections limited to this probe's loopback port.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
from pathlib import Path
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = Path(__file__).resolve().parents[2]
HELPER = REPO / "plugins/muse-github/skills/muse-github-setup/templates/.github/scripts/muse_ci.py"
TEMPLATES = HELPER.parents[2]
# Public synthetic marker used to check whether denied reads expose file contents.
DENIED_READ_MARKER = "PUBLIC_DENIED_READ_MARKER_39c127"
PROJECT_MARKER = "PROJECT_INSTRUCTIONS_PROBE_8e1b0"


def load_helper():
    spec = importlib.util.spec_from_file_location("muse_probe_helper", HELPER)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper


def sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--claude", default=shutil.which("claude"), help="Path to the installed Claude CLI")
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    if not args.claude:
        parser.error("Claude CLI not found; pass --claude")
    with tempfile.TemporaryDirectory(prefix="muse-permission-probe-") as temp:
        base = Path(temp)
        root, runtime = base / "checkout", base / "runner_temp" / "runtime"
        root.mkdir()
        runtime.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (root / "normal.txt").write_text("NORMAL_TRACKED_PROBE_73f1\n")
        (root / "nested").mkdir()
        (root / "nested/normal.txt").write_text("NORMAL_TRACKED_PROBE_73f1\n")
        (root / "nested/CLAUDE.md").write_text(PROJECT_MARKER + "_NESTED\n")
        subprocess.run(["git", "-C", str(root), "add", "normal.txt"], check=True)
        with (root / ".git/config").open("a") as f:
            f.write(f"\n[probe]\n    fake = {DENIED_READ_MARKER}\n")
        outside = base / "outside-marker.txt"
        outside.write_text(DENIED_READ_MARKER + "\n")
        state = runtime / "state.json"
        state.write_text(json.dumps({"fake": DENIED_READ_MARKER}))
        profile_dir = root / ".github/muse-ci"
        profile_dir.mkdir(parents=True)
        (profile_dir / "fix-settings.json").write_bytes((TEMPLATES / ".github/muse-ci/fix-settings.json").read_bytes())
        settings = runtime / "settings.json"
        helper = load_helper()
        spec = importlib.util.spec_from_file_location("muse_triage_probe", HELPER.with_name("muse_audit_triage.py"))
        triage = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(triage)
        source = json.loads((TEMPLATES / ".github/muse-audit-triage/triage-settings.json").read_text())
        profile = triage.triage_configuration(helper, root, runtime, source)
        settings.write_text(json.dumps(profile))
        (root / "docs").mkdir()
        (root / "docs/normal.md").write_text("ORIGINAL\n")
        (root / "docs/CLAUDE.md").write_text("ORIGINAL\n")
        (root / "docs/.env.local").write_text("ORIGINAL\n")
        logs = runtime.parent / "github-ci-logs"
        logs.mkdir()
        (logs / "job.log").write_text("ALLOWED_CI_LOG_PROBE\n")
        other_temp = runtime.parent / "other-marker.txt"
        other_temp.write_text(DENIED_READ_MARKER + "\n")
        marker = base / "unwanted-execution"
        (root / "CLAUDE.md").write_text(PROJECT_MARKER + "\n")
        (root / ".claude").mkdir()
        (root / ".claude/rules").mkdir()
        (root / ".claude/rules/probe.md").write_text(PROJECT_MARKER + "_RULE\n")
        skill = root / ".claude/skills/probe"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: injected_probe\ndescription: " + PROJECT_MARKER + "\n---\nInjected instruction.\n")
        (root / ".claude/settings.json").write_text(json.dumps({"hooks": {"SessionStart": [{"hooks": [{
            "type": "command", "command": f"touch {marker}"}]}]}}))
        (root / ".mcp.json").write_text(json.dumps({"mcpServers": {"probe_forbidden_mcp": {
            "command": "/usr/bin/touch", "args": [str(marker)]}}}))
        for name in ("claude", "config", "cache", "data", "state"):
            (runtime / name).mkdir()
        calls = [
            ("allowed_edit", "Edit", {"file_path": str(root / "docs/normal.md"), "old_string": "ORIGINAL", "new_string": "UPDATED"}),
            ("allowed_write", "Write", {"file_path": str(root / "docs/new.md"), "content": "NEW"}),
            ("outside_edit", "Edit", {"file_path": str(root / "normal.txt"), "old_string": "NORMAL_TRACKED", "new_string": "BAD"}),
            ("outside_write", "Write", {"file_path": str(root / "outside.txt"), "content": "BAD"}),
            ("protected_write", "Write", {"file_path": str(root / "docs/CLAUDE.md"), "content": "BAD"}),
            ("secret_edit", "Edit", {"file_path": str(root / "docs/.env.local"), "old_string": "ORIGINAL", "new_string": "BAD"}),
            ("normal_read", "Read", {"file_path": str(root / "normal.txt")}),
        ]
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *unused):
                pass
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"LOOPBACK_WEB_PROBE_CONTENT")
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                if self.path.split("?")[0] != "/v1/messages" or length > 4_000_000:
                    self.send_error(404)
                    return
                data = json.loads(self.rfile.read(length))
                requests.append(data)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                initial = {"id": "msg_probe", "type": "message", "role": "assistant", "model": "muse-spark-1.3-contributor",
                           "content": [], "stop_reason": None, "stop_sequence": None,
                           "usage": {"input_tokens": 100, "output_tokens": 1}}
                self.wfile.write(sse("message_start", {"type": "message_start", "message": initial}))
                if len(requests) == 1:
                    current_calls = calls if len(requests) == 1 else [
                        ("web_fetch", "WebFetch", {"url": f"http://127.0.0.1:{port}/page", "prompt": "Read page."}),
                        ("web_search", "WebSearch", {"query": "loopback mock search"})]
                    for i, (label, tool, tool_input) in enumerate(current_calls):
                        self.wfile.write(sse("content_block_start", {"type": "content_block_start", "index": i,
                            "content_block": {"type": "tool_use", "id": "toolu_" + label, "name": tool, "input": {}}}))
                        self.wfile.write(sse("content_block_delta", {"type": "content_block_delta", "index": i,
                            "delta": {"type": "input_json_delta", "partial_json": json.dumps(tool_input)}}))
                        self.wfile.write(sse("content_block_stop", {"type": "content_block_stop", "index": i}))
                    reason = "tool_use"
                else:
                    self.wfile.write(sse("content_block_start", {"type": "content_block_start", "index": 0,
                        "content_block": {"type": "text", "text": ""}}))
                    self.wfile.write(sse("content_block_delta", {"type": "content_block_delta", "index": 0,
                        "delta": {"type": "text_delta", "text": "Probe complete."}}))
                    self.wfile.write(sse("content_block_stop", {"type": "content_block_stop", "index": 0}))
                    reason = "end_turn"
                self.wfile.write(sse("message_delta", {"type": "message_delta", "delta": {"stop_reason": reason,
                    "stop_sequence": None}, "usage": {"output_tokens": 10}}))
                self.wfile.write(sse("message_stop", {"type": "message_stop"}))
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        # A separately applied OS policy permits connections to this exact local
        # port only; no external service is reachable from the Claude subprocess.
        profile = f'(version 1)(allow default)(deny network*)(allow network-outbound (remote ip "localhost:{port}"))'
        # Verify the OS boundary before launching the CLI. No packet should be sent.
        boundary = subprocess.run(["/usr/bin/sandbox-exec", "-p", profile, "/usr/bin/python3", "-c",
            "import socket; s=socket.socket(); s.settimeout(2); print(s.connect_ex(('1.1.1.1',443)))"],
            capture_output=True, text=True, timeout=10)
        if boundary.returncode != 0 or boundary.stdout.strip() not in ("1", "13"):
            raise RuntimeError("Local-only network sandbox did not deny the external socket probe")
        env = {"HOME": os.environ["HOME"], "PATH": "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "en_US.UTF-8",
               "CLAUDE_CONFIG_DIR": str(runtime / "claude"), "XDG_CONFIG_HOME": str(runtime / "config"),
               "XDG_CACHE_HOME": str(runtime / "cache"), "XDG_DATA_HOME": str(runtime / "data"),
               "XDG_STATE_HOME": str(runtime / "state"), "ANTHROPIC_API_KEY": "fake-local-key",
               "ANTHROPIC_AUTH_TOKEN": "fake-local-token", "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{port}",
               "ANTHROPIC_MODEL": "muse-spark-1.3-contributor", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
               "DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1", "ENABLE_TOOL_SEARCH": "true", "NO_PROXY": "127.0.0.1,localhost"}
        command = ["/usr/bin/sandbox-exec", "-p", profile, args.claude, "-p", "Run the requested probe.",
                   "--restricted", "--disable-slash-commands", "--setting-sources", "user",
                   "--strict-mcp-config", "--settings", str(settings), "--add-dir", str(logs),
                   "--tools", "Edit,Write,Read,Glob,Grep,WebFetch,WebSearch,ToolSearch,ListMcpResourcesTool,ReadMcpResourceTool,LSP,WaitForMcpServers,CronList,ListAgents,TaskGet,TaskList",
                   "--permission-mode", "dontAsk", "--allowedTools",
                   "Read,Glob,Grep,WebFetch,WebSearch,ToolSearch,ListMcpResourcesTool,ReadMcpResourceTool,LSP,WaitForMcpServers,CronList,ListAgents,TaskGet,TaskList", "--disallowedTools",
                   "Bash,PowerShell,MultiEdit,NotebookEdit,Agent,Task,Skill,mcp__github_file_ops__commit_files,mcp__github_file_ops__delete_files",
                   "--max-turns", "20", "--output-format", "json"]
        try:
            process = subprocess.run(command, cwd=root, env=env, text=True, capture_output=True, timeout=50)
            status = {"exit_code": process.returncode, "stdout": process.stdout, "stderr": process.stderr}
        except subprocess.TimeoutExpired as error:
            status = {"timeout": True, "stdout": str(error.stdout or ""), "stderr": str(error.stderr or "")}
        finally:
            server.shutdown()
            server.server_close()
        results = {}
        for req in requests[1:]:
            for message in req.get("messages", []):
                for block in message.get("content", []) if isinstance(message.get("content"), list) else []:
                    if block.get("type") == "tool_result":
                        results[block.get("tool_use_id", "")] = block
        first = requests[0] if requests else {}
        tool_names = [tool.get("name") for tool in first.get("tools", [])]
        payload_text = json.dumps(requests)
        checks = {
            "docs_edit": (root / "docs/normal.md").read_text() == "UPDATED\n",
            "docs_write": (root / "docs/new.md").exists(),
            "outside_edit_denied": "NORMAL_TRACKED" in (root / "normal.txt").read_text(),
            "outside_write_denied": not (root / "outside.txt").exists(),
            "protected_write_denied": (root / "docs/CLAUDE.md").read_text() == "ORIGINAL\n",
            "secret_edit_denied": (root / "docs/.env.local").read_text() == "ORIGINAL\n",
            "native_read": "NORMAL_TRACKED" in str(results.get("toolu_normal_read", {})),
            "startup_isolated": PROJECT_MARKER not in payload_text and not marker.exists(),
        }
        report = {"checks": checks, "network_external_connect_errno": int(boundary.stdout.strip()), "cli_version": subprocess.check_output([args.claude, "--version"], text=True).strip(),
                  "local_requests": len(requests), "status": status, "tools_offered": tool_names,
                  "tool_schemas": first.get("tools", []),
                  "project_instruction_loaded": PROJECT_MARKER in payload_text,
                  "project_mcp_offered": any("probe_forbidden_mcp" in str(x) for x in tool_names),
                  "hook_or_mcp_executed": marker.exists(),
                  "normal_file_unchanged": (root / "normal.txt").read_text() == "NORMAL_TRACKED_PROBE_73f1\n",
                  "tool_results": results}
        text = json.dumps(report, indent=2)
        if args.json_output:
            args.json_output.write_text(text + "\n")
        print(text)
        if not requests or status.get("exit_code") != 0:
            return 1
        return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
