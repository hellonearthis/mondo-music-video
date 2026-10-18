"""Video encoding formats, hardware encoders, and FFmpeg capability probing."""
from __future__ import annotations
import shutil
import subprocess

VIDEO_ENCODERS = {
    "libx264": {
        "id": "libx264",
        "name": "AVC / H.264 (libx264 - Default, Universal)",
        "codec": "h264",
        "description": "Standard software AVC encoder with universal device and browser compatibility.",
        "hardware": False,
        "high": ["-c:v", "libx264", "-crf", "6", "-preset", "slow", "-pix_fmt", "yuv420p"],
        "low": ["-c:v", "libx264", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p"],
    },
    "libx265": {
        "id": "libx265",
        "name": "HEVC / H.265 (libx265 - Software, High compression)",
        "codec": "hevc",
        "description": "High-efficiency software HEVC encoder for smaller file sizes at identical visual quality.",
        "hardware": False,
        "high": ["-c:v", "libx265", "-crf", "18", "-preset", "medium", "-tag:v", "hvc1", "-pix_fmt", "yuv420p"],
        "low": ["-c:v", "libx265", "-crf", "24", "-preset", "medium", "-tag:v", "hvc1", "-pix_fmt", "yuv420p"],
    },
    "hevc_nvenc": {
        "id": "hevc_nvenc",
        "name": "HEVC / H.265 (NVIDIA NVENC Hardware acceleration)",
        "codec": "hevc",
        "description": "Ultra-fast hardware-accelerated HEVC encoding via NVIDIA GeForce / RTX GPU.",
        "hardware": True,
        "high": ["-c:v", "hevc_nvenc", "-preset", "p5", "-cq", "20", "-tag:v", "hvc1", "-pix_fmt", "yuv420p"],
        "low": ["-c:v", "hevc_nvenc", "-preset", "p5", "-cq", "24", "-tag:v", "hvc1", "-pix_fmt", "yuv420p"],
    },
    "hevc_qsv": {
        "id": "hevc_qsv",
        "name": "HEVC / H.265 (Intel QuickSync Hardware acceleration)",
        "codec": "hevc",
        "description": "Hardware-accelerated HEVC encoding using Intel QuickSync Video.",
        "hardware": True,
        "high": ["-c:v", "hevc_qsv", "-global_quality", "20", "-preset", "medium", "-tag:v", "hvc1", "-pix_fmt", "yuv420p"],
        "low": ["-c:v", "hevc_qsv", "-global_quality", "24", "-preset", "medium", "-tag:v", "hvc1", "-pix_fmt", "yuv420p"],
    },
    "hevc_amf": {
        "id": "hevc_amf",
        "name": "HEVC / H.265 (AMD AMF Hardware acceleration)",
        "codec": "hevc",
        "description": "Hardware-accelerated HEVC encoding using AMD Radeon graphics.",
        "hardware": True,
        "high": ["-c:v", "hevc_amf", "-quality", "quality", "-rc", "cqp", "-qp_p", "20", "-qp_i", "20", "-tag:v", "hvc1", "-pix_fmt", "yuv420p"],
        "low": ["-c:v", "hevc_amf", "-quality", "quality", "-rc", "cqp", "-qp_p", "24", "-qp_i", "24", "-tag:v", "hvc1", "-pix_fmt", "yuv420p"],
    },
    "hevc_videotoolbox": {
        "id": "hevc_videotoolbox",
        "name": "HEVC / H.265 (Apple VideoToolbox Hardware acceleration)",
        "codec": "hevc",
        "description": "Hardware-accelerated HEVC encoding for macOS and Apple Silicon.",
        "hardware": True,
        "high": ["-c:v", "hevc_videotoolbox", "-q:v", "75", "-tag:v", "hvc1", "-pix_fmt", "yuv420p"],
        "low": ["-c:v", "hevc_videotoolbox", "-q:v", "65", "-tag:v", "hvc1", "-pix_fmt", "yuv420p"],
    },
}

DEFAULT_ENCODER = "libx264"


def get_encoder_args(encoder: str | None = None, quality: str = "high") -> list[str]:
    """Return the FFmpeg video encoder arguments for the specified encoder and quality."""
    enc = encoder if encoder in VIDEO_ENCODERS else DEFAULT_ENCODER
    config = VIDEO_ENCODERS[enc]
    return list(config.get(quality, config["high"]))


def probe_installed_encoders() -> set[str]:
    """Parse `ffmpeg -encoders` to find all encoders compiled into the installed FFmpeg binary."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return set()
    try:
        res = subprocess.run([ffmpeg, "-encoders"], capture_output=True, text=True, timeout=10)
        return {enc_id for enc_id in VIDEO_ENCODERS if enc_id in res.stdout}
    except Exception:
        return {"libx264"}


def probe_encoder_support(check_hardware: bool = True) -> list[dict]:
    """Return a detailed list of all supported encoders with their installed and hardware-ready state."""
    installed = probe_installed_encoders()
    results = []
    for enc_id, conf in VIDEO_ENCODERS.items():
        is_installed = enc_id in installed
        hw_ready = False
        if is_installed:
            if not conf["hardware"]:
                hw_ready = True
            elif check_hardware:
                try:
                    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi",
                           "-i", "nullsrc=s=256x256:d=0.05", "-c:v", enc_id, "-f", "null", "-"]
                    hw_ready = (subprocess.run(cmd, capture_output=True, timeout=5).returncode == 0)
                except Exception:
                    hw_ready = False
        results.append({
            "id": enc_id,
            "name": conf["name"],
            "codec": conf["codec"],
            "description": conf["description"],
            "hardware": conf["hardware"],
            "installed": is_installed,
            "available": hw_ready,
        })
    return results

