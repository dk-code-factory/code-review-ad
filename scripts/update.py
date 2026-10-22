#!/usr/bin/env python3
"""Self-contained plugin lifecycle and release policy (Python standard library)."""
import argparse
from contextlib import contextmanager
import errno
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

DAY = 86400
MODES = ('notify', 'auto', 'off')


def read(path, default=None):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {} if default is None else default


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False, encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        temporary = stream.name
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


@contextmanager
def locked(path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('a+b') as stream:
        if os.name == 'nt':
            import msvcrt
            stream.seek(0, 2)
            if stream.tell() == 0:
                stream.write(b'0'); stream.flush()
            stream.seek(0)
            while True:
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    time.sleep(0.05)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def version(value):
    match = re.fullmatch(r'v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value or '')
    return tuple(map(int, match.groups())) if match else None


def run(argv, *, cwd=None):
    proc = subprocess.run(argv, text=True, capture_output=True, timeout=90, cwd=cwd)
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or 'Host command failed')
    return proc.stdout


def project_path(record):
    if record.get('scope') not in ('project', 'local'):
        return None
    value = record.get('projectPath')
    if isinstance(value, str) and Path(value).is_absolute():
        return str(Path(value).resolve())
    return None


def installed(root, host):
    root = root.resolve()
    manifest = read(root / f'.{host}-plugin/plugin.json')
    name = manifest['name']
    marketplace = None
    pinned = False
    scope = 'user'
    project = None
    records = []
    if host == 'claude':
        home = Path(os.environ.get('CLAUDE_CONFIG_DIR', Path.home() / '.claude'))
        plugins = read(home / 'plugins/installed_plugins.json').get('plugins', {})
        for key, values in plugins.items():
            if key.split('@', 1)[0] == name:
                records += [(key, r) for r in values if Path(r.get('installPath', '')).resolve() == root]
        known = read(home / 'plugins/known_marketplaces.json')
    else:
        data = json.loads(run(['codex', 'plugin', 'list', '--json']))
        home = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))
        for record in data.get('installed', []):
            if record.get('name') != name or record.get('installed') is False:
                continue
            identity = record.get('pluginId', '')
            plugin_name, separator, catalog_name = identity.partition('@')
            if not separator or plugin_name != name or not catalog_name:
                continue
            # Listing a plugin with the same name does not register this script's
            # checkout. Current Codex lists omit installPath, so also recognize
            # the host's versioned cache directory (including an older loaded
            # version after the registry has advanced).
            install_path = record.get('installPath')
            registered_root = (Path(install_path) if install_path else
                               home / 'plugins/cache' / catalog_name / name / manifest['version'])
            if registered_root.resolve() == root:
                records.append((identity, record))
        known = {}
    if len(records) > 1:
        raise ValueError('Ambiguous installed plugin registry identity; no automatic update')
    if records:
        identity, record = records[0]
        manifest['version'] = record.get('version', manifest['version'])
        marketplace = identity.split('@', 1)[1]
        scope = record.get('scope', 'user')
        if host == 'claude':
            project = project_path(record)
            pinned |= scope in ('project', 'local') and project is None
        source = record.get('source') or known.get(marketplace, {}).get('source', {})
        if isinstance(source, str):
            source = {'source': source}
        marketplace_source = record.get('marketplaceSource') or {}
        remote_marketplace = marketplace_source.get('sourceType') == 'git'
        pinned |= bool(record.get('pinned') or source.get('sha') or source.get('ref') not in (None, 'main')
                      or marketplace_source.get('sha') or marketplace_source.get('ref') not in (None, 'main')
                      or marketplace_source.get('sourceType') in ('local', 'directory', 'file')
                      or (source.get('source') == 'local' and not remote_marketplace)
                      or source.get('sourceType') in ('local', 'directory')
                      or source.get('source') in ('directory', 'file'))
        # Inspect the registered catalog entry as well as the marketplace source.
        catalog = known.get(marketplace, {}).get('installLocation')
        if catalog:
            entries = read(Path(catalog) / '.claude-plugin/marketplace.json').get('plugins', [])
            for entry in entries:
                if entry.get('name') == name:
                    source = entry.get('source', {})
                    if isinstance(source, dict):
                        pinned |= bool(source.get('sha') or source.get('ref') not in (None, 'main'))
    else:
        pinned = True  # Direct checkout, plugin-dir, or unregistered installation.
    return {'name': name, 'host': host, 'marketplace': marketplace, 'version': manifest['version'],
            'repository': 'dk-code-factory/' + name, 'pinned': pinned, 'scope': scope,
            'root': str(root), 'project_path': project}


