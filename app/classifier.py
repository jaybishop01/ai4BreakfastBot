"""Message filtering, URL extraction, and queue classification."""

import re
from urllib.parse import urlparse

from .log import log

# Regex to extract URLs from Slack message format: <https://example.com> or <https://example.com|Display Text>
_URL_RE = re.compile(r"<(https?://[^>|]+)(?:\|[^>]*)?>")

# Regex to extract tagged user: <@U0550EH7H44> or <@U0550EH7H44|display_name>
_USER_TAG_RE = re.compile(r"<@(U[A-Z0-9]+)")

# Known company domains -> friendly names
KNOWN_COMPANIES = {
    "cbre.com": "CBRE",
    "cox.com": "Cox Automotive",
    "coxautoinc.com": "Cox Automotive",
    "delta.com": "Delta Air Lines",
    "equifax.com": "Equifax",
    "hilton.com": "Hilton",
    "chick-fil-a.com": "Chick-fil-A",
    "ncl.com": "Norwegian Cruise Line",
    "homedepot.com": "Home Depot",
    "capitalone.com": "Capital One",
    "fisglobal.com": "FIS",
    "hardrockdigital.com": "Hard Rock Digital",
    "abarcahealth.com": "Abarca Health",
    "conaservices.com": "CONA Services",
    "aflac.com": "Aflac",
    "bankunited.com": "BankUnited",
    "autonation.com": "AutoNation",
    "assurant.com": "Assurant",
    "synovus.com": "Synovus Financial",
    "adventhealth.com": "AdventHealth",
    "adt.com": "ADT",
    "ford.com": "Ford",
    "snowflake.com": "Snowflake",
    "databricks.com": "Databricks",
    "am-online.com": "AM Online",
    "nationaltoday.com": "National Today",
}


def extract_urls(text):
    """Extract and deduplicate external URLs from Slack message text.

    Handles <https://example.com> and <https://example.com|Display Text> formats.
    Skips Slack internal refs like <@U...> and <#C...>.
    """
    urls = []
    seen = set()
    for match in _URL_RE.finditer(text):
        url = match.group(1).strip()
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def parse_tagged_user(text):
    """Extract the first tagged user ID from text, e.g. <@U0550EH7H44> -> 'U0550EH7H44'."""
    match = _USER_TAG_RE.search(text)
    return match.group(1) if match else None


def extract_company(url):
    """Extract company name from URL domain. Uses known mapping, falls back to domain name."""
    try:
        parsed = urlparse(url)
        domain = parsed.hostname or ""
        # Strip www.
        if domain.startswith("www."):
            domain = domain[4:]

        # Check known companies
        for known_domain, company in KNOWN_COMPANIES.items():
            if domain == known_domain or domain.endswith("." + known_domain):
                return company

        # Fallback: title-case the main domain part
        parts = domain.rsplit(".", 1)
        if len(parts) >= 1:
            name = parts[0].replace("-", " ").replace("_", " ").title()
            return name
    except Exception:
        pass
    return "Unknown"


CURATOR_EMOJI = "studio_microphone"


def classify_messages(messages, joe_user_id):
    """Classify Slack messages into daily digest URLs and PG alert entries.

    Args:
        messages: list of Slack message dicts (from conversations.history)
        joe_user_id: only process messages from this user (for direct posts and PG alerts)

    Returns:
        (digest_urls, pg_alerts) where:
        - digest_urls: flat list of article URLs for the daily digest
        - pg_alerts: list of dicts with keys: message_ts, url, tagged_user_id, text
    """
    digest_urls = []
    pg_alerts = []
    seen_urls = set()

    for msg in messages:
        text = msg.get("text", "")
        ts = msg.get("ts", "")
        reactions = msg.get("reactions", [])
        from_joe = msg.get("user") == joe_user_id

        # Any message with :studio_microphone: reaction gets its URLs added to the digest
        if CURATOR_EMOJI in reactions:
            urls = extract_urls(text)
            for url in urls:
                if url not in seen_urls:
                    seen_urls.add(url)
                    digest_urls.append(url)
                    log.info("Curator-picked URL from message %s: %s", ts, url)
            continue

        # For Joe's own messages, apply existing digest/PG alert logic
        if not from_joe:
            continue

        urls = extract_urls(text)
        if not urls:
            continue

        if "pg alert" in text.lower():
            tagged_user = parse_tagged_user(text)
            if tagged_user and urls:
                pg_alerts.append({
                    "message_ts": ts,
                    "url": urls[0],
                    "tagged_user_id": tagged_user,
                    "text": text,
                })
                log.info("PG Alert found: user=%s url=%s", tagged_user, urls[0])
            else:
                log.warning("PG Alert message missing user tag or URL: %s", ts)
        else:
            for url in urls:
                if url not in seen_urls:
                    seen_urls.add(url)
                    digest_urls.append(url)
            log.info("Digest URLs from message %s: %s", ts, urls)

    log.info("Classification complete: %d digest URLs, %d PG alerts", len(digest_urls), len(pg_alerts))
    return digest_urls, pg_alerts
