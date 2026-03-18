"""Configuration and constants for AI for Breakfast automation."""

import glob
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_DIR = os.path.join(BASE_DIR, "audio")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
STATE_PATH = os.path.join(BASE_DIR, "state.json")
PRIMER_PATH = os.path.join(BASE_DIR, "dbt_primer.md")

NLM_PATH = "/Users/jaybishop/.local/bin/nlm"
FFMPEG_PATH = "/opt/homebrew/bin/ffmpeg"


def _find_claude_path():
    """Resolve the Claude CLI binary from the VS Code extension directory, picking the latest version."""
    pattern = os.path.expanduser(
        "~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude"
    )
    matches = sorted(glob.glob(pattern))
    if matches:
        return matches[-1]
    return "claude"  # fallback to PATH


CLAUDE_PATH = _find_claude_path()

JOE_USER_ID = "U0847KPJA2K"
CHANNEL_ID = "C0AJAFD7CLB"
SLACK_API_BASE = "https://slack.com/api"

MAX_POLL_SECONDS = 600
POLL_INTERVAL = 30


def load_config():
    """Load config.json and return dict with slack_bot_token, slack_channel_id."""
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)
