/** Exercise the unmodified pinned Action parser against generated workflow args.
 * Usage: bun tests/probes/muse_action_parser.ts /absolute/path/parse-sdk-options.ts /absolute/path/cases.json
 */
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

const [parserPath, casesPath] = process.argv.slice(2);
if (!parserPath || !casesPath) throw new Error("Expected pinned parser path and extracted workflow cases");
const { parseSdkOptions } = await import(pathToFileURL(parserPath).href);
const cases = JSON.parse(await readFile(casesPath, "utf8"));
const settings = "/private/tmp/muse parser fixture/settings.json";
const logs = "/private/tmp/muse parser fixture/github-ci-logs";
const safeConfig = JSON.stringify({mcpServers: {github_comment: {command: "/usr/bin/false"}, github_ci: {command: "/usr/bin/false"}, github_inline_comment: {command: "/usr/bin/false"}}});
const actionRoot = "/action";
const baseTools = ["Glob", "Grep", "LS", "Read", "mcp__github_comment__update_claude_comment",
  "mcp__github_ci__get_ci_status", "mcp__github_ci__get_workflow_run_details", "mcp__github_ci__download_job_log",
  "mcp__github_inline_comment__create_inline_comment",
  ...["git-add", "git-commit", "git-push", "git-rm"].map(n => `Bash(${actionRoot}/scripts/${n}.sh:*)`)];
const readonly = ["Read", "Glob", "Grep", "WebFetch", "WebSearch", "ToolSearch", "ListMcpResourcesTool", "ReadMcpResourceTool", "LSP", "WaitForMcpServers", "CronList", "ListAgents", "TaskGet", "TaskList"];
const denied = ["Bash", "PowerShell", "Edit", "Write", "MultiEdit", "NotebookEdit", "Agent", "Task", "Skill", "mcp__github_file_ops__commit_files", "mcp__github_file_ops__delete_files"];
for (const [name, original] of Object.entries(cases) as [string, string][]) {
  const user = original.replaceAll("${{ steps.prepare.outputs.settings }}", settings)
                       .replaceAll("${{ steps.prepare.outputs.ci_logs }}", logs);
  assert(!user.includes("${{"), `${name}: unexpected unresolved expression`);
  for (const mode of ["auto", "acceptEdits"]) {
    // This is the construction in src/modes/tag/index.ts for no API commit signing.
    const tag = `--mcp-config '${safeConfig}' --permission-mode ${mode} --allowedTools "${baseTools.join(",")}"`;
    const parsed = parseSdkOptions({claudeArgs: `${tag} ${user}`});
    const sdk = parsed.sdkOptions;
    assert.equal(sdk.extraArgs["permission-mode"], "default", `${name}: final mode`);
    assert.deepEqual(sdk.settingSources, ["user"]);
    for (const flag of ["restricted", "disable-slash-commands", "strict-mcp-config"]) assert(flag in sdk.extraArgs, `${name}: ${flag}`);
    assert.equal(sdk.extraArgs.settings, settings);
    assert.deepEqual(sdk.additionalDirectories, [logs]);
    assert.deepEqual(sdk.extraArgs.tools.split(","), readonly);
    for (const item of [...readonly, ...baseTools]) assert(sdk.allowedTools.includes(item), `${name}: missing allowed ${item}`);
    for (const item of denied) assert(sdk.disallowedTools.includes(item), `${name}: missing denied ${item}`);
    assert.deepEqual(JSON.parse(sdk.extraArgs["mcp-config"]), JSON.parse(safeConfig));
    assert.equal(sdk.maxTurns, 12);
    assert(!("allowedTools" in sdk.extraArgs) && !("disallowedTools" in sdk.extraArgs));
    // The parser forwards permission mode in extraArgs, not sdkOptions.permissionMode.
    assert.equal(sdk.permissionMode, undefined);
    console.log(`${name} with tag mode ${mode}: PASS`);
  }
}
