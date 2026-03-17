"""Slack read operations via Claude CLI (uses MCP Slack tools with proper auth).

The bot token only has upload scopes. For reads (channel history, threads,
user profiles), we shell out to Claude CLI which has the MCP Slack integration
with full read access.

Strategy: use --model haiku for speed, --output-format json for structured data,
and increase timeouts since MCP startup adds overhead.
"""

import json
import subprocess

from .config import CLAUDE_PATH
from .log import log


def _claude_prompt(prompt, timeout=120):
    """Run a Claude CLI prompt and return stdout."""
    try:
        result = subprocess.run(
            [CLAUDE_PATH, "--print", "--model", "haiku", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            log.warning("Claude CLI returned rc=%d: %s", result.returncode, result.stderr[:200])
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        log.error("Claude CLI timed out after %ds", timeout)
        return ""
    except FileNotFoundError:
        log.error("Claude CLI not found at %s", CLAUDE_PATH)
        return ""


def _strip_markdown_fences(text):
    """Remove markdown code fences from text if present."""
    text = text.strip()
    if "```" not in text:
        return text
    lines = text.split("\n")
    result = []
    in_block = False
    for line in lines:
        if line.strip().startswith("```") and not in_block:
            in_block = True
            continue
        elif line.strip().startswith("```") and in_block:
            in_block = False
            continue
        elif in_block:
            result.append(line)
    return "\n".join(result) if result else text


def _parse_json(output):
    """Try to parse JSON from Claude output, handling markdown fences."""
    if not output:
        return None
    cleaned = _strip_markdown_fences(output)
    # Also try to find JSON array/object in the text
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        idx_start = cleaned.find(start_char)
        idx_end = cleaned.rfind(end_char)
        if idx_start != -1 and idx_end > idx_start:
            try:
                return json.loads(cleaned[idx_start:idx_end + 1])
            except json.JSONDecodeError:
                continue
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def get_channel_messages(channel_id, oldest_ts):
    """Read channel messages since oldest_ts via Claude CLI + MCP Slack.

    Returns list of dicts with keys: user, ts, text
    """
    prompt = (
        f'Use the mcp__slack__slack_read_channel tool to read messages from channel "{channel_id}" '
        f'with oldest="{oldest_ts}" and limit=100. '
        f'Then return ONLY a JSON array where each element has: '
        f'"user" (the user ID like U0847KPJA2K), "ts" (the Message TS string), '
        f'"text" (the full message text). '
        f'Return ONLY valid JSON, no explanation. If no messages, return [].'
    )

    output = _claude_prompt(prompt, timeout=120)
    messages = _parse_json(output)
    if messages is None:
        log.warning("Failed to parse channel messages from Claude output")
        log.debug("Raw output: %s", output[:500] if output else "(empty)")
        return []
    if not isinstance(messages, list):
        log.warning("Expected list, got %s", type(messages).__name__)
        return []
    log.info("Got %d messages from Claude Slack read", len(messages))
    return messages


def get_thread_replies(channel_id, thread_ts):
    """Read thread replies via Claude CLI + MCP Slack.

    Returns list of reply dicts with keys: user, ts, text, bot_id
    """
    prompt = (
        f'Use the mcp__slack__slack_read_thread tool with channel_id="{channel_id}" '
        f'and message_ts="{thread_ts}". '
        f'Return ONLY a JSON array of REPLY messages (skip the parent). '
        f'Each element: "user" (user ID), "ts" (message TS), "text" (text), '
        f'"bot_id" (string if from a bot, null otherwise). '
        f'Return ONLY valid JSON. If no replies, return [].'
    )

    output = _claude_prompt(prompt, timeout=90)
    replies = _parse_json(output)
    if replies is None or not isinstance(replies, list):
        log.info("No parseable replies from thread %s", thread_ts)
        return []
    log.info("Got %d replies from thread %s", len(replies), thread_ts)
    return replies


def get_user_name(user_id):
    """Look up a user's real name via Claude CLI + MCP Slack."""
    prompt = (
        f'Use the mcp__slack__slack_read_user_profile tool with user_id="{user_id}". '
        f'Return ONLY the person\'s Real Name as plain text, nothing else.'
    )

    output = _claude_prompt(prompt, timeout=60)
    if output and len(output) < 100 and "error" not in output.lower():
        name = output.strip().split("\n")[0].strip()
        if name:
            log.info("User %s -> %s", user_id, name)
            return name

    log.warning("Could not resolve user name for %s", user_id)
    return user_id
