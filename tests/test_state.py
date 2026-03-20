"""Tests for app.state — idempotency, pruning, feedback, timestamp logic."""

import json
import os
import pytest
from datetime import date, timedelta
from unittest.mock import patch, mock_open, MagicMock

from app.state import (
    is_processed,
    has_digest_today,
    update_last_processed,
    update_feedback,
    prune_old_notebooks,
    get_recent_notebooks,
    record_notebook,
    save_state,
)


def _notebook(nb_type="digest", days_ago=0, slack_ts="1000.0", notebook_id="abc-123", company=None):
    d = (date.today() - timedelta(days=days_ago)).isoformat()
    entry = {"date": d, "notebook_id": notebook_id, "type": nb_type, "slack_ts": slack_ts}
    if company:
        entry["company"] = company
    return entry


# ---------------------------------------------------------------------------
# is_processed
# ---------------------------------------------------------------------------

class TestIsProcessed:
    def test_returns_true_when_ts_matches(self):
        state = {"notebooks": [_notebook(slack_ts="2000.0")]}
        assert is_processed(state, "2000.0") is True

    def test_returns_false_when_no_match(self):
        state = {"notebooks": [_notebook(slack_ts="2000.0")]}
        assert is_processed(state, "9999.0") is False

    def test_empty_notebooks(self):
        assert is_processed({"notebooks": []}, "1000.0") is False

    def test_missing_notebooks_key(self):
        assert is_processed({}, "1000.0") is False


# ---------------------------------------------------------------------------
# has_digest_today
# ---------------------------------------------------------------------------

class TestHasDigestToday:
    def test_returns_true_when_digest_today(self):
        state = {"notebooks": [_notebook(nb_type="digest", days_ago=0)]}
        assert has_digest_today(state) is True

    def test_returns_false_when_digest_yesterday(self):
        state = {"notebooks": [_notebook(nb_type="digest", days_ago=1)]}
        assert has_digest_today(state) is False

    def test_returns_false_for_pg_alert_today(self):
        state = {"notebooks": [_notebook(nb_type="pg_alert", days_ago=0)]}
        assert has_digest_today(state) is False

    def test_returns_false_empty(self):
        assert has_digest_today({"notebooks": []}) is False


# ---------------------------------------------------------------------------
# update_last_processed
# ---------------------------------------------------------------------------

class TestUpdateLastProcessed:
    def test_advances_when_newer(self):
        state = {"last_processed_ts": "1000.0"}
        update_last_processed(state, "2000.0")
        assert state["last_processed_ts"] == "2000.0"

    def test_does_not_regress(self):
        state = {"last_processed_ts": "2000.0"}
        update_last_processed(state, "1000.0")
        assert state["last_processed_ts"] == "2000.0"

    def test_sets_from_zero(self):
        state = {}
        update_last_processed(state, "1000.0")
        assert state["last_processed_ts"] == "1000.0"

    def test_equal_ts_no_change(self):
        state = {"last_processed_ts": "1000.0"}
        update_last_processed(state, "1000.0")
        assert state["last_processed_ts"] == "1000.0"


# ---------------------------------------------------------------------------
# update_feedback
# ---------------------------------------------------------------------------

class TestUpdateFeedback:
    def test_appends_to_empty(self):
        state = {}
        update_feedback(state, "great episode!")
        assert state["accumulated_feedback"] == "great episode!"

    def test_appends_to_existing(self):
        state = {"accumulated_feedback": "first feedback"}
        update_feedback(state, "second feedback")
        assert "first feedback" in state["accumulated_feedback"]
        assert "second feedback" in state["accumulated_feedback"]

    def test_caps_at_2000_chars(self):
        long_existing = "x" * 1990
        state = {"accumulated_feedback": long_existing}
        update_feedback(state, "new feedback here")
        assert len(state["accumulated_feedback"]) <= 2000

    def test_keeps_tail_not_head(self):
        # The last 2000 chars are kept (most recent feedback)
        state = {"accumulated_feedback": "old " * 600}
        update_feedback(state, "NEWEST")
        assert state["accumulated_feedback"].endswith("NEWEST")

    def test_empty_feedback_no_op(self):
        state = {"accumulated_feedback": "existing"}
        update_feedback(state, "")
        assert state["accumulated_feedback"] == "existing"

    def test_none_feedback_no_op(self):
        state = {"accumulated_feedback": "existing"}
        update_feedback(state, None)
        assert state["accumulated_feedback"] == "existing"


# ---------------------------------------------------------------------------
# prune_old_notebooks
# ---------------------------------------------------------------------------

class TestPruneOldNotebooks:
    def test_removes_entries_older_than_14_days(self):
        state = {
            "notebooks": [
                _notebook(days_ago=15),
                _notebook(days_ago=13),
                _notebook(days_ago=0),
            ]
        }
        prune_old_notebooks(state, days=14)
        assert len(state["notebooks"]) == 2

    def test_keeps_entries_within_window(self):
        state = {"notebooks": [_notebook(days_ago=13), _notebook(days_ago=0)]}
        prune_old_notebooks(state, days=14)
        assert len(state["notebooks"]) == 2

    def test_removes_all_old(self):
        state = {"notebooks": [_notebook(days_ago=20), _notebook(days_ago=30)]}
        prune_old_notebooks(state, days=14)
        assert state["notebooks"] == []

    def test_empty_notebooks(self):
        state = {"notebooks": []}
        prune_old_notebooks(state)
        assert state["notebooks"] == []

    def test_custom_days_window(self):
        state = {"notebooks": [_notebook(days_ago=5), _notebook(days_ago=10)]}
        prune_old_notebooks(state, days=7)
        assert len(state["notebooks"]) == 1


# ---------------------------------------------------------------------------
# get_recent_notebooks
# ---------------------------------------------------------------------------

class TestGetRecentNotebooks:
    def test_returns_notebooks_within_window(self):
        state = {
            "notebooks": [
                _notebook(days_ago=0),
                _notebook(days_ago=2),
                _notebook(days_ago=4),
            ]
        }
        recent = get_recent_notebooks(state, days=3)
        assert len(recent) == 2

    def test_excludes_older_than_window(self):
        state = {"notebooks": [_notebook(days_ago=10)]}
        assert get_recent_notebooks(state, days=3) == []

    def test_empty_state(self):
        assert get_recent_notebooks({}, days=3) == []


# ---------------------------------------------------------------------------
# save_state (atomic write)
# ---------------------------------------------------------------------------

class TestSaveState:
    def test_atomic_write(self, tmp_path):
        state_file = tmp_path / "state.json"
        state = {"last_processed_ts": "9999.0", "notebooks": []}
        with patch("app.state.STATE_PATH", str(state_file)):
            save_state(state)
        assert state_file.exists()
        loaded = json.loads(state_file.read_text())
        assert loaded["last_processed_ts"] == "9999.0"

    def test_no_tmp_file_left_behind(self, tmp_path):
        state_file = tmp_path / "state.json"
        state = {"notebooks": []}
        with patch("app.state.STATE_PATH", str(state_file)):
            save_state(state)
        assert not (tmp_path / "state.json.tmp").exists()
