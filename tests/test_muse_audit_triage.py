"""Offline verification of trusted audit triage and pre-publication guards."""
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parents[1] / 'plugins/muse-github/skills/muse-github-setup/templates/.github'

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

triage = load('test_muse_audit', TEMPLATES / 'scripts/muse_audit_triage.py')
guard = load('test_muse_guard', TEMPLATES / 'scripts/muse_ci.py')


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    root = tmp_path / 'repo'
    root.mkdir()
    git(root, 'init', '-q', '-b', 'main')
    git(root, 'config', 'user.name', 'Fixture')
    git(root, 'config', 'user.email', 'fixture@example.invalid')
    (root / 'docs').mkdir()
    (root / 'docs/guide.md').write_text('before\n')
    (root / 'app.txt').write_text('before\n')
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'initial')
    base = git(root, 'rev-parse', 'HEAD')
    git(root, 'checkout', '-qb', 'bot/weekly-audit-12')
    state = tmp_path / 'state.json'
    state.write_text(json.dumps({'base': base, 'branch': 'bot/weekly-audit-12'}))
    output = tmp_path / 'output'
    monkeypatch.setattr(triage, 'guard_module', lambda: guard)
    execution = tmp_path / 'execution.json'
    execution.write_text(json.dumps([{'type': 'result', 'subtype': 'success', 'is_error': False}]))
    env = {'MUSE_EXECUTION_FILE': str(execution), 'GITHUB_WORKSPACE': str(root), 'MUSE_TRIAGE_STATE': str(state),
           'MUSE_ACTION_OUTCOME': 'success', 'MUSE_ACTION_CONCLUSION': 'success',
           'GITHUB_OUTPUT': str(output)}
    return root, env, output


def test_validate_stages_only_literal_docs_paths(prepared):
    root, env, output = prepared
    (root / 'docs/guide.md').write_text('after\n')
    (root / 'docs/[new].md').write_text('new\n')
    triage.validate(env)
    assert set(git(root, 'diff', '--cached', '--name-only').splitlines()) == {'docs/guide.md', 'docs/[new].md'}
    assert 'true' in output.read_text()


@pytest.mark.parametrize('kind', ['outcome', 'conclusion', 'outside', 'protected', 'credential', 'symlink', 'staged'])
def test_validate_refuses_unsafe_changes_before_staging(prepared, kind):
    root, env, _ = prepared
    (root / 'docs/guide.md').write_text('after\n')
    if kind in ('outcome', 'conclusion'):
        env['MUSE_ACTION_' + kind.upper()] = 'failure'
    elif kind == 'outside':
        (root / 'app.txt').write_text('changed\n')
    elif kind == 'protected':
        (root / 'docs/CLAUDE.md').write_text('changed\n')
    elif kind == 'credential':
        (root / 'docs/.env.local').write_text('public marker\n')
    elif kind == 'symlink':
        (root / 'docs/alias').symlink_to(root / 'app.txt')
    else:
        git(root, 'add', 'docs/guide.md')
    with pytest.raises(triage.RefusalError):
        triage.validate(env)
    if kind != 'staged':
        assert git(root, 'diff', '--cached', '--name-only') == ''


def test_no_changes_reports_no_publication(prepared):
    _, env, output = prepared
    triage.validate(env)
    assert 'false' in output.read_text()


