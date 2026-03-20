"""Archive fallback for paywalled or failed URL sources.

After adding URLs to a NotebookLM notebook, NLM silently drops any it can't
fetch (paywall, bot block, etc.) — no error is raised, the source just doesn't
appear in the source list. This module detects those failures by comparing
submitted URLs against what NLM actually loaded, then retries each failed URL
via archive.ph and the Wayback Machine before giving up.
"""

import requests

from .log import log
from . import nlm

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ai4breakfast-archiver/1.0)"}
_TIMEOUT = 10


def _try_archive_ph(url):
    """Return the archive.ph URL for a snapshot if one exists, else None."""
    try:
        resp = requests.head(
            f"https://archive.ph/newest/{url}",
            headers=_HEADERS,
            allow_redirects=False,
            timeout=_TIMEOUT,
        )
        # archive.ph redirects to the snapshot on success
        if resp.status_code in (301, 302):
            location = resp.headers.get("Location", "")
            if "archive.ph" in location or "archive.is" in location:
                return location
        # Some snapshots return 200 directly at the canonical URL
        if resp.status_code == 200:
            return f"https://archive.ph/newest/{url}"
    except Exception as e:
        log.debug("archive.ph check failed for %s: %s", url, e)
    return None


def _try_wayback(url):
    """Return the Wayback Machine URL for the closest snapshot if one exists, else None."""
    try:
        resp = requests.get(
            f"https://archive.org/wayback/available?url={url}",
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        data = resp.json()
        snapshot = data.get("archived_snapshots", {}).get("closest", {})
        if snapshot.get("available") and snapshot.get("url"):
            return snapshot["url"]
    except Exception as e:
        log.debug("Wayback check failed for %s: %s", url, e)
    return None


def resolve_failed_sources(notebook_id, submitted_urls):
    """Check which submitted URLs failed to load in NLM and retry via archives.

    Args:
        notebook_id: NotebookLM notebook ID.
        submitted_urls: List of URLs originally passed to add_url_sources.

    Returns:
        List of URLs that could not be resolved even after archive fallback.
    """
    if not submitted_urls:
        return []

    # Determine which URLs NLM actually loaded
    try:
        loaded = nlm.list_sources(notebook_id)
        loaded_urls = {s.get("url") for s in loaded if s.get("url")}
    except nlm.NLMError as e:
        log.warning("Could not list sources to verify loading: %s", e)
        return []

    failed = [u for u in submitted_urls if u not in loaded_urls]

    if not failed:
        log.info("All %d URL source(s) loaded successfully", len(submitted_urls))
        return []

    log.warning(
        "%d URL(s) not loaded by NLM (paywall or fetch error) — attempting archive fallback",
        len(failed),
    )

    still_failed = []
    for url in failed:
        log.info("Trying archive fallback for: %s", url)
        archive_url = _try_archive_ph(url) or _try_wayback(url)

        if not archive_url:
            log.warning("No archive found for: %s", url)
            still_failed.append(url)
            continue

        log.info("Archive found: %s -> %s", url, archive_url)
        try:
            nlm.add_url_sources(notebook_id, [archive_url])
            log.info("Archive source added successfully: %s", archive_url)
        except nlm.NLMError:
            log.warning("Archive URL also failed to load: %s", archive_url)
            still_failed.append(url)

    if still_failed:
        log.warning(
            "%d URL(s) could not be resolved after archive fallback: %s",
            len(still_failed),
            still_failed,
        )
    else:
        log.info("All failed sources resolved via archives")

    return still_failed
