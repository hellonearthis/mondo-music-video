"""
🪿 MAXIMUM GOOSE LABORATORY 🪿
atomic_io — write a file so it is never seen half-written.

A file written in place and interrupted (Ctrl-C, a crash, a power blip)
can be left truncated: a renders.json that no longer parses refuses the
next step, and a receipt is lost. write_text_atomic writes the new text to
a temporary file beside the target, flushes it to the disk, keeps the old
file's permission bits, and swaps it in with one os.replace — a reader sees
the old file or the new one, never a piece of either. If anything fails,
the original is untouched and the temporary file is removed.

The text written is exactly the text given: switching a write_text call to
this changes no byte of the result.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path

NEW_FILE_MODE = 0o644


def write_text_atomic(path, text: str, encoding: str = "utf-8") -> Path:
    """Write `text` to `path` atomically. Returns the path."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp",
                               dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        try:
            mode = stat.S_IMODE(os.stat(path).st_mode)
        except FileNotFoundError:
            mode = NEW_FILE_MODE
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    return path


def write_json_atomic(path, obj, *, indent: int | None = 2,
                      trailing_newline: bool = False, **dumps_kwargs) -> Path:
    """json.dumps(obj, indent=...) written atomically (optionally + "\\n")."""
    text = json.dumps(obj, indent=indent, **dumps_kwargs)
    return write_text_atomic(path, text + ("\n" if trailing_newline else ""))
