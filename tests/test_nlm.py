"""Tests for app.nlm — UUID extraction and poll_status state machine."""

import json
import itertools
import pytest
from unittest.mock import patch, MagicMock

from app.nlm import _extract_uuid, poll_status, NLMError


def _clock(*values):
    """
    Return a time.time side_effect that cycles through the given values.
    Using cycle avoids StopIteration when logging internally calls time.time().
    """
    return itertools.cycle(values)


# ---------------------------------------------------------------------------
# _extract_uuid
# ---------------------------------------------------------------------------

class TestExtractUuid:
    def test_basic_uuid(self):
        text = "Created notebook edb23d11-53cf-43e1-9951-270c3511d71a"
        assert _extract_uuid(text) == "edb23d11-53cf-43e1-9951-270c3511d71a"

    def test_uuid_at_start(self):
        assert _extract_uuid("edb23d11-53cf-43e1-9951-270c3511d71a some text") == "edb23d11-53cf-43e1-9951-270c3511d71a"

    def test_returns_first_uuid(self):
        text = "aabbccdd-0000-0000-0000-000000000001 and aabbccdd-0000-0000-0000-000000000002"
        assert _extract_uuid(text) == "aabbccdd-0000-0000-0000-000000000001"

    def test_no_uuid_returns_none(self):
        assert _extract_uuid("no uuid here") is None

    def test_empty_string(self):
        assert _extract_uuid("") is None

    def test_partial_uuid_not_matched(self):
        assert _extract_uuid("edb23d11-53cf-43e1") is None


# ---------------------------------------------------------------------------
# poll_status
# ---------------------------------------------------------------------------

def _make_run_response(data):
    """Return a mock _run that yields json.dumps(data) as stdout."""
    return MagicMock(return_value=(json.dumps(data), ""))


class TestPollStatus:
    def _run_poll(self, run_side_effect, max_secs=5, interval=0):
        with patch("app.nlm._run", side_effect=run_side_effect):
            with patch("app.nlm.time.sleep"):
                with patch("app.nlm.time.time", side_effect=_make_clock(max_secs)):
                    return poll_status("fake-id", max_secs=max_secs, interval=interval)

    def test_completed_audio_dict_response(self):
        artifact = {"type": "audio", "status": "completed", "audio_url": "https://example.com/audio.m4a"}
        data = {"artifacts": [artifact]}
        with patch("app.nlm._run", return_value=(json.dumps(data), "")):
            with patch("app.nlm.time.sleep"):
                with patch("app.nlm.time.time", side_effect=_clock(0, 1)):
                    result = poll_status("fake-id", max_secs=10, interval=0)
        assert result["status"] == "completed"

    def test_completed_audio_list_response(self):
        # The bug we fixed: status returns a list directly
        artifact = {"type": "audio", "status": "completed", "audio_url": "https://example.com/audio.m4a"}
        data = [artifact]
        with patch("app.nlm._run", return_value=(json.dumps(data), "")):
            with patch("app.nlm.time.sleep"):
                with patch("app.nlm.time.time", side_effect=_clock(0, 1)):
                    result = poll_status("fake-id", max_secs=10, interval=0)
        assert result["status"] == "completed"

    def test_failed_audio_raises(self):
        # "failed" status raises NLMError inside the loop, which is caught by the
        # except clause and retried. The function ultimately raises "timed out".
        # Clock: start=0, while-check=100 → immediately exceeds max_secs=10.
        artifact = {"type": "audio", "status": "failed"}
        data = [artifact]
        with patch("app.nlm._run", return_value=(json.dumps(data), "")):
            with patch("app.nlm.time.sleep"):
                with patch("app.nlm.time.time", side_effect=_clock(0, 100)):
                    with pytest.raises(NLMError, match="timed out"):
                        poll_status("fake-id", max_secs=10, interval=0)

    def test_unknown_status_with_audio_url_succeeds(self):
        artifact = {"type": "audio", "status": "unknown", "audio_url": "https://example.com/audio.m4a"}
        data = [artifact]
        with patch("app.nlm._run", return_value=(json.dumps(data), "")):
            with patch("app.nlm.time.sleep"):
                with patch("app.nlm.time.time", side_effect=_clock(0, 1)):
                    result = poll_status("fake-id", max_secs=10, interval=0)
        assert result.get("audio_url") is not None

    def test_timeout_raises(self):
        artifact = {"type": "audio", "status": "in_progress"}
        data = [artifact]
        # Return 0 for start, then 100 to immediately exceed max_secs=10
        with patch("app.nlm._run", return_value=(json.dumps(data), "")):
            with patch("app.nlm.time.sleep"):
                with patch("app.nlm.time.time", side_effect=_clock(0, 100)):
                    with pytest.raises(NLMError, match="timed out"):
                        poll_status("fake-id", max_secs=10, interval=0)

    def test_empty_artifacts_keeps_polling(self):
        # First call returns empty, second returns completed
        artifact = {"type": "audio", "status": "completed", "audio_url": "https://example.com/a.m4a"}
        responses = [
            (json.dumps([]), ""),
            (json.dumps([artifact]), ""),
        ]
        with patch("app.nlm._run", side_effect=responses):
            with patch("app.nlm.time.sleep"):
                with patch("app.nlm.time.time", side_effect=_clock(0, 1, 2)):
                    result = poll_status("fake-id", max_secs=10, interval=0)
        assert result["status"] == "completed"

    def test_no_audio_artifact_keeps_polling(self):
        # First call has non-audio artifact, second has audio
        artifact_audio = {"type": "audio", "status": "completed", "audio_url": "https://example.com/a.m4a"}
        responses = [
            (json.dumps([{"type": "video", "status": "completed"}]), ""),
            (json.dumps([artifact_audio]), ""),
        ]
        with patch("app.nlm._run", side_effect=responses):
            with patch("app.nlm.time.sleep"):
                with patch("app.nlm.time.time", side_effect=_clock(0, 1, 2)):
                    result = poll_status("fake-id", max_secs=10, interval=0)
        assert result["type"] == "audio"
