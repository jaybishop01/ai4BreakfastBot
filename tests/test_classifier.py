"""Tests for app.classifier — URL extraction, company mapping, message classification."""

import pytest
from app.classifier import extract_urls, parse_tagged_user, extract_company, classify_messages

JOE = "U0847KPJA2K"


# ---------------------------------------------------------------------------
# extract_urls
# ---------------------------------------------------------------------------

class TestExtractUrls:
    def test_basic_url(self):
        assert extract_urls("<https://example.com>") == ["https://example.com"]

    def test_url_with_display_text(self):
        assert extract_urls("<https://example.com|Click here>") == ["https://example.com"]

    def test_multiple_urls(self):
        text = "<https://a.com> and <https://b.com>"
        assert extract_urls(text) == ["https://a.com", "https://b.com"]

    def test_deduplicates_urls(self):
        text = "<https://a.com> <https://a.com>"
        assert extract_urls(text) == ["https://a.com"]

    def test_ignores_user_tags(self):
        assert extract_urls("<@U0847KPJA2K>") == []

    def test_ignores_channel_refs(self):
        assert extract_urls("<#C0AJAFD7CLB>") == []

    def test_empty_string(self):
        assert extract_urls("") == []

    def test_no_urls(self):
        assert extract_urls("just some text with no links") == []

    def test_mixed_content(self):
        text = "Hey <@U123>, check out <https://news.com|this article> and <https://other.com>"
        assert extract_urls(text) == ["https://news.com", "https://other.com"]

    def test_http_url(self):
        assert extract_urls("<http://example.com>") == ["http://example.com"]


# ---------------------------------------------------------------------------
# parse_tagged_user
# ---------------------------------------------------------------------------

class TestParseTaggedUser:
    def test_basic_tag(self):
        assert parse_tagged_user("<@U0550EH7H44>") == "U0550EH7H44"

    def test_tag_with_display_name(self):
        assert parse_tagged_user("<@U0550EH7H44|john>") == "U0550EH7H44"

    def test_no_tag(self):
        assert parse_tagged_user("no tag here") is None

    def test_tag_in_sentence(self):
        assert parse_tagged_user("PG Alert <@UABC123> <https://example.com>") == "UABC123"

    def test_returns_first_tag(self):
        assert parse_tagged_user("<@UAAA111> and <@UBBB222>") == "UAAA111"


# ---------------------------------------------------------------------------
# extract_company
# ---------------------------------------------------------------------------

class TestExtractCompany:
    def test_known_domain(self):
        assert extract_company("https://cox.com/article") == ("Cox Automotive", True)

    def test_known_domain_with_www(self):
        assert extract_company("https://www.delta.com/news") == ("Delta Air Lines", True)

    def test_known_subdomain(self):
        assert extract_company("https://careers.hilton.com/jobs") == ("Hilton", True)

    def test_unknown_domain_fallback(self):
        company, known = extract_company("https://somecompany.com/page")
        assert company == "Somecompany"
        assert known is False

    def test_hyphenated_domain_fallback(self):
        company, known = extract_company("https://my-company.com/page")
        assert company == "My Company"
        assert known is False

    def test_strategy_com(self):
        # The domain that triggered today's bug
        company, known = extract_company("https://www.strategy.com/software/customer-stories/diageo")
        assert company == "Strategy"
        assert known is False

    def test_invalid_url(self):
        # urlparse("not-a-url") has no hostname, so domain="" → title("") → ""
        company, known = extract_company("not-a-url")
        assert isinstance(company, str)  # doesn't raise

    def test_known_domain_coxautoinc(self):
        assert extract_company("https://coxautoinc.com/page") == ("Cox Automotive", True)


# ---------------------------------------------------------------------------
# classify_messages
# ---------------------------------------------------------------------------

class TestClassifyMessages:
    def _msg(self, text, user=JOE, ts="1000.0"):
        return {"user": user, "ts": ts, "text": text}

    def test_digest_url(self):
        msgs = [self._msg("<https://news.com/article>")]
        digest_urls, pg_alerts = classify_messages(msgs, JOE)
        assert digest_urls == ["https://news.com/article"]
        assert pg_alerts == []

    def test_pg_alert(self):
        msgs = [self._msg("PG Alert <@UREP123> <https://cox.com/article>", ts="2000.0")]
        digest_urls, pg_alerts = classify_messages(msgs, JOE)
        assert digest_urls == []
        assert len(pg_alerts) == 1
        assert pg_alerts[0]["url"] == "https://cox.com/article"
        assert pg_alerts[0]["tagged_user_id"] == "UREP123"
        assert pg_alerts[0]["message_ts"] == "2000.0"

    def test_filters_non_joe_messages(self):
        msgs = [self._msg("<https://news.com/article>", user="USOMEONEELSE")]
        digest_urls, pg_alerts = classify_messages(msgs, JOE)
        assert digest_urls == []
        assert pg_alerts == []

    def test_message_without_url_skipped(self):
        msgs = [self._msg("just some text", user=JOE)]
        digest_urls, pg_alerts = classify_messages(msgs, JOE)
        assert digest_urls == []
        assert pg_alerts == []

    def test_pg_alert_case_insensitive(self):
        msgs = [self._msg("pg ALERT <@UREP123> <https://example.com>")]
        _, pg_alerts = classify_messages(msgs, JOE)
        assert len(pg_alerts) == 1

    def test_pg_alert_without_tag_skipped(self):
        # PG alert with no @user tag — should be skipped with a warning
        msgs = [self._msg("PG Alert <https://example.com>")]
        digest_urls, pg_alerts = classify_messages(msgs, JOE)
        assert pg_alerts == []
        assert digest_urls == []  # also not a digest since it says "pg alert"

    def test_multiple_digest_urls_in_one_message(self):
        msgs = [self._msg("<https://a.com> <https://b.com>")]
        digest_urls, _ = classify_messages(msgs, JOE)
        assert digest_urls == ["https://a.com", "https://b.com"]

    def test_mixed_messages(self):
        msgs = [
            self._msg("<https://news1.com>", ts="1000.0"),
            self._msg("PG Alert <@UREP1> <https://cox.com>", ts="2000.0"),
            self._msg("<https://news2.com>", ts="3000.0"),
            self._msg("not from joe", user="UOTHER", ts="4000.0"),
        ]
        digest_urls, pg_alerts = classify_messages(msgs, JOE)
        assert digest_urls == ["https://news1.com", "https://news2.com"]
        assert len(pg_alerts) == 1

    def test_empty_messages(self):
        assert classify_messages([], JOE) == ([], [])
