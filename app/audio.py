"""FFmpeg audio conversion and cleanup."""

import glob
import os
import subprocess

from .config import FFMPEG_PATH
from .log import log


def convert_to_mp3(input_path, output_path):
    """Convert an m4a/mp4 audio file to mp3 using ffmpeg.

    Returns True on success, False on failure.
    """
    log.info("Converting %s -> %s", input_path, output_path)
    try:
        subprocess.run(
            [FFMPEG_PATH, "-i", input_path, "-vn", "-acodec", "libmp3lame", "-q:a", "2", output_path, "-y"],
            capture_output=True,
            text=True,
            timeout=300,
            check=True,
        )
        log.info("Conversion complete: %s (%d bytes)", output_path, os.path.getsize(output_path))
        return True
    except subprocess.CalledProcessError as e:
        log.error("ffmpeg conversion failed: %s", e.stderr[:200] if e.stderr else "unknown error")
        return False
    except subprocess.TimeoutExpired:
        log.error("ffmpeg conversion timed out")
        return False


def cleanup(audio_dir):
    """Remove all audio files from the temp directory."""
    patterns = ["*.m4a", "*.mp4", "*.mp3"]
    removed = 0
    for pattern in patterns:
        for f in glob.glob(os.path.join(audio_dir, pattern)):
            try:
                os.remove(f)
                removed += 1
            except OSError as e:
                log.warning("Failed to remove %s: %s", f, e)
    if removed:
        log.info("Cleaned up %d audio files", removed)
