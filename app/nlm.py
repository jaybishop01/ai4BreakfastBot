"""NotebookLM CLI (nlm) subprocess wrappers."""

import json
import re
import time
import subprocess

from .config import NLM_PATH, MAX_POLL_SECONDS, POLL_INTERVAL
from .log import log

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


class NLMError(Exception):
    """Raised when an nlm CLI command fails."""
    pass


def _run(args, timeout=120):
    """Run an nlm CLI command and return (stdout, stderr)."""
    cmd = [NLM_PATH] + args
    log.info("nlm: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            log.error("nlm failed (rc=%d): %s", result.returncode, result.stderr.strip())
            raise NLMError(f"nlm {args[0]} failed: {result.stderr.strip()}")
        return result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        log.error("nlm timed out after %ds: %s", timeout, args)
        raise NLMError(f"nlm {args[0]} timed out after {timeout}s")


def _extract_uuid(text):
    """Extract the first UUID from text."""
    match = _UUID_RE.search(text)
    if match:
        return match.group(0)
    return None


def create_notebook(title):
    """Create a new NotebookLM notebook. Returns notebook_id."""
    stdout, _ = _run(["notebook", "create", title])
    notebook_id = _extract_uuid(stdout)
    if not notebook_id:
        raise NLMError(f"Could not extract notebook ID from output: {stdout[:200]}")
    log.info("Created notebook: %s (%s)", title, notebook_id)
    return notebook_id


def add_url_sources(notebook_id, urls):
    """Add URL sources to a notebook. Tries batch first, falls back to individual."""
    if not urls:
        return

    # Try batch add
    args = ["source", "add", notebook_id, "--wait"]
    for url in urls:
        args.extend(["--url", url])

    try:
        _run(args, timeout=180)
        log.info("Added %d URL sources (batch)", len(urls))
        return
    except NLMError:
        log.warning("Batch URL add failed, trying individually...")

    # Fallback: add one at a time, skip failures
    added = 0
    for url in urls:
        try:
            _run(["source", "add", notebook_id, "--url", url, "--wait"], timeout=120)
            added += 1
        except NLMError:
            log.warning("Skipping failed URL source: %s", url)
    log.info("Added %d/%d URL sources (individual)", added, len(urls))


def add_file_source(notebook_id, filepath, title):
    """Add a local file as a source to a notebook."""
    _run(["source", "add", notebook_id, "--file", filepath, "--title", title, "--wait"], timeout=120)
    log.info("Added file source: %s", title)


def add_text_source(notebook_id, text, title):
    """Add text content as a source to a notebook."""
    _run(["source", "add", notebook_id, "--text", text, "--title", title, "--wait"], timeout=120)
    log.info("Added text source: %s", title)


def create_audio(notebook_id, fmt="deep_dive", length="default", focus=""):
    """Start audio generation for a notebook. Returns immediately (async)."""
    args = ["audio", "create", notebook_id, "-f", fmt, "-l", length, "-y"]
    if focus:
        args.extend(["--focus", focus])
    _run(args, timeout=60)
    log.info("Audio generation started (format=%s, length=%s)", fmt, length)


def poll_status(notebook_id, max_secs=None, interval=None):
    """Poll studio status until audio is completed or failed. Returns artifact info dict."""
    if max_secs is None:
        max_secs = MAX_POLL_SECONDS
    if interval is None:
        interval = POLL_INTERVAL

    start = time.time()
    while time.time() - start < max_secs:
        try:
            stdout, _ = _run(["studio", "status", notebook_id, "--json"], timeout=30)
            data = json.loads(stdout)

            if isinstance(data, list):
                artifacts = data
            else:
                artifacts = data.get("artifacts", [])
            if not artifacts:
                log.info("No artifacts yet, waiting %ds...", interval)
                time.sleep(interval)
                continue

            audio = None
            for a in artifacts:
                if a.get("type") == "audio":
                    audio = a
                    break

            if not audio:
                log.info("No audio artifact yet, waiting %ds...", interval)
                time.sleep(interval)
                continue

            status = audio.get("status", "")
            if status == "completed":
                log.info("Audio generation completed")
                return audio
            elif status == "failed":
                raise NLMError("Audio generation failed")
            elif status in ("in_progress", "unknown", ""):
                # "unknown" with an audio_url means it's done
                if audio.get("audio_url"):
                    log.info("Audio ready (status=%s, has audio_url)", status)
                    return audio
                elapsed = int(time.time() - start)
                log.info("Audio status=%s, elapsed=%ds, waiting %ds...", status, elapsed, interval)
                time.sleep(interval)
            else:
                log.info("Audio status=%s, waiting %ds...", status, interval)
                time.sleep(interval)

        except (json.JSONDecodeError, NLMError) as e:
            log.warning("Poll error: %s, retrying...", e)
            time.sleep(interval)

    raise NLMError(f"Audio generation timed out after {max_secs}s")


def download_audio(notebook_id, output_path):
    """Download audio artifact to the specified path."""
    _run(["download", "audio", notebook_id, "-o", output_path, "--no-progress"], timeout=120)
    log.info("Downloaded audio to %s", output_path)
