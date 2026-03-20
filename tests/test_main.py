"""Tests for main.py — partial failure state update logic."""

import pytest
from unittest.mock import patch, MagicMock, call


def _make_messages(*timestamps):
    return [{"user": "U123", "ts": ts, "text": f"msg {ts}"} for ts in timestamps]


def _run_main_step6(messages, pg_alerts, failed_ts, initial_ts="0"):
    """
    Simulate the Step 6 logic from main.py in isolation.
    Returns the final value of state["last_processed_ts"].
    """
    from app.state import update_last_processed

    state = {"last_processed_ts": initial_ts}

    if failed_ts:
        min_failed = min(failed_ts)
        safe_messages = [m for m in messages if m.get("ts", "0") < min_failed]
        if safe_messages:
            max_ts = max(m.get("ts", "0") for m in safe_messages)
            update_last_processed(state, max_ts)
    else:
        max_ts = max(m.get("ts", "0") for m in messages)
        update_last_processed(state, max_ts)

    return state.get("last_processed_ts", initial_ts)


class TestPartialFailureStateUpdate:
    def test_no_failures_advances_to_max(self):
        messages = _make_messages("1000.0", "2000.0", "3000.0")
        result = _run_main_step6(messages, [], failed_ts=set())
        assert result == "3000.0"

    def test_first_message_fails_no_advance(self):
        messages = _make_messages("1000.0", "2000.0", "3000.0")
        result = _run_main_step6(messages, [], failed_ts={"1000.0"}, initial_ts="500.0")
        # No safe messages before the failure; ts should not advance
        assert result == "500.0"

    def test_middle_message_fails_advances_to_before_failure(self):
        messages = _make_messages("1000.0", "2000.0", "3000.0")
        result = _run_main_step6(messages, [], failed_ts={"2000.0"})
        assert result == "1000.0"

    def test_last_message_fails_advances_to_second_to_last(self):
        messages = _make_messages("1000.0", "2000.0", "3000.0")
        result = _run_main_step6(messages, [], failed_ts={"3000.0"})
        assert result == "2000.0"

    def test_multiple_failures_stops_at_earliest(self):
        messages = _make_messages("1000.0", "2000.0", "3000.0", "4000.0")
        result = _run_main_step6(messages, [], failed_ts={"2000.0", "3000.0"})
        assert result == "1000.0"

    def test_single_message_fails_no_advance(self):
        messages = _make_messages("1000.0")
        result = _run_main_step6(messages, [], failed_ts={"1000.0"}, initial_ts="500.0")
        assert result == "500.0"

    def test_single_message_succeeds_advances(self):
        messages = _make_messages("1000.0")
        result = _run_main_step6(messages, [], failed_ts=set())
        assert result == "1000.0"

    def test_does_not_regress_existing_ts(self):
        # If initial ts is already higher than safe messages, don't regress
        messages = _make_messages("100.0", "200.0", "300.0")
        result = _run_main_step6(messages, [], failed_ts={"200.0"}, initial_ts="500.0")
        # safe messages are ["100.0"], but initial is "500.0", so no regression
        assert result == "500.0"
