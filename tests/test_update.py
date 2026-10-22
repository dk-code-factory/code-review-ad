import json
import shutil
import pytest
from update_fixtures import Fixture


@pytest.mark.parametrize('host',['codex','claude'])
@pytest.mark.parametrize('mode',['notify','auto','off'])
def test_nested_plugins_defer_until_outer_completes(tmp_path,host,mode):
    f=Fixture(tmp_path,'nested',mode,host)
    outer=f.invoke();inner=f.invoke('code-review-qodo',parent=outer['token'])
    assert f.invoke('code-review-qodo','complete',token=inner['token'])['status']=='deferred'
    assert not [a for a in f.calls if a[1:3] in (['plugin','add'],['plugin','update'])]
    done=f.invoke(phase='complete',token=outer['token'])
    assert len(done['updates'])==(2 if mode=='auto' else 0)
    assert all(u['reload_required'] for u in done['updates'])
    assert len(f.network)==(0 if mode=='off' else 2)


def test_parallel_outer_invocations_also_defer(tmp_path):
    f=Fixture(tmp_path,'parallel','auto')
    one=f.invoke();two=f.invoke();inner=f.invoke('code-review-qodo',parent=two['token'])
    assert f.invoke(phase='complete',token=one['token'])['status']=='deferred'
    assert f.invoke(phase='complete',token=two['token'])['status']=='deferred'
    done=f.invoke('code-review-qodo','complete',token=inner['token'])
    assert len(done['updates'])==2
    assert not f.invoke(phase='complete',token=one['token'])['updates']


def test_completion_failure_preserves_earlier_success_and_state(tmp_path):
    f=Fixture(tmp_path,'failure','auto');outer=f.invoke();inner=f.invoke('code-review-qodo',parent=outer['token'])
    f.invoke('code-review-qodo','complete',token=inner['token'])
    f.records.append(dict(f.records[1],scope='project'))
    done=f.invoke(phase='complete',token=outer['token'])
    assert [u['status'] for u in done['updates']]==['updated','update_failed']
    assert done['updates'][0]['reload_required'] is True
    assert f.state()['invocations'][outer['token']]['complete'] is True


def test_cache_deduplicates_notices_and_checks(tmp_path):
    f=Fixture(tmp_path,'cache');one=f.invoke();f.invoke(phase='complete',token=one['token']);two=f.invoke()
    assert one['action']=='notify' and two['action']=='continue'
    assert len(f.network)==1
    state=f.state();state['checks']['dk-code-factory/dk-workflows']['checked']-=86401
    (f.base/'state/dk-code-factory/updates/state.json').write_text(json.dumps(state))
    f.invoke();assert len(f.network)==2


def test_offline_operation_is_nonblocking_and_cached(tmp_path):
    f=Fixture(tmp_path,'offline')
    def offline(*a,**kw):f.network.append('offline');raise OSError('offline')
    f.urlopen=offline
    one=f.invoke();two=f.invoke()
    assert one['status']==two['status']=='offline' and one['token']
    assert len(f.network)==1
    assert f.invoke(phase='complete',token=one['token'])['status']=='deferred'


@pytest.mark.parametrize('tag', ['v01.2.3', 'v1.02.3', 'v1.2.03', 'v١.2.3'])
def test_non_semver_release_is_unavailable_and_never_auto_installed(tmp_path, tag):
    import io

    f = Fixture(tmp_path, 'invalid-release', 'auto')

    def invalid_release(request, **kwargs):
        f.network.append(request.full_url)
        return io.StringIO(json.dumps({'tag_name': tag, 'draft': False, 'prerelease': False}))

    f.urlopen = invalid_release
    first = f.invoke()
    second = f.invoke()
    assert first['status'] == second['status'] == 'offline'
    assert len(f.network) == 1
    assert f.invoke(phase='complete', token=first['token'])['status'] == 'deferred'
    assert f.invoke(phase='complete', token=second['token'])['updates'] == []
    assert not [call for call in f.calls if call[1:3] == ['plugin', 'add']]