def latest(repository):
    request = urllib.request.Request('https://api.github.com/repos/' + repository + '/releases/latest',
                                     headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'dk-code-factory-updater/1'})
    with urllib.request.urlopen(request, timeout=4) as response:
        release = json.load(response)
    tag = release.get('tag_name')
    if release.get('draft') or release.get('prerelease') or not version(tag):
        raise ValueError('Latest release is not stable semantic versioning')
    return tag.removeprefix('v')


def paths(root, cwd):
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'dk-code-factory/updates.json'
    state = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'dk-code-factory/updates'
    # A configured XDG location must not write into a plugin or reviewed repository.
    repo = subprocess.run(['git', '-C', str(cwd), 'rev-parse', '--show-toplevel'],
                          text=True, capture_output=True)
    protected = [root.resolve()]
    if repo.returncode == 0:
        protected.append(Path(repo.stdout.strip()).resolve())
    if any(path.resolve().is_relative_to(parent) for path in (config, state) for parent in protected):
        raise ValueError('Update settings and state must be outside plugin and reviewed repository')
    return config, state


def mode(settings, name):
    value = settings.get('plugins', {}).get(name, settings.get('mode', 'notify'))
    if isinstance(value, dict):
        value = value.get('mode', settings.get('mode', 'notify'))
    if value not in MODES:
        raise ValueError('Update mode must be notify, auto or off')
    return value


def installation_key(identity):
    return json.dumps([identity[key] for key in ('host', 'name', 'marketplace', 'scope', 'root')]
                      + [identity.get('project_path')])


def update(identity, target):
    name, marketplace, host = (identity[k] for k in ('name', 'marketplace', 'host'))
    if (identity['pinned'] or not marketplace
            or host == 'claude' and identity['scope'] in ('project', 'local')
            and not identity.get('project_path')):
        return {'status': 'pinned', 'message': 'Pinned or unregistered installation; update manually.'}
    if version(identity['version']) and version(identity['version']) >= version(target):
        return {'status': 'current', 'version': identity['version'], 'reload_required': True,
                'message': 'The host already has this release or a newer version. Reload plugins or start a new session.'}
    if host == 'claude':
        commands = [['claude', 'plugin', 'marketplace', 'update', marketplace],
                    ['claude', 'plugin', 'update', name + '@' + marketplace, '--scope', identity['scope']]]
    else:
        commands = [['codex', 'plugin', 'marketplace', 'upgrade', marketplace],
                    ['codex', 'plugin', 'add', name + '@' + marketplace, '--json']]
    try:
        for command in commands:
            run(command, cwd=identity.get('project_path') if host == 'claude' else None)
        if host == 'codex':
            rows = json.loads(run(['codex', 'plugin', 'list', '--json'])).get('installed', [])
            versions = [r['version'] for r in rows if r['pluginId'] == name + '@' + marketplace
                        and r.get('installed') is not False
                        and r.get('scope', 'user') == identity['scope']]
        else:
            home = Path(os.environ.get('CLAUDE_CONFIG_DIR', Path.home() / '.claude'))
            rows = read(home / 'plugins/installed_plugins.json').get('plugins', {}).get(name + '@' + marketplace, [])
            versions = [r['version'] for r in rows if r.get('scope') == identity['scope']
                        and project_path(r) == identity.get('project_path')]
        if len(versions) != 1 or not version(versions[0]) or version(versions[0]) < version(target):
            raise RuntimeError('Host did not confirm installation of the released version')
        return {'status': 'updated', 'version': versions[0], 'reload_required': True,
                'message': 'Update installed. ' + ('Run /reload-plugins or start a new session.' if host == 'claude' else 'Start a new Codex session.')}
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        return {'status': 'update_failed', 'message': str(exc), 'reload_required': False}


