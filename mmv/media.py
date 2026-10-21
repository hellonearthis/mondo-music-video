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


def video_info(path):
    """Container facts the Topaz cloud API needs for a request: size, duration, frames, rate, dimensions, audio."""
    if not shutil.which("ffprobe"):
        raise ValueError("FFprobe is missing. Install FFmpeg and add it to PATH")
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                 "format=duration,size:stream=codec_type,width,height,avg_frame_rate,nb_frames",
                                 "-of", "json", str(path)], check=True, capture_output=True, timeout=20)
        probe = json.loads(result.stdout)
        streams = probe["streams"]
        video = next(s for s in streams if s["codec_type"] == "video")
        numerator, denominator = (int(x) for x in video["avg_frame_rate"].split("/"))
        rate = numerator / denominator
        seconds = float(probe["format"]["duration"])
        frames = int(video["nb_frames"]) if str(video.get("nb_frames", "")).isdigit() else round(seconds * rate)
        info = {"width": int(video["width"]), "height": int(video["height"]), "frame_rate": rate,
                "frame_count": frames, "duration": seconds, "size": int(probe["format"]["size"]),
                "has_audio": any(s["codec_type"] == "audio" for s in streams)}
        if not all(math.isfinite(info[k]) and info[k] > 0 for k in ("frame_rate", "duration", "size", "width", "height")):
            raise ValueError("Invalid video facts")
        return info
    except (subprocess.SubprocessError, KeyError, StopIteration, ValueError, ZeroDivisionError) as exc:
        raise ValueError("Cannot read video details") from exc
