"""Gong/Glean context lookup via Claude CLI shell-out."""

import subprocess

from .config import CLAUDE_PATH
from .log import log


def lookup_gong_context(rep_name, company):
    """Shell out to Claude CLI to search Glean for recent call themes.

    Returns a summary string (max 2000 chars) or None if no results/error.
    """
    prompt = (
        f'Use mcp__glean__meeting_lookup to search for meetings: '
        f'participants:"{rep_name}" topic:"{company}" after:now-3M before:now '
        f'extract_transcript:"false". '
        f'If results are found, provide a 2-3 sentence summary of the key discussion themes '
        f'between {rep_name} and {company}. Focus on business needs, pain points, and '
        f'opportunities discussed. If no results are found, respond with exactly: NO_RESULTS'
    )

    try:
        log.info("Looking up Gong context: rep=%s, company=%s", rep_name, company)
        result = subprocess.run(
            [CLAUDE_PATH, "--print", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=60,
        )

        stdout = result.stdout.strip()
        if not stdout or "NO_RESULTS" in stdout or result.returncode != 0:
            log.info("No Gong context found for %s / %s", rep_name, company)
            return None

        # Cap at 2000 chars
        context = stdout[:2000]
        log.info("Gong context found (%d chars)", len(context))
        return context

    except subprocess.TimeoutExpired:
        log.warning("Claude CLI timed out for Gong lookup (%s / %s)", rep_name, company)
        return None
    except FileNotFoundError:
        log.warning("Claude CLI not found at %s", CLAUDE_PATH)
        return None
    except Exception as e:
        log.warning("Gong lookup error: %s", e)
        return None