def lifecycle(root, host, phase, *, token=None, parent=None, now=None):
    now = time.time() if now is None else now
    config_path, state = paths(root, Path.cwd())
    with locked(state / '.lock'):
        data = read(state / 'state.json', {'checks': {}, 'notices': [], 'invocations': {}, 'sessions': {}})
        if phase == 'entry':
            token = uuid.uuid4().hex
            if parent:
                if parent not in data['invocations'] or data['invocations'][parent]['complete']:
                    raise ValueError('Unknown or completed parent workflow token')
                session_id = data['invocations'][parent]['session']
            else:
                session_id = uuid.uuid4().hex
                data['sessions'][session_id] = {'active': [], 'pending': {}}
            session = data['sessions'][session_id]
            session['active'].append(token)
            data['invocations'][token] = {'session': session_id, 'complete': False}
            # Host/configuration failures must not hide a live workflow from
            # other invocations that are waiting to install an update.
            try:
                identity = installed(root, host)
                if not version(identity['version']):
                    raise ValueError('Installed plugin version is not stable semantic versioning')
                policy = mode(read(config_path), identity['name'])
            except Exception as exc:
                write(state / 'state.json', data)
                return {'status': 'unavailable', 'action': 'continue', 'message': str(exc),
                        'non_blocking': True, 'token': token}
            result = {'status': 'current', 'action': 'continue', 'message': '', 'token': token,
                      'identity': identity, 'mode': policy}
            if policy != 'off':
                cache = data['checks'].get(identity['repository'], {})
                checked = cache.get('checked') if isinstance(cache, dict) else None
                valid_cache = (isinstance(checked, (int, float)) and not isinstance(checked, bool)
                               and 0 <= now - checked < DAY
                               and ('error' in cache or isinstance(cache.get('version'), str)
                                    and version(cache['version'])))
                if not valid_cache:
                    try:
                        cache = {'checked': now, 'version': latest(identity['repository'])}
                    except Exception as exc:
                        cache = {'checked': now, 'error': str(exc)}
                    data['checks'][identity['repository']] = cache
                if 'error' in cache:
                    result.update(status='offline', message='Update check unavailable; workflow may continue.')
                elif version(cache['version']) > version(identity['version']):
                    target = cache['version']
                    notice = ':'.join((host, identity['name'], identity['version'], target, policy))
                    if identity['pinned']:
                        status, message = 'pinned', f'{identity["name"]} {target} is available; this installation is pinned or unregistered.'
                    elif policy == 'auto':
                        status, message = 'deferred', f'{identity["name"]} {target} will update after the outer workflow completes.'
                        session['pending'][installation_key(identity)] = {'identity': identity, 'target': target}
                    else:
                        status, message = 'available', f'{identity["name"]} {target} is available (installed {identity["version"]}).'
                    result['status'] = status
                    if notice not in data['notices']:
                        data['notices'].append(notice)
                        result.update(action='notify', message=message)
        else:
            invocation = data['invocations'].get(token)
            if not invocation:
                raise ValueError('Unknown completion token')
            session = data['sessions'][invocation['session']]
            result = {'status': 'completed', 'action': 'continue', 'message': '', 'token': token, 'updates': []}
            if not invocation['complete']:
                invocation['complete'] = True
                session['active'].remove(token)
            if any(row['active'] for row in data['sessions'].values()):
                result['status'] = 'deferred'
            else:
                # Concurrent outer workflows can share an installation too. Drain
                # pending work only when all recorded invocations have finished.
                pending_updates = {}
                for row in data['sessions'].values():
                    # Derive keys from saved identities so older host:name keys
                    # remain readable without merging distinct installations.
                    for pending in row['pending'].values():
                        pending_updates[installation_key(pending['identity'])] = pending
                for pending in pending_updates.values():
                    identity = pending['identity']
                    # Recheck policy and pins at completion; changing settings must cancel a pending auto-update.
                    try:
                        if mode(read(config_path), identity['name']) != 'auto':
                            continue
                        current = installed(Path(identity['root']), identity['host'])
                        if installation_key(current) != installation_key(identity):
                            raise ValueError('Installation identity changed during workflow')
                        outcome = update(current, pending['target'])
                    except Exception as exc:
                        outcome = {'status': 'update_failed', 'message': str(exc), 'reload_required': False}
                    result['updates'].append({'plugin': identity['name'], **outcome})
                for row in data['sessions'].values():
                    row['pending'] = {}
                if result['updates']:
                    result.update(action='notify', message='; '.join(u['message'] for u in result['updates']))
        write(state / 'state.json', data)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['entry', 'complete', 'policy'])
    parser.add_argument('--host', choices=['claude', 'codex'], required=True)
    parser.add_argument('--token')
    parser.add_argument('--parent', default=os.environ.get('DK_UPDATE_PARENT'))
    parser.add_argument('--mode', choices=MODES)
    parser.add_argument('--plugin', help='Per-plugin policy override; omit for the global default')
    args = parser.parse_args()
    root = next(p for p in Path(__file__).resolve().parents if (p / '.codex-plugin/plugin.json').is_file())
    try:
        if args.phase == 'policy':
            config, _ = paths(root, Path.cwd())
            with locked(config.with_suffix('.lock')):
                settings = read(config)
                if args.mode:
                    if args.plugin:
                        settings.setdefault('plugins', {})[args.plugin] = args.mode
                    else:
                        settings['mode'] = args.mode
                    write(config, settings)
            result = {'status': 'policy', 'settings': settings, 'path': str(config)}
        else:
            result = lifecycle(root, args.host, args.phase, token=args.token, parent=args.parent)
    except Exception as exc:
        result = {'status': 'unavailable', 'action': 'continue', 'message': str(exc), 'non_blocking': True}
    print(json.dumps(result))


if __name__ == '__main__':
    main()
