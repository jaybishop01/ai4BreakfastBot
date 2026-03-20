"""Tests for app.slack_reader — JSON parsing and markdown fence stripping."""

import pytest
from app.slack_reader import _strip_markdown_fences, _parse_json


# ---------------------------------------------------------------------------
# _strip_markdown_fences
# ---------------------------------------------------------------------------

class TestStripMarkdownFences:
    def test_no_fences(self):
        assert _strip_markdown_fences('["a", "b"]') == '["a", "b"]'

    def test_basic_json_fence(self):
        text = "```\n[1, 2, 3]\n```"
        assert _strip_markdown_fences(text) == "[1, 2, 3]"

    def test_json_labeled_fence(self):
        text = "```json\n{\"key\": \"value\"}\n```"
        result = _strip_markdown_fences(text)
        assert result == '{"key": "value"}'

    def test_multiline_content(self):
        text = "```\n[\n  {\"a\": 1},\n  {\"b\": 2}\n]\n```"
        result = _strip_markdown_fences(text)
        assert "[" in result and "{" in result

    def test_preserves_text_without_fences(self):
        text = "some plain text"
        assert _strip_markdown_fences(text) == "some plain text"

    def test_strips_surrounding_whitespace(self):
        text = "  ```\n[1]\n```  "
        result = _strip_markdown_fences(text)
        assert result == "[1]"


# ---------------------------------------------------------------------------
# _parse_json
# ---------------------------------------------------------------------------

class TestParseJson:
    def test_plain_array(self):
        result = _parse_json('[{"user": "U123", "ts": "1000.0"}]')
        assert isinstance(result, list)
        assert result[0]["user"] == "U123"

    def test_plain_object(self):
        result = _parse_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_fenced_json(self):
        text = "```json\n[{\"user\": \"U123\"}]\n```"
        result = _parse_json(text)
        assert isinstance(result, list)

    def test_json_with_preamble(self):
        text = "Here are the messages:\n[{\"user\": \"U123\"}]"
        result = _parse_json(text)
        assert isinstance(result, list)
        assert result[0]["user"] == "U123"

    def test_empty_array(self):
        assert _parse_json("[]") == []

    def test_empty_string(self):
        assert _parse_json("") is None

    def test_none_input(self):
        assert _parse_json(None) is None

    def test_invalid_json(self):
        assert _parse_json("this is not json at all") is None

    def test_json_embedded_in_prose(self):
        text = 'The result is [{"ts": "999.0", "user": "UABC"}] as requested.'
        result = _parse_json(text)
        assert isinstance(result, list)
        assert result[0]["ts"] == "999.0"

    def test_plain_object_no_arrays(self):
        # _parse_json tries [ first; use an object with no nested arrays
        text = '{"key": "value", "count": 1}'
        result = _parse_json(text)
        assert result["count"] == 1
