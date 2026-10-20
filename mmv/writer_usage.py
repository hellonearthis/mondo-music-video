"""Read-only token telemetry for writer calls (adapted from hellonearthis' 1.8.11 contribution).

The pinned `engine/writer.py` discards the completion's `usage`/`timings`, so this observes the HTTP response while the call runs.
It never changes a request or a response."""
import json, threading, urllib.request

_LOCK = threading.Lock()


def launch_context(settings):
    """Context size from the configured llama-server launch arguments, or None when unknown (API writers)."""
    try:
        args = json.loads(settings.get('writer_launch') or '[]')
        size = next((int(b) for a, b in zip(args, args[1:]) if a in ('-c', '--ctx-size')), 0)
    except (TypeError, ValueError):
        return None
    return size if size >= 512 else None


def usage_line(captured, ctx_size, label=None):
    """The `[tokens]` log line for one completion, or '' when the server reported no usage."""
    usage = captured.get('usage')
    if not isinstance(usage, dict):
        return ''
    prompt, done = usage.get('prompt_tokens', 0), usage.get('completion_tokens', 0)
    total = usage.get('total_tokens', prompt + done)
    speed = (captured.get('timings') or {}).get('predicted_per_second')
    return (f"   [tokens]{f' {label}' if label else ''}: {prompt:,} prompt + {done:,} generated = {total:,} total"
            + (f" — {round(total / ctx_size * 100)}% context used" if ctx_size else '')
            + (f", {speed:.0f} t/s" if speed else ''))


class _Tap:
    """Pass-through response wrapper that records the JSON usage fields it reads."""
    def __init__(self, response, captured):
        self._response, self._captured = response, captured

    def read(self, *args, **kwargs):
        data = self._response.read(*args, **kwargs)
        try:
            body = json.loads(data.decode('utf-8'))
            if isinstance(body, dict):
                self._captured.update(usage=body.get('usage'), timings=body.get('timings'))
        except ValueError:
            pass
        return data

    def __getattr__(self, name):
        return getattr(self._response, name)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return self._response.__exit__(*exc)


def observe(call, captured):
    """Run `call()` with urlopen tapped into `captured`; the original urlopen is always restored."""
    with _LOCK:
        original = urllib.request.urlopen
        urllib.request.urlopen = lambda *a, **k: _Tap(original(*a, **k), captured)
        try:
            return call()
        finally:
            urllib.request.urlopen = original
