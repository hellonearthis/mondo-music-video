"""Media metadata helper. Production assembly lives in the original engine."""
import subprocess
import shutil
import json
import math

def duration(path):
    if not shutil.which("ffprobe"):
        raise ValueError("FFprobe is missing. Install FFmpeg and add it to PATH")
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "json", str(path)], check=True, capture_output=True, timeout=20)
        seconds = float(json.loads(result.stdout)["format"]["duration"])
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("Invalid duration")
        return seconds
    except (subprocess.SubprocessError, KeyError, ValueError) as exc:
        raise ValueError("Cannot read media duration") from exc