@pytest.mark.parametrize('failure', ['host-offline', 'host-invalid', 'config-invalid', 'version-invalid'])
def test_optional_entry_failure_still_defers_updates_until_completion(tmp_path, failure):
    import subprocess

    f = Fixture(tmp_path, 'entry-failure', 'auto')
    outer = f.invoke()
    original = f.subrun
    config = f.base / 'config/dk-code-factory/updates.json'

    def unavailable(argv, **kwargs):
        if argv[:3] == ['codex', 'plugin', 'list']:
            if failure == 'host-offline':
                raise OSError('Host unavailable')
            return subprocess.CompletedProcess(argv, 0, 'null', '')
        return original(argv, **kwargs)

    if failure.startswith('host-'):
        f.subrun = unavailable
    elif failure == 'config-invalid':
        config.write_text('{')
    else:
        f.records[0]['version'] = 'unknown'
    inner = f.invoke()
    assert inner['status'] == 'unavailable'
    assert inner['non_blocking'] is True
    assert inner['token'] in f.state()['invocations']
    f.subrun = original
    config.write_text('{"mode":"auto"}')
    f.records[0]['version'] = '1.0.0'
    assert f.invoke(phase='complete', token=outer['token'])['status'] == 'deferred'
    assert not [call for call in f.calls if call[1:3] == ['plugin', 'add']]
    done = f.invoke(phase='complete', token=inner['token'])
    assert done['updates'][0]['status'] == 'updated'


@pytest.mark.parametrize('config', ['{', '{"mode":"invalid"}', '{"plugins":null}'])
def test_invalid_configuration_does_not_strand_completion_or_install(tmp_path, config):
    f = Fixture(tmp_path, 'completion-config', 'auto')
    entry = f.invoke()
    (f.base / 'config/dk-code-factory/updates.json').write_text(config)
    done = f.invoke(phase='complete', token=entry['token'])
    assert done['status'] == 'completed'
    assert done['updates'][0]['status'] == 'update_failed'
    assert f.state()['invocations'][entry['token']]['complete'] is True
    assert not [call for call in f.calls if call[1:3] == ['plugin', 'add']]


@pytest.mark.parametrize('cache', [None, {'checked': 'invalid', 'version': '1.1.0'},
                                 {'checked': 1e100, 'version': '1.1.0'},
                                 {}, {'version': 'invalid'}, {'version': None}])
def test_invalid_release_cache_is_refreshed_without_losing_entry_token(tmp_path, cache):
    f = Fixture(tmp_path, 'invalid-cache', 'auto')
    entry = f.invoke()
    state = f.state()
    if isinstance(cache, dict) and 'checked' not in cache:
        cache['checked'] = state['checks']['dk-code-factory/dk-workflows']['checked']
    state['checks']['dk-code-factory/dk-workflows'] = cache
    (f.base / 'state/dk-code-factory/updates/state.json').write_text(json.dumps(state))
    other = f.invoke()
    assert other['status'] == 'deferred'
    assert other['token'] in f.state()['invocations']
    assert len(f.network) == 2


def test_pinned_version_does_not_update(tmp_path):
    f=Fixture(tmp_path,'pin','auto');f.records[0]['source']['ref']='v1.0.0'
    one=f.invoke();assert one['status']=='pinned'
    assert not f.invoke(phase='complete',token=one['token'])['updates']


def test_policy_change_cancels_pending_update(tmp_path):
    f=Fixture(tmp_path,'policy','auto');one=f.invoke()
    (f.base/'config/dk-code-factory/updates.json').write_text('{"mode":"off"}')
    assert not f.invoke(phase='complete',token=one['token'])['updates']


