#!/usr/bin/env python3
"""AI for Breakfast podcast automation -- entry point.

Usage: python3 /Users/jaybishop/Documents/claude/ai4breakfast/app/main.py
"""

import sys
import os

# Ensure the package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import load_config, CHANNEL_ID, JOE_USER_ID, AUDIO_DIR
from app.log import log
from app.state import (
    load_state,
    save_state,
    is_processed,
    has_digest_today,
    update_last_processed,
    prune_old_notebooks,
)
from app.classifier import classify_messages
from app.slack_reader import get_channel_messages
from app.pipeline import collect_feedback, run_digest, run_pg_alert
from app.audio import cleanup


def main():
    log.info("=" * 60)
    log.info("AI for Breakfast automation starting")
    log.info("=" * 60)

    # Load config and state
    config = load_config()
    state = load_state()
    token = config["slack_bot_token"]

    # Prune old notebook entries
    prune_old_notebooks(state)

    # Step 1: Fetch new messages (via Claude CLI + MCP Slack)
    messages = get_channel_messages(CHANNEL_ID, state.get("last_processed_ts", "0"))
    if not messages:
        log.info("No new messages. Exiting.")
        return

    # Step 2: Classify into digest URLs and PG alerts
    digest_urls, pg_alerts = classify_messages(messages, JOE_USER_ID)

    if not digest_urls and not pg_alerts:
        log.info("No actionable messages (no URLs from Joe). Updating timestamp.")
        max_ts = max(m.get("ts", "0") for m in messages)
        update_last_processed(state, max_ts)
        save_state(state)
        return

    # Step 3: Collect feedback from previous episodes
    try:
        collect_feedback(state, config)
    except Exception as e:
        log.warning("Feedback collection failed (non-fatal): %s", e)

    # Step 4: Process Daily Digest
    if digest_urls and not has_digest_today(state):
        try:
            run_digest(digest_urls, state, config)
        except Exception as e:
            log.error("Daily digest failed: %s", e, exc_info=True)
    elif digest_urls:
        log.info("Skipping digest -- already created one today")

    # Step 5: Process PG Alerts
    failed_ts = set()
    for alert in pg_alerts:
        if is_processed(state, alert["message_ts"]):
            log.info("Skipping already-processed PG Alert: %s", alert["message_ts"])
            continue
        try:
            run_pg_alert(alert, state, config)
        except Exception as e:
            log.error("PG Alert failed for %s: %s", alert["url"], e, exc_info=True)
            failed_ts.add(alert["message_ts"])

    # Step 6: Final state update and cleanup
    # Only advance last_processed_ts up to the last message before any failure,
    # so failed items are retried on the next run.
    if failed_ts:
        min_failed = min(failed_ts)
        safe_messages = [m for m in messages if m.get("ts", "0") < min_failed]
        if safe_messages:
            max_ts = max(m.get("ts", "0") for m in safe_messages)
            update_last_processed(state, max_ts)
            log.info("Partial state update: advanced to %s (stopped before failed ts %s)", max_ts, min_failed)
        else:
            log.info("No state timestamp update -- earliest message failed, will retry next run")
    else:
        max_ts = max(m.get("ts", "0") for m in messages)
        update_last_processed(state, max_ts)
    save_state(state)
    cleanup(AUDIO_DIR)

    log.info("=" * 60)
    log.info("AI for Breakfast automation complete")
    log.info("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log.error("Fatal error: %s", e, exc_info=True)
        sys.exit(1)
