"""Startup updates for the installation's own tracked Git branch.

No production, model downloads, remote submissions, stashing or hard resets.
"""
from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

from .storage import read_json, write_json

STATUS_FILE = 'update-status.json'


class UpdateError(ValueError):
    pass


def _git(root, *args, timeout=20, check=True):
    result = subprocess.run(['git', '-c', 'core.hooksPath=' + os.devnull, '-C', str(root), *args],
                            capture_output=True, text=True, timeout=timeout,
                            env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
    if check and result.returncode:
        raise UpdateError('Git command could not complete')
    return result


def _is_source(path):
    path = Path(path)
    if not (path / '.git').exists() or not (path / 'pyproject.toml').is_file():
        return False
    try:
        return tomllib.loads((path / 'pyproject.toml').read_text())['project']['name'] == 'mondo-music-video'
    except (OSError, ValueError, KeyError):
        return False


def source_root(store):
    # An installed wheel's own parent need not be the checkout used by install.sh.
    candidate = Path(__file__).resolve().parent.parent
    if _is_source(candidate):
        return candidate
    try:
        direct = json.loads(importlib.metadata.distribution('mondo-music-video').read_text('direct_url.json') or '{}')
        url = urlsplit(direct.get('url', ''))
        if url.scheme == 'file' and not url.netloc and 'archive_info' not in direct:
            path = unquote(url.path)
            if os.name == 'nt' and re.match(r'^/[A-Za-z]:', path):
                path = path[1:]
            if _is_source(path):
                return Path(path).resolve()
    except (importlib.metadata.PackageNotFoundError, OSError, ValueError, TypeError):
        pass
    # Installing our staged wheel replaces direct_url.json. Retain the already
    # identified checkout in private application state for subsequent launches.
    try:
        record = read_json(store.home / STATUS_FILE, {})
    except (OSError, ValueError):
        record = {}
    candidate = record.get('source_root')
    if candidate and _is_source(candidate):
        return Path(candidate).resolve()
    return None


def repository_link(remote):
    if remote.startswith('git@github.com:'):
        remote = 'https://github.com/' + remote.split(':', 1)[1]
    url = urlsplit(remote)
    if url.scheme not in ('https', 'http') or not url.hostname:
        return None
    path = url.path.removesuffix('.git').rstrip('/')
    return urlunsplit((url.scheme, url.netloc.rsplit('@', 1)[-1], path, '', ''))


def _version(root, commit):
    try:
        data = _git(root, 'show', commit + ':pyproject.toml').stdout
        return str(tomllib.loads(data)['project']['version'])
    except (UpdateError, ValueError, KeyError):
        return 'unknown'


def _clean(root):
    return not _git(root, 'status', '--porcelain', '--untracked-files=normal').stdout.strip()


@contextmanager
def _update_lock(root, name="mmv-update.lock"):
    directory = Path(_git(root, 'rev-parse', '--absolute-git-dir').stdout.strip())
    stream = (directory / name).open('a+b')
    try:
        try:
            if os.name == 'nt':
                import msvcrt
                stream.seek(0)
                if not stream.read(1):
                    stream.write(b'0'); stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise UpdateError('Another application/updater is already using this checkout') from None
        yield
    finally:
        stream.close()


@contextmanager
def repository_session(store):
    """Hold a checkout-wide lease so updates cannot modify another live app."""
    root = source_root(store)
    if root is None:
        yield
    else:
        with _update_lock(root, 'mmv-runtime.lock'):
            yield


def _archive(root, commit, destination):
    destination.mkdir()
    archive = destination.parent / (destination.name + '.tar')
    with archive.open('wb') as stream:
        result = subprocess.run(['git', '-C', str(root), 'archive', '--format=tar', commit],
                                stdout=stream, stderr=subprocess.PIPE, timeout=30)
    if result.returncode:
        raise UpdateError('Could not stage the update source')
    with tarfile.open(archive) as bundle:
        for member in bundle:
            path = Path(member.name)
            if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
                raise UpdateError('Update contains unsupported archive paths or links')
            target = destination / path
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.extractfile(member) as source, target.open('wb') as output:
                    import shutil
                    shutil.copyfileobj(source, output)


def _pip(store, args, timeout=600):
    log_path = store.home / 'update-install.log'
    with log_path.open('ab') as log:
        os.chmod(log_path, 0o600)
        result = subprocess.run([sys.executable, '-m', 'pip', '--disable-pip-version-check',
                                 '--no-input', *args], stdout=log, stderr=log, timeout=timeout,
                                env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    if result.returncode:
        raise UpdateError('Package installation failed; inspect the private update-install.log')


def _build_wheel(store, source, destination):
    destination.mkdir()
    _pip(store, ['wheel', '--no-deps', '--wheel-dir', str(destination), str(source)])
    wheels = list(destination.glob('mondo_music_video-*.whl'))
    if len(wheels) != 1:
        raise UpdateError('Update did not produce one application wheel')
    return wheels[0]


def _installed_extras():
    return [name for name, module in [('comfy', 'comfy_sdk'), ('mcp', 'mcp')]
            if importlib.util.find_spec(module) is not None]


def _install_wheel(store, wheel, *, rollback=False):
    if rollback:
        _pip(store, ['install', '--force-reinstall', '--no-deps', str(wheel)])
    else:
        extras = _installed_extras()
        spec = str(wheel) + ('[' + ','.join(extras) + ']' if extras else '')
        _pip(store, ['install', '--upgrade', spec])


def _virtualenv():
    return sys.prefix != sys.base_prefix


def startup_update(store, *, root=None, automatic=None):
    """Check once at launch; return status, plus restart/fatal when applicable.

    Caller holds the application data SessionLock and has not started its server.
    """
    result = {'state': 'checking', 'available': False, 'checked_at': time.time(),
              'automatic': bool(store.settings().get('auto_updates', False)) if automatic is None else bool(automatic)}
    root = Path(root).resolve() if root else source_root(store)
    def finish(state, message, **fields):
        result.update(state=state, message=message, **fields)
        write_json(store.home / STATUS_FILE, result, private=True)
        return result
    if root is None:
        return finish('unsupported', 'Automatic updates require a Git checkout. Use the repository installation instructions.',
                      repository_url='https://github.com/hodgemann/mondo-music-video')
    result['source_root'] = str(root)
    try:
        with _update_lock(root):
            head = _git(root, 'rev-parse', 'HEAD').stdout.strip()
            skip = os.environ.pop('MMV_UPDATE_RESTART_COMMIT', None)
            if skip == head:
                previous = read_json(store.home / STATUS_FILE, {})
                if previous.get('installed_commit') == head:
                    return finish('updated', 'Update installed successfully.', installed_commit=head,
                                  installed_version=_version(root, head), repository_url=previous.get('repository_url'))
            branch = _git(root, 'symbolic-ref', '--quiet', '--short', 'HEAD', check=False)
            if branch.returncode:
                return finish('blocked', 'Detached checkout: automatic updates are paused.')
            branch = branch.stdout.strip()
            remote = _git(root, 'config', '--get', 'branch.' + branch + '.remote', check=False).stdout.strip()
            merge = _git(root, 'config', '--get', 'branch.' + branch + '.merge', check=False).stdout.strip()
            if not remote or remote == '.' or remote.startswith('-') or not merge.startswith('refs/heads/'):
                return finish('blocked', 'Set a tracked remote branch to enable update checks.')
            url = _git(root, 'remote', 'get-url', remote).stdout.strip()
            result.update(repository_url=repository_link(url), branch=branch, installed_commit=head,
                          installed_version=_version(root, head))
            _git(root, 'fetch', '--no-tags', '--no-recurse-submodules', remote, merge, timeout=15)
            target = _git(root, 'rev-parse', 'FETCH_HEAD').stdout.strip()
            if head == target:
                return finish('current', 'Mondo Music Video is up to date.')
            behind = _git(root, 'merge-base', '--is-ancestor', target, head, check=False)
            if behind.returncode == 0:
                return finish('current', 'This checkout already includes the remote updates.')
            result.update(available=True, available_commit=target, available_version=_version(root, target))
            if not result['automatic']:
                return finish('available', 'An update is available. Automatic installation is turned off.')
            if read_json(store.home / 'operation.json', {}).get('state') in ('running', 'cancelling', 'interrupted'):
                return finish('blocked', 'An update is available; reconcile the interrupted production before updating.')
            if not _clean(root):
                return finish('blocked', 'An update is available; local code changes prevent automatic installation.')
            if _git(root, 'merge-base', '--is-ancestor', head, target, check=False).returncode:
                return finish('blocked', 'An update is available; this branch has diverged. Review and merge it manually.')
            if not _virtualenv():
                return finish('blocked', 'Automatic installation requires a virtual environment. Update manually or use the repository installer.')
            finish('installing', 'Preparing and installing the update before startup.')
            with tempfile.TemporaryDirectory(prefix='mmv-update-') as temp:
                stage = Path(temp)
                _archive(root, head, stage / 'previous')
                _archive(root, target, stage / 'candidate')
                previous_wheel = _build_wheel(store, stage / 'previous', stage / 'old-wheel')
                candidate_wheel = _build_wheel(store, stage / 'candidate', stage / 'new-wheel')
                # Recheck after builds; no local work is stashed or discarded.
                if not _clean(root) or _git(root, 'rev-parse', 'HEAD').stdout.strip() != head:
                    return finish('blocked', 'Checkout changed while preparing the update; no update was applied.')
                installation_started = False
                try:
                    installation_started = True
                    _install_wheel(store, candidate_wheel)
                    if not _clean(root) or _git(root, 'rev-parse', 'HEAD').stdout.strip() != head:
                        raise UpdateError('Checkout changed during installation')
                    # Git must refuse collisions even with ignored local assets.
                    _git(root, 'merge', '--ff-only', '--no-overwrite-ignore', target, timeout=30)
                except (UpdateError, OSError, subprocess.TimeoutExpired):
                    if installation_started:
                        try:
                            _install_wheel(store, previous_wheel, rollback=True)
                        except (UpdateError, OSError, subprocess.TimeoutExpired):
                            return finish('failed', 'Update failed and application-package recovery failed. Repair the environment before starting.', fatal=True)
                    # Dependencies may have changed during a failed pip transaction.
                    return finish('failed', 'Update failed. Previous application package restored; repair dependencies before starting. See update-install.log.', fatal=True)
            return finish('updated', 'Update installed; restarting into the new version.', restart=True,
                          installed_commit=target, installed_version=_version(root, target), available=False)
    except subprocess.TimeoutExpired:
        return finish('unavailable', 'Update check/preparation timed out. Continuing with the installed version.')
    except (OSError, UpdateError, ValueError):
        return finish('unavailable', 'Update check/preparation could not complete. Continuing with the installed version.')


def public_status(store):
    try:
        record = read_json(store.home / STATUS_FILE, {})
    except (OSError, ValueError):
        record = {}
    allowed = ('state', 'available', 'automatic', 'message', 'checked_at', 'repository_url',
               'branch', 'installed_version', 'available_version')
    return {key: record[key] for key in allowed if key in record} or {
        'state': 'not_checked', 'available': False,
        'message': 'Update checks run when the application is launched.'}