@pytest.mark.parametrize("ref_state", ["none", "similar", "existing", "malformed"])
def test_prepare_freezes_historical_audited_revision_using_current_trusted_code(tmp_path, monkeypatch, ref_state):
    root = tmp_path / 'repo'
    root.mkdir()
    git(root, 'init', '-q', '-b', 'main')
    git(root, 'config', 'user.name', 'Fixture')
    git(root, 'config', 'user.email', 'fixture@example.invalid')
    (root / 'docs').mkdir()
    (root / 'docs/readme.md').write_text('historical\n')
    legacy = root / '.opencode/audit-triage'
    legacy.mkdir(parents=True)
    (legacy / 'policy.json').write_text(json.dumps({'schema_version': 1, 'organization': 'org', 'model': 'model_api/muse-spark-1.3-contributor'}))
    (legacy / 'triage.json').write_text('{}')
    old_scripts = root / '.github/scripts'
    old_scripts.mkdir(parents=True)
    (old_scripts / 'audit_triage.py').write_text('# never executed\n')
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'audit target')
    base = git(root, 'rev-parse', 'HEAD')
    config = root / '.github/muse-audit-triage'
    scripts = root / '.github/scripts'
    config.mkdir(parents=True)
    scripts.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(TEMPLATES / 'scripts/muse_ci.py', config / 'runtime.py')
    shutil.copyfile(TEMPLATES / 'scripts/muse_audit_triage.py', scripts / 'muse_audit_triage.py')
    shutil.copyfile(TEMPLATES / 'muse-audit-triage/triage-settings.json', config / 'triage-settings.json')
    (config / 'policy.json').write_text(json.dumps({'schema_version': 2, 'organization': 'org', 'model': 'muse-spark-1.3-contributor', 'max_findings_bytes': 20000}))
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'trusted tooling')
    current = git(root, 'rev-parse', 'HEAD')
    git(root, 'update-ref', 'refs/remotes/origin/main', current)
    event = {'repository': {'full_name': 'org/repo', 'default_branch': 'main', 'owner': {'type': 'Organization', 'login': 'org'}},
             'workflow_run': {'id': 12, 'name': 'weekly-audit', 'conclusion': 'failure', 'event': 'schedule', 'head_branch': 'main', 'head_sha': base}}
    eventfile = tmp_path / 'event.json'
    eventfile.write_text(json.dumps(event))
    calls, downloads = [], []
    class API:
        def get(self, path):
            calls.append(path)
            if '/pulls?' in path: return []
            if '/git/matching-refs/' in path:
                if ref_state == 'existing': return [{'ref': 'refs/heads/bot/weekly-audit-12'}]
                if ref_state == 'similar': return [{'ref': 'refs/heads/bot/weekly-audit-120'}]
                if ref_state == 'malformed': return {'error': 'unexpected'}
                return []
            if '/jobs?' in path:
                return {'jobs': [{'id': i, 'name': f'other-{i}', 'conclusion': 'failure'} for i in range(1, 6)] +
                                [{'id': 20, 'name': 'docs-linkcheck', 'conclusion': 'failure'}]}
            raise AssertionError(path)
    monkeypatch.setattr(triage, 'GitHub', lambda token: API())
    def download(url, *args):
        downloads.append(url)
        return '(x: line 1) broken https://example.invalid - 404'
    monkeypatch.setattr(triage, 'download_logs', download)
    monkeypatch.setattr(triage, 'guard_module', lambda: guard)
    monkeypatch.setattr(triage, '__file__', str(scripts / 'muse_audit_triage.py'))
    runner = tmp_path / 'runner'
    runner.mkdir()
    out, environment = tmp_path / 'output', tmp_path / 'environment'
    env = {'GITHUB_WORKSPACE': str(root), 'GITHUB_EVENT_NAME': 'workflow_run', 'GITHUB_EVENT_PATH': str(eventfile),
           'GITHUB_REPOSITORY': 'org/repo', 'MUSE_TRIAGE_TRUSTED_SHA': current, 'RUNNER_TEMP': str(runner),
           'GITHUB_OUTPUT': str(out), 'GITHUB_ENV': str(environment)}
    if ref_state in ('existing', 'malformed'):
        with pytest.raises(triage.RefusalError, match='already exists|verify existing triage branches'):
            triage.prepare(env)
        assert not downloads and not any('/jobs?' in path for path in calls)
        assert not list(runner.iterdir())
        assert git(root, 'rev-parse', 'HEAD') == current
        return
    triage.prepare(env)
    assert len(downloads) == 5 and '/jobs/20/logs' in downloads[0]
    assert git(root, 'rev-parse', 'HEAD') == base
    state_paths = list(runner.glob('audit-triage-*/state.json'))
    state = json.loads(state_paths[0].read_text())
    assert state['checkout_sha'] == current and state['base'] == base
    assert 'muse-spark-1.3-contributor' in out.read_text()
    settings = json.loads(state_paths[0].with_name('settings.json').read_text())
    assert settings['permissions']['defaultMode'] == 'dontAsk'
    assert any(rule.startswith('Edit(//') and rule.endswith('/docs/**)') for rule in settings['permissions']['allow'])
    assert 'Edit' not in settings['permissions']['allow']


def test_validate_accepts_only_exact_forward_action_restoration(prepared):
    root, env, _ = prepared
    branch = git(root, 'branch', '--show-current')
    git(root, 'checkout', '-q', 'main')
    (root / 'CLAUDE.md').write_text('trusted current guidance\n')
    git(root, 'add', 'CLAUDE.md')
    git(root, 'commit', '-qm', 'trusted guidance')
    current = git(root, 'rev-parse', 'HEAD')
    git(root, 'update-ref', 'refs/remotes/origin/main', current)
    git(root, 'checkout', '-q', branch)
    state_path = Path(env['MUSE_TRIAGE_STATE'])
    state = json.loads(state_path.read_text())
    state.update(checkout_sha=current, default_branch='main')
    state_path.write_text(json.dumps(state))
    (root / 'CLAUDE.md').write_text('trusted current guidance\n')
    (root / 'docs/guide.md').write_text('after\n')
    triage.validate(env)
    assert git(root, 'diff', '--cached', '--name-only') == 'docs/guide.md'
    assert (root / 'CLAUDE.md').read_text() == 'trusted current guidance\n'


