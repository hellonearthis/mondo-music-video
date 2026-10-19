#!/usr/bin/env python3
"""Run one read-only peer task using an existing CLI login."""
import argparse
import datetime
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid


def summarize(provider, raw):
    """Return (answer text, receipt lines, failed) from the CLI's JSON output."""
    try:
        if provider == 'claude':
            data = json.loads(raw)
            used = ', '.join(data.get('modelUsage', {})) or 'not reported'
            usage = data.get('usage', {})
            receipt = [f'Model used (reported by CLI): {used}',
                       f'Tokens: {usage.get("input_tokens")} in, {usage.get("output_tokens")} out '
                       f'(cache read {usage.get("cache_read_input_tokens")})',
                       f'Cost USD: {data.get("total_cost_usd")}']
            text = data.get('result') or ''
            failed = bool(data.get('is_error'))
            if failed:
                errors = '; '.join(str(e) for e in data.get('errors') or []) or 'no details'
                receipt.append(f'Failed ({data.get("subtype")}): {errors}')
                text = text or f'Helper failed: {errors}'
            return text, receipt, failed
        events = [json.loads(line) for line in raw.splitlines() if line.startswith('{')]
        text = '\n\n'.join(e['item']['text'] for e in events
                            if e.get('type') == 'item.completed'
                            and e['item'].get('type') == 'agent_message')
        usage = next((e['usage'] for e in reversed(events)
                      if e.get('type') == 'turn.completed'), {})
        return text, ['Model used: not reported by the Codex CLI (requested model only)',
                      f'Tokens: {usage.get("input_tokens")} in, {usage.get("output_tokens")} out '
                      f'(cached {usage.get("cached_input_tokens")})'], False
    except (ValueError, KeyError, TypeError, AttributeError):
        return raw, ['Model used: unknown; CLI output was not parseable JSON'], False


