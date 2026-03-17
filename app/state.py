"""State management and idempotency tracking."""

import json
import os
from datetime import date, datetime, timedelta

from .config import STATE_PATH
from .log import log


def load_state():
    """Load state.json, returning dict with last_processed_ts, notebooks, accumulated_feedback."""
    with open(STATE_PATH, "r") as f:
        return json.load(f)


def save_state(state):
    """Atomically write state.json (write to tmp, then rename)."""
    tmp_path = STATE_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")
    os.rename(tmp_path, STATE_PATH)
    log.info("State saved")


def is_processed(state, message_ts):
    """Check if a message has already been processed (by slack_ts in notebooks)."""
    return any(nb.get("slack_ts") == message_ts for nb in state.get("notebooks", []))


def has_digest_today(state):
    """Check if a daily digest has already been created for today."""
    today = date.today().isoformat()
    return any(
        nb.get("type") == "digest" and nb.get("date") == today
        for nb in state.get("notebooks", [])
    )


def record_notebook(state, notebook_id, nb_type, slack_ts, company=None):
    """Record a completed notebook in state and save immediately."""
    entry = {
        "date": date.today().isoformat(),
        "notebook_id": notebook_id,
        "type": nb_type,
        "slack_ts": slack_ts,
    }
    if company:
        entry["company"] = company
    state.setdefault("notebooks", []).append(entry)
    save_state(state)
    log.info("Recorded notebook %s (type=%s)", notebook_id, nb_type)


def update_feedback(state, feedback_text):
    """Append new feedback to accumulated_feedback, capping at 2000 chars."""
    current = state.get("accumulated_feedback", "")
    if feedback_text:
        combined = (current + "\n" + feedback_text).strip()
        state["accumulated_feedback"] = combined[-2000:]
        log.info("Updated accumulated feedback (%d chars)", len(state["accumulated_feedback"]))


def update_last_processed(state, ts):
    """Set last_processed_ts to the max of current and new timestamp."""
    current = state.get("last_processed_ts", "0")
    if ts > current:
        state["last_processed_ts"] = ts
        log.info("Updated last_processed_ts to %s", ts)


def prune_old_notebooks(state, days=14):
    """Remove notebook entries older than `days` to prevent unbounded growth."""
    cutoff = (datetime.now() - timedelta(days=days)).date().isoformat()
    before = len(state.get("notebooks", []))
    state["notebooks"] = [
        nb for nb in state.get("notebooks", [])
        if nb.get("date", "9999-99-99") >= cutoff
    ]
    after = len(state["notebooks"])
    if before != after:
        log.info("Pruned %d old notebook entries", before - after)


def get_recent_notebooks(state, days=3):
    """Return notebooks from the last `days` days."""
    cutoff = (datetime.now() - timedelta(days=days)).date().isoformat()
    return [
        nb for nb in state.get("notebooks", [])
        if nb.get("date", "0000-00-00") >= cutoff
    ]