def test_validate_rejects_modified_action_restoration_before_stage(prepared):
    root, env, _ = prepared
    branch = git(root, 'branch', '--show-current')
    git(root, 'checkout', '-q', 'main')
    (root / 'CLAUDE.md').write_text('trusted guidance\n')
    git(root, 'add', 'CLAUDE.md')
    git(root, 'commit', '-qm', 'trusted guidance')
    current = git(root, 'rev-parse', 'HEAD')
    git(root, 'update-ref', 'refs/remotes/origin/main', current)
    git(root, 'checkout', '-q', branch)
    state_path = Path(env['MUSE_TRIAGE_STATE'])
    state = json.loads(state_path.read_text())
    state.update(checkout_sha=current, default_branch='main')
    state_path.write_text(json.dumps(state))
    (root / 'CLAUDE.md').write_text('tampered\n')
    (root / 'docs/guide.md').write_text('after\n')
    with pytest.raises(triage.RefusalError, match='restoration'):
        triage.validate(env)
    assert git(root, 'diff', '--cached', '--name-only') == ''


def test_failed_terminal_sdk_result_never_stages(prepared):
    root, env, _ = prepared
    (root / 'docs/guide.md').write_text('after\n')
    Path(env['MUSE_EXECUTION_FILE']).write_text(json.dumps([{'type': 'result', 'subtype': 'error_max_turns', 'is_error': True}]))
    with pytest.raises(triage.RefusalError, match='terminal result'):
        triage.validate(env)
    assert git(root, 'diff', '--cached', '--name-only') == ''


def test_audited_policy_rejects_missing_tooling_and_tier_change(tmp_path):
    root = tmp_path / 'repo'
    root.mkdir()
    git(root, 'init', '-q', '-b', 'main')
    git(root, 'config', 'user.name', 'Fixture')
    git(root, 'config', 'user.email', 'fixture@example.invalid')
    (root / 'README').write_text('initial')
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'initial')
    initial = git(root, 'rev-parse', 'HEAD')
    with pytest.raises(triage.RefusalError, match='predates'):
        triage.validate_audited_policy(root, initial, 'muse-spark-1.3-contributor', 'org')
    legacy = root / '.opencode/audit-triage'
    legacy.mkdir(parents=True)
    (legacy / 'policy.json').write_text(json.dumps({'schema_version': 1, 'organization': 'org', 'model': 'model_api/muse-spark-1.3'}))
    (legacy / 'triage.json').write_text('{}')
    (root / '.github/scripts').mkdir(parents=True)
    (root / '.github/scripts/audit_triage.py').write_text('# old')
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'old tier')
    old = git(root, 'rev-parse', 'HEAD')
    with pytest.raises(triage.RefusalError, match='different model'):
        triage.validate_audited_policy(root, old, 'muse-spark-1.3-contributor', 'org')
    triage.validate_audited_policy(root, old, 'muse-spark-1.3', 'org')


def test_guard_loading_does_not_write_bytecode_into_trusted_checkout(tmp_path, monkeypatch):
    scripts = tmp_path / '.github/scripts'
    config = tmp_path / '.github/muse-audit-triage'
    scripts.mkdir(parents=True)
    config.mkdir(parents=True)
    shutil.copyfile(TEMPLATES / 'scripts/muse_ci.py', config / 'runtime.py')
    monkeypatch.setattr(triage, '__file__', str(scripts / 'muse_audit_triage.py'))
    triage.guard_module.cache_clear()
    try:
        loaded = triage.guard_module()
        assert loaded.READ_TOOLS
        assert not (config / '__pycache__').exists()
    finally:
        triage.guard_module.cache_clear()


def test_installed_helper_never_loads_unrelated_sibling_runtime(tmp_path, monkeypatch):
    scripts = tmp_path / '.github/scripts'
    config = tmp_path / '.github/muse-audit-triage'
    scripts.mkdir(parents=True)
    config.mkdir(parents=True)
    (scripts / 'runtime.py').write_text('raise AssertionError("unrelated sibling executed")\n')
    (config / 'runtime.py').write_text('SOURCE = "managed"\n')
    monkeypatch.setattr(triage, '__file__', str(scripts / 'muse_audit_triage.py'))
    triage.guard_module.cache_clear()
    try:
        assert triage.guard_module().SOURCE == 'managed'
        (config / 'runtime.py').unlink()
        triage.guard_module.cache_clear()
        with pytest.raises(OSError):
            triage.guard_module()
    finally:
        triage.guard_module.cache_clear()


def test_copied_private_helper_loads_sibling_runtime(tmp_path, monkeypatch):
    private = tmp_path / ('audit-triage-' + 'a' * 32)
    private.mkdir()
    (private / 'runtime.py').write_text('SOURCE = "copied"\n')
    monkeypatch.setattr(triage, '__file__', str(private / 'muse_audit_triage.py'))
    triage.guard_module.cache_clear()
    try:
        assert triage.guard_module().SOURCE == 'copied'
    finally:
        triage.guard_module.cache_clear()
