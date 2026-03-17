"""Configuration and constants for AI for Breakfast automation."""

import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_DIR = os.path.join(BASE_DIR, "audio")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
STATE_PATH = os.path.join(BASE_DIR, "state.json")
PRIMER_PATH = os.path.join(BASE_DIR, "dbt_primer.md")

NLM_PATH = "/Users/jaybishop/.local/bin/nlm"
FFMPEG_PATH = "/opt/homebrew/bin/ffmpeg"
CLAUDE_PATH = "/Users/jaybishop/.vscode/extensions/anthropic.claude-code-2.1.76-darwin-arm64/resources/native-binary/claude"

JOE_USER_ID = "U0847KPJA2K"
CHANNEL_ID = "C0AJAFD7CLB"
SLACK_API_BASE = "https://slack.com/api"

MAX_POLL_SECONDS = 600
POLL_INTERVAL = 30


def load_config():
    """Load config.json and return dict with slack_bot_token, slack_channel_id."""
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)