def test_plugin_override_does_not_install_other_plugin(tmp_path):
    f=Fixture(tmp_path,'override','auto')
    (f.base/'config/dk-code-factory/updates.json').write_text('{"mode":"auto","plugins":{"code-review-qodo":"off"}}')
    one=f.invoke();two=f.invoke('code-review-qodo',parent=one['token'])
    f.invoke('code-review-qodo','complete',token=two['token'])
    assert [u['plugin'] for u in f.invoke(phase='complete',token=one['token'])['updates']]==['dk-workflows']


def test_uncertain_host_update_cannot_claim_success(tmp_path):
    f=Fixture(tmp_path,'uncertain','auto');one=f.invoke();original=f.subrun
    def unchanged(argv,**kwargs):
        if argv[1:3]==['plugin','add']:
            import subprocess
            return subprocess.CompletedProcess(argv,0,'','')
        return original(argv,**kwargs)
    f.subrun=unchanged
    done=f.invoke(phase='complete',token=one['token'])
    assert done['updates'][0]['status']=='update_failed'


@pytest.mark.parametrize('changed', [{'installed': False}, {'scope': 'project'}])
def test_codex_verification_requires_installed_record_in_requested_scope(tmp_path, changed):
    f = Fixture(tmp_path, 'final-verification', 'auto')
    entry = f.invoke()
    original = f.subrun

    def changed_record(argv, **kwargs):
        result = original(argv, **kwargs)
        if argv[:3] == ['codex', 'plugin', 'add']:
            f.records[0].update(changed)
        return result

    f.subrun = changed_record
    done = f.invoke(phase='complete', token=entry['token'])
    assert done['updates'][0]['status'] == 'update_failed'
    assert 'did not confirm' in done['updates'][0]['message']


def test_codex_verification_ignores_uninstalled_duplicate(tmp_path):
    f = Fixture(tmp_path, 'uninstalled-duplicate', 'auto')
    entry = f.invoke()
    original = f.subrun

    def duplicate_record(argv, **kwargs):
        result = original(argv, **kwargs)
        if argv[:3] == ['codex', 'plugin', 'add']:
            f.records.append(dict(f.records[0], installed=False))
        return result

    f.subrun = duplicate_record
    done = f.invoke(phase='complete', token=entry['token'])
    assert done['updates'][0]['status'] == 'updated'


def test_already_newer_installation_is_not_reinstalled(tmp_path):
    f=Fixture(tmp_path,'newer','auto');one=f.invoke();f.records[0]['version']='2.0.0'
    done=f.invoke(phase='complete',token=one['token'])
    assert done['updates'][0]['status']=='current'
    assert not [a for a in f.calls if a[1:3]==['plugin','add']]


def test_local_entry_in_remote_marketplace_can_auto_update(tmp_path):
    f=Fixture(tmp_path,'remote','auto')
    f.records[0]['source']={'source':'local','path':'./'}
    f.records[0]['marketplaceSource']={'sourceType':'git','source':'https://github.com/dk-code-factory/dk-workflows.git','ref':'main'}
    one=f.invoke();assert one['status']=='deferred'
    assert f.invoke(phase='complete',token=one['token'])['updates'][0]['status']=='updated'


@pytest.mark.parametrize('has_install_path', [True, False])
def test_codex_local_checkout_does_not_borrow_registered_identity(tmp_path, has_install_path):
    f = Fixture(tmp_path, 'checkout', 'auto')
    if has_install_path:
        f.records[0]['installPath'] = str(f.base / 'another-installed-copy')
    else:
        del f.records[0]['installPath']
    f.env['CODEX_HOME'] = str(f.base / 'codex')
    one = f.invoke()
    assert one['status'] == 'pinned'
    assert one['identity']['marketplace'] is None
    assert not f.invoke(phase='complete', token=one['token'])['updates']
    assert not [call for call in f.calls if call[1:3] == ['plugin', 'add']]