def acquire_lock(path):
    """Hold an OS lock for one helper run at a time; released if the process dies."""
    handle = open(path, 'a+')
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def kill_tree(proc):
    """Kill the helper and everything it started in its process group."""
    if os.name == 'nt':
        subprocess.run(['taskkill', '/T', '/F', '/PID', str(proc.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def interrupt(signum, frame):
    raise KeyboardInterrupt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('provider', choices=['claude', 'codex'])
    parser.add_argument('task')
    parser.add_argument('--model', help='Exact helper model for this run only; overrides --tier')
    parser.add_argument('--tier', choices=['low', 'medium'], default='low',
                        help='Helper tier (default: low). The model comes from '
                        'MMV_PEER_<PROVIDER>_MODEL_<TIER>, else the CLI\'s own default')
    parser.add_argument('--timeout', type=int, default=300, help='Seconds (default: 300)')
    parser.add_argument('--max-budget-usd', type=float, help='Claude spending cap for this run '
                        '(default: MMV_PEER_MAX_BUDGET_USD, else 0.50). Codex has no equivalent')
    parser.add_argument('--allow-default-model', action='store_true',
                        help='Run on the CLI\'s own default model when none is configured')
    parser.add_argument('--accept-api-billing', action='store_true',
                        help='Run even though an API key in the environment may bill per token')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    budget = args.max_budget_usd
    if budget is None:
        try:
            budget = float(os.environ.get('MMV_PEER_MAX_BUDGET_USD', '0.50'))
        except ValueError:
            parser.error('MMV_PEER_MAX_BUDGET_USD must be a number')
    if not math.isfinite(budget) or budget <= 0:
        parser.error('the budget must be a positive, finite number')
    if os.environ.get('MMV_PEER_ACTIVE') and not args.dry_run:
        parser.error('refusing to run: a peer helper must not launch another helper')
    root = Path(__file__).resolve().parents[1]
    tier_var = f'MMV_PEER_{args.provider.upper()}_MODEL_{args.tier.upper()}'
    model = args.model or os.environ.get(tier_var) or None
    if not model:
        message = (f'{tier_var} is not set, so the {args.provider} CLI default would be used; '
                   f'it may be a costly model, not a {args.tier}-tier one. Set {tier_var}, '
                   'pass --model, or pass --allow-default-model.')
        if not (args.allow_default_model or args.dry_run):
            parser.error(message)
        print('Note: ' + message, file=sys.stderr)
    # Credentials or providers that bill per token instead of a subscription login.
    key_vars = {'claude': ['ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_USE_BEDROCK',
                           'CLAUDE_CODE_USE_VERTEX'],
                'codex': ['OPENAI_API_KEY', 'CODEX_API_KEY']}
    keys = [name for name in key_vars[args.provider] if os.environ.get(name)]
    if keys:
        message = (f'{", ".join(keys)} is set, so this helper may be billed per token '
                   'instead of using a subscription. Pass --accept-api-billing to proceed.')
        if not (args.accept_api_billing or args.dry_run):
            parser.error(message)
        print('Note: ' + message, file=sys.stderr)
    model_args = ['--model', model] if model else []
    model_label = model or 'CLI default'
    prompt = (
        'You are a read-only peer helper for the Mondo Music Video project. Read AGENTS.md and the shared '
        'collaboration instructions. Do not edit files, run tests or mutating commands, delegate, '
        'or claim coordinator/writer ownership. Answer only the assigned task; '
        'cite relevant files and describe uncertainties. Begin your answer with one line '
        'stating which model you are (your own claim, unverified). Task: ' + args.task
    )
    empty_home = None
    if args.provider == 'claude':
        command = ['claude', '-p', *model_args, '--permission-mode', 'dontAsk',
                   '--tools', 'Read,Glob,Grep', '--strict-mcp-config',
                   '--no-session-persistence', '--setting-sources', '',
                   '--max-budget-usd', f'{budget:g}',
                   '--output-format', 'json', prompt]
    else:
        # Commands the Codex helper runs see an empty home (no CLI logins), no API
        # keys, and the nested-helper marker. Defense in depth, not a boundary.
        empty_home = tempfile.mkdtemp(prefix='peer-home-')
        home_value = json.dumps(empty_home)
        command = ['codex', 'exec', *model_args, '--sandbox', 'read-only',
                   '--ephemeral', '--ignore-user-config', '-c', 'model_reasoning_effort="low"',
                   '-c', 'features.multi_agent=false',
                   '-c', 'shell_environment_policy.exclude=["*API_KEY*", "*TOKEN*"]',
                   '-c', 'shell_environment_policy.set.MMV_PEER_ACTIVE="1"',
                   '-c', f'shell_environment_policy.set.HOME={home_value}',
                   '-c', f'shell_environment_policy.set.USERPROFILE={home_value}',
                   '-c', f'shell_environment_policy.set.CODEX_HOME={home_value}',
                   '--json', prompt]
    if args.dry_run:
        print(json.dumps({'cwd': str(root), 'argv': command}, indent=2))
        if empty_home:
            shutil.rmtree(empty_home, ignore_errors=True)
        return 0
    if not shutil.which(command[0]):
        if empty_home:
            shutil.rmtree(empty_home, ignore_errors=True)
        parser.error(f'{command[0]} is not on PATH')
    runs = root / '.collaboration' / 'runs'
    runs.mkdir(parents=True, exist_ok=True)
    lock = acquire_lock(root / '.collaboration' / 'peer.lock')
    if lock is None:
        if empty_home:
            shutil.rmtree(empty_home, ignore_errors=True)
        parser.error('another peer helper is already running; wait for it to finish')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    report = runs / f'{stamp}-{args.provider}-{uuid.uuid4().hex[:8]}.txt'
    limit = (f'Claude cap ${budget:g}' if args.provider == 'claude'
             else 'no dollar cap available for Codex')
    print(f'Running {args.provider} ({model_label}; {limit}; timeout {args.timeout}s); '
          f'report: {report}', flush=True)
    if os.name != 'nt':
        signal.signal(signal.SIGTERM, interrupt)
        signal.signal(signal.SIGHUP, interrupt)
    group = ({'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt'
             else {'start_new_session': True})
    proc = subprocess.Popen(command, cwd=root, text=True, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env={**os.environ, 'MMV_PEER_ACTIVE': '1'}, **group)
    try:
        output, diagnostics = proc.communicate(timeout=args.timeout)
        code = proc.returncode
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as stop:
        kill_tree(proc)
        try:
            proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        timed_out = isinstance(stop, subprocess.TimeoutExpired)
        output = ''
        diagnostics = ('Helper timed out' if timed_out else 'Helper interrupted') + \
            '; process tree killed; no automatic retry.'
        code = 124 if timed_out else 130
    finally:
        kill_tree(proc)  # also removes anything the helper left running
        lock.close()
        if empty_home:
            shutil.rmtree(empty_home, ignore_errors=True)
    if output:
        output, receipt, failed = summarize(args.provider, output)
        if failed and code == 0:
            code = 1
    else:
        receipt = ['Model used: none (no output)']
    receipt = '\n'.join(receipt)
    report.write_text(f'Provider: {args.provider}\nModel requested: {model_label}\n'
                      f'{receipt}\n'
                      f'Exit: {code}\nTask: {args.task}\n\n{output}\n\n'
                      f'Diagnostics:\n{diagnostics}', encoding='utf-8')
    print(output)
    if diagnostics:
        print(diagnostics, file=sys.stderr)
    return code


if __name__ == '__main__':
    sys.exit(main())
