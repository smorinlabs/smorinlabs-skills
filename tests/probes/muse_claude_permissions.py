#!/usr/bin/env python3
"""Probe the installed Claude CLI using deterministic fake tool calls and loopback only.

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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--discover", action="store_true", help="Diagnostic: ask ToolSearch for deferred read-only tools")
    mode.add_argument("--web-probe", action="store_true", help="Diagnostic: request deferred web tools with only loopback reachable")
    mode.add_argument("--symlinks", action="store_true", help="Probe safe and protected directory symlinks")
    mode.add_argument("--data-fixtures", action="store_true", help="Probe exact tracked data-fixture exceptions")
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
        if args.data_fixtures:
            fixture_dir = root / "tests/fixtures"
            fixture_dir.mkdir(parents=True)
            for name in ("x.env.json", "x[1].env.json", "blocked.env.json", "x.env.yaml", "x.env.local", ".env.local"):
                (fixture_dir / name).write_text("PUBLIC_FIXTURE_MARKER\n")
            subprocess.run(["git", "-C", str(root), "add", "tests/fixtures/x.env.json",
                            ":(literal)tests/fixtures/x[1].env.json", "tests/fixtures/blocked.env.json"], check=True)
        subprocess.run(["git", "-C", str(root), "add", "normal.txt"], check=True)
        with (root / ".git/config").open("a") as f:
            f.write(f"\n[probe]\n    fake = {DENIED_READ_MARKER}\n")
        outside = base / "outside-marker.txt"
        outside.write_text(DENIED_READ_MARKER + "\n")
        state = runtime / "state.json"
        state.write_text(json.dumps({"fake": DENIED_READ_MARKER}))
        profile_dir = root / ".github/muse-ci"
        profile_dir.mkdir(parents=True)
        (profile_dir / "review-settings.json").write_bytes((TEMPLATES / ".github/muse-ci/review-settings.json").read_bytes())
        settings = runtime / "settings.json"
        helper = load_helper()
        if args.data_fixtures:
            source = json.loads((profile_dir / "review-settings.json").read_text())
            source["permissions"]["deny"].append("Read(**/blocked*)")
            profile = helper.configuration(root, "review", runtime, source=source, fixture_root=root)
        else:
            profile = helper.configuration(root, "review", runtime)
        settings.write_text(json.dumps(profile))
        logs = runtime.parent / "github-ci-logs"
        logs.mkdir()
        (logs / "job.log").write_text("ALLOWED_CI_LOG_PROBE\n")
        other_temp = runtime.parent / "other-marker.txt"
        other_temp.write_text(DENIED_READ_MARKER + "\n")
        if args.symlinks:
            (root / "safe_alias").symlink_to(root / "nested", target_is_directory=True)
            (root / "outside_alias").symlink_to(base, target_is_directory=True)
            (root / "git_alias").symlink_to(root / ".git", target_is_directory=True)
            (root / "runtime_alias").symlink_to(runtime, target_is_directory=True)
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
            ("normal_read", "Read", {"file_path": str(root / "nested/normal.txt")}),
            ("git_read", "Read", {"file_path": str(root / ".git/config")}),
            ("outside_read", "Read", {"file_path": str(outside)}),
            ("runtime_state_read", "Read", {"file_path": str(state)}),
            ("runtime_settings_read", "Read", {"file_path": str(settings)}),
            ("normal_search", "Grep", {"pattern": "NORMAL_TRACKED_PROBE", "path": str(root / "normal.txt")}),
            ("git_search", "Grep", {"pattern": DENIED_READ_MARKER, "path": str(root / ".git")}),
            ("ci_log_read", "Read", {"file_path": str(logs / "job.log")}),
            ("other_temp_read", "Read", {"file_path": str(other_temp)}),
            ("shell", "Bash", {"command": f"touch {marker}"}),
            ("edit", "Edit", {"file_path": str(root / "normal.txt"), "old_string": "NORMAL_TRACKED", "new_string": "MODIFIED"}),
        ]
        if args.data_fixtures:
            calls = [
                ("fixture_read", "Read", {"file_path": str(fixture_dir / "x.env.json")}),
                ("fixture_search", "Grep", {"pattern": "PUBLIC_FIXTURE_MARKER", "path": str(fixture_dir / "x.env.json")}),
                ("fixture_escaped_read", "Read", {"file_path": str(fixture_dir / "x[1].env.json")}),
                ("fixture_untracked_read", "Read", {"file_path": str(fixture_dir / "x.env.yaml")}),
                ("fixture_custom_denied", "Read", {"file_path": str(fixture_dir / "blocked.env.json")}),
                ("fixture_dotenv_denied", "Read", {"file_path": str(fixture_dir / ".env.local")}),
                ("fixture_named_env_denied", "Read", {"file_path": str(fixture_dir / "x.env.local")}),
                ("fixture_parent_search", "Grep", {"pattern": "PUBLIC_FIXTURE_MARKER", "path": str(fixture_dir)}),
            ]
        if args.symlinks:
            calls = [
                ("safe_link_read", "Read", {"file_path": str(root / "safe_alias/normal.txt")}),
                ("safe_link_search", "Grep", {"pattern": "NORMAL_TRACKED_PROBE", "path": str(root / "safe_alias")}),
                ("outside_link_read", "Read", {"file_path": str(root / "outside_alias/outside-marker.txt")}),
                ("git_link_read", "Read", {"file_path": str(root / "git_alias/config")}),
                ("runtime_link_read", "Read", {"file_path": str(root / "runtime_alias/state.json")}),
                ("outside_link_search", "Grep", {"pattern": DENIED_READ_MARKER, "path": str(root / "outside_alias/outside-marker.txt")}),
                ("git_link_search", "Grep", {"pattern": DENIED_READ_MARKER, "path": str(root / "git_alias")}),
                ("runtime_link_search", "Grep", {"pattern": DENIED_READ_MARKER, "path": str(root / "runtime_alias")}),
            ]
        if args.web_probe:
            calls = [("discover", "ToolSearch", {"query": "select:WebFetch,WebSearch"})]
        if args.discover:
            calls = [("discover", "ToolSearch", {"query": "select:WebFetch,WebSearch,ListMcpResourcesTool,ReadMcpResourceTool,LSP,WaitForMcpServers,CronList,ListAgents,TaskGet,TaskList", "max_results": 100})]
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
                if len(requests) == 1 or (args.web_probe and len(requests) == 2):
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
                   "--tools", "Read,Glob,Grep,WebFetch,WebSearch,ToolSearch,ListMcpResourcesTool,ReadMcpResourceTool,LSP,WaitForMcpServers,CronList,ListAgents,TaskGet,TaskList",
                   "--permission-mode", "default", "--allowedTools",
                   "Read,Glob,Grep,WebFetch,WebSearch,ToolSearch,ListMcpResourcesTool,ReadMcpResourceTool,LSP,WaitForMcpServers,CronList,ListAgents,TaskGet,TaskList,mcp__github_inline_comment__create_inline_comment", "--disallowedTools",
                   "Bash,PowerShell,Edit,Write,MultiEdit,NotebookEdit,Agent,Task,Skill,mcp__github_file_ops__commit_files,mcp__github_file_ops__delete_files",
                   "--max-turns", "12", "--output-format", "json"]
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
            "required_tools_offered": all(name in tool_names for name in ("Read", "Glob", "Grep", "ToolSearch")),
            "normal_read": "NORMAL_TRACKED_PROBE_73f1" in str(results.get("toolu_normal_read", {})),
            "protected_reads_denied": all(results.get("toolu_" + name, {}).get("is_error") is True
                                          for name in ("git_read", "outside_read", "runtime_state_read", "runtime_settings_read")),
            "ci_log_read": "ALLOWED_CI_LOG_PROBE" in str(results.get("toolu_ci_log_read", {})),
            "other_temp_read_denied": results.get("toolu_other_temp_read", {}).get("is_error") is True,
            "search_baseline_available": "normal.txt" in str(results.get("toolu_normal_search", {})) and not results.get("toolu_normal_search", {}).get("is_error", False),
            "protected_search_denied": all(results.get("toolu_" + name, {}).get("is_error") is True
                                           and "No such tool available" not in str(results.get("toolu_" + name, {}))
                                           for name in ("git_search",)),
            "shell_and_edit_unavailable": all(results.get("toolu_" + name, {}).get("is_error") is True
                                              for name in ("shell", "edit")),
            "protected_values_not_returned": DENIED_READ_MARKER not in json.dumps(results),
            "startup_isolated": PROJECT_MARKER not in payload_text and not marker.exists()
                                and not any("probe_forbidden_mcp" in str(x) for x in tool_names),
            "normal_file_unchanged": (root / "normal.txt").read_text() == "NORMAL_TRACKED_PROBE_73f1\n",
        }
        if args.data_fixtures:
            checks = {
                "tracked_fixture_read": "PUBLIC_FIXTURE_MARKER" in str(results.get("toolu_fixture_read", {})),
                "tracked_fixture_search": "x.env.json" in str(results.get("toolu_fixture_search", {})) and not results.get("toolu_fixture_search", {}).get("is_error", False),
                "escaped_fixture_read": "PUBLIC_FIXTURE_MARKER" in str(results.get("toolu_fixture_escaped_read", {})),
                "untracked_and_custom_denied": all(results.get("toolu_" + name, {}).get("is_error") is True for name in ("fixture_untracked_read", "fixture_custom_denied")),
                "credential_names_denied": all(results.get("toolu_" + name, {}).get("is_error") is True for name in ("fixture_dotenv_denied", "fixture_named_env_denied")),
                "startup_isolated": PROJECT_MARKER not in payload_text and not marker.exists(),
            }
        if args.symlinks:
            checks = {
                "safe_link_read": "NORMAL_TRACKED_PROBE_73f1" in str(results.get("toolu_safe_link_read", {})),
                "safe_link_search": "normal.txt" in str(results.get("toolu_safe_link_search", {})) and not results.get("toolu_safe_link_search", {}).get("is_error", False),
                "protected_link_reads_denied": all(results.get("toolu_" + name, {}).get("is_error") is True for name in
                    ("outside_link_read", "git_link_read", "runtime_link_read")),
                "protected_link_searches_denied": all(results.get("toolu_" + name, {}).get("is_error") is True for name in
                    ("outside_link_search", "git_link_search", "runtime_link_search")),
                "protected_values_not_returned": DENIED_READ_MARKER not in json.dumps(results),
                "startup_isolated": PROJECT_MARKER not in payload_text and not marker.exists()
                    and not any("probe_forbidden_mcp" in str(x) for x in tool_names),
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
        if args.web_probe:
            return 0 if all("toolu_" + name in results for name in ("discover", "web_fetch", "web_search")) else 1
        if args.discover:
            return 0 if "toolu_discover" in results else 1
        return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