@pytest.mark.parametrize('registered_version', ['1.0.0', '1.1.0'])
def test_codex_cache_identity_without_install_path(tmp_path, monkeypatch, registered_version):
    f = Fixture(tmp_path, 'cache-identity', 'auto')
    mod = f.modules['dk-workflows']
    home = f.base / 'codex'
    root = home / 'plugins/cache/factory/dk-workflows/1.0.0'
    shutil.copytree(f.base / 'installed/dk-workflows', root)
    del f.records[0]['installPath']
    f.records[0]['version'] = registered_version
    monkeypatch.setenv('CODEX_HOME', str(home))
    monkeypatch.setattr(mod.subprocess, 'run', f.subrun)
    identity = mod.installed(root, 'codex')
    assert identity['marketplace'] == 'factory'
    assert identity['version'] == registered_version
    assert identity['pinned'] is False


@pytest.mark.parametrize('source_type', ['local', 'directory', 'file'])
def test_codex_local_marketplace_does_not_auto_update_remote_plugin(tmp_path, source_type):
    f = Fixture(tmp_path, 'local-marketplace', 'auto')
    f.records[0]['source'] = {'source': 'git', 'url': 'https://example.com/plugin.git', 'ref': 'main'}
    f.records[0]['marketplaceSource'] = {'sourceType': source_type, 'source': str(f.base / 'catalog')}
    one = f.invoke()
    assert one['status'] == 'pinned'
    assert not f.invoke(phase='complete', token=one['token'])['updates']


@pytest.mark.parametrize('host', ['codex', 'claude'])
def test_changed_installation_scope_cancels_pending_update(tmp_path, host):
    f = Fixture(tmp_path, 'changed-scope', 'auto', host)
    one = f.invoke()
    f.records[0]['scope'] = 'project'
    f.write_claude()
    done = f.invoke(phase='complete', token=one['token'])
    assert done['updates'][0]['status'] == 'update_failed'
    assert 'identity changed' in done['updates'][0]['message']
    assert not [call for call in f.calls if call[1:3] in (['plugin', 'add'], ['plugin', 'update'])]


@pytest.mark.parametrize('nested,legacy_keys', [(False, False), (True, False), (False, True)])
def test_parallel_scoped_installations_are_both_updated(tmp_path, nested, legacy_keys):
    import subprocess

    first = Fixture(tmp_path, 'first-scope', 'auto', 'claude')
    second = Fixture(tmp_path, 'second-scope', 'auto', 'claude')
    second.env = first.env
    records = [first.records[0], second.records[0]]
    records[1]['scope'] = 'project'
    records[1]['projectPath'] = str(second.base)
    registry = first.base / 'claude/plugins/installed_plugins.json'

    def write_registry():
        registry.write_text(json.dumps({'plugins': {'dk-workflows@factory': records}}))

    original = first.subrun

    def scoped_run(argv, **kwargs):
        if argv[:3] == ['claude', 'plugin', 'update']:
            first.calls.append(argv)
            for record in records:
                if record['scope'] == argv[-1]:
                    record['version'] = '1.1.0'
            write_registry()
            return subprocess.CompletedProcess(argv, 0, '', '')
        return original(argv, **kwargs)

    write_registry()
    first.subrun = second.subrun = scoped_run
    one = first.invoke()
    two = second.invoke(**({'parent': one['token']} if nested else {}))
    if legacy_keys:
        state = first.state()
        for session in state['sessions'].values():
            session['pending'] = {'claude:dk-workflows': next(iter(session['pending'].values()))}
        (first.base / 'state/dk-code-factory/updates/state.json').write_text(json.dumps(state))
    assert second.invoke(phase='complete', token=two['token'])['status'] == 'deferred'
    done = first.invoke(phase='complete', token=one['token'])
    assert [update['status'] for update in done['updates']] == ['updated', 'updated']
    assert [record['version'] for record in records] == ['1.1.0', '1.1.0']
    assert {call[-1] for call in first.calls if call[:3] == ['claude', 'plugin', 'update']} == {'user', 'project'}


@pytest.mark.parametrize('scope', ['project', 'local'])
def test_claude_scoped_update_uses_registered_project_and_verifies_it(tmp_path, scope):
    f = Fixture(tmp_path, 'project-context', 'auto', 'claude')
    project = f.base / 'project'
    project.mkdir()
    f.records[0].update(scope=scope, projectPath=str(project))
    f.write_claude()
    original = f.subrun
    contexts = []

    def scoped_run(argv, **kwargs):
        if argv[0] == 'claude':
            contexts.append(kwargs.get('cwd'))
        return original(argv, **kwargs)

    f.subrun = scoped_run
    entry = f.invoke()
    done = f.invoke(phase='complete', token=entry['token'])
    assert done['updates'][0]['status'] == 'updated'
    assert contexts == [str(project), str(project)]


@pytest.mark.parametrize('project', [None, '', 'relative/project'])
def test_claude_project_scope_without_absolute_context_is_pinned(tmp_path, project):
    f = Fixture(tmp_path, 'missing-context', 'auto', 'claude')
    f.records[0].update(scope='project', projectPath=project)
    f.write_claude()
    entry = f.invoke()
    assert entry['status'] == 'pinned'
    assert not f.invoke(phase='complete', token=entry['token'])['updates']


def test_claude_verification_does_not_accept_another_project(tmp_path):
    f = Fixture(tmp_path, 'project-verification', 'auto', 'claude')
    project = f.base / 'project'
    project.mkdir()
    f.records[0].update(scope='project', projectPath=str(project))
    f.write_claude()
    entry = f.invoke()
    original = f.subrun

    def moved_record(argv, **kwargs):
        result = original(argv, **kwargs)
        if argv[:3] == ['claude', 'plugin', 'update']:
            f.records[0]['projectPath'] = str(f.base / 'different-project')
            f.write_claude()
        return result

    f.subrun = moved_record
    done = f.invoke(phase='complete', token=entry['token'])
    assert done['updates'][0]['status'] == 'update_failed'
    assert 'did not confirm' in done['updates'][0]['message']


@pytest.mark.parametrize('scope', ['user', 'project'])
def test_legacy_pending_context_is_safe(tmp_path, scope):
    f = Fixture(tmp_path, 'legacy-context', 'auto', 'claude')
    f.records[0].update(scope=scope, projectPath=str(f.base))
    f.write_claude()
    entry = f.invoke()
    state = f.state()
    for session in state['sessions'].values():
        for pending in session['pending'].values():
            pending['identity'].pop('project_path')
    (f.base / 'state/dk-code-factory/updates/state.json').write_text(json.dumps(state))
    done = f.invoke(phase='complete', token=entry['token'])
    assert done['updates'][0]['status'] == ('updated' if scope == 'user' else 'update_failed')
    if scope == 'project':
        assert not [call for call in f.calls if call[:3] == ['claude', 'plugin', 'update']]


def test_windows_lock_retries_contention_without_growing_lock_file(tmp_path, monkeypatch):
    import errno
    import sys
    from types import SimpleNamespace

    f = Fixture(tmp_path, 'windows-lock')
    mod = f.modules['dk-workflows']
    lock = f.base / '.lock'
    attempts = []

    def locking(fd, operation, size):
        attempts.append(operation)
        if operation == 1 and attempts.count(1) <= 12:
            raise OSError(errno.EACCES, 'Lock held by another workflow')

    monkeypatch.setattr(mod, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setitem(sys.modules, 'msvcrt', SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2, locking=locking))
    monkeypatch.setattr(mod.time, 'sleep', lambda delay: None)
    for _ in range(2):
        with mod.locked(lock):
            assert lock.read_bytes() == b'0'
    assert attempts.count(1) == 14
    assert attempts.count(2) == 2
