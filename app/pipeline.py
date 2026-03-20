"""Core pipeline logic for Daily Digest and PG Alert podcast generation."""

import os
from datetime import date

from .config import AUDIO_DIR, PRIMER_PATH, CHANNEL_ID
from .log import log
from . import slack_api
from . import slack_reader
from . import nlm
from . import audio as audio_mod
from . import gong
from . import archiver
from .classifier import extract_company
from .state import (
    record_notebook,
    update_feedback,
    get_recent_notebooks,
    save_state,
)

# --- Slack message templates ---

DIGEST_COMMENT_TEMPLATE = """:studio_microphone: *AI for Breakfast Podcast — {date}*

Today's digest covers {n} article{s}:
{bullets}

_Your feedback directly affects future episodes. Drop a :+1: or :-1:, or reply in the thread with details._

_DISCLAIMER: Use judgment before repeating statements heard in AI for Breakfast podcasts. AI hallucinates. Podcasts may include sensitive internal and/or customer information._ *_Do not share outside of dbt Labs._*"""

PG_ALERT_COMMENT_TEMPLATE = """:studio_microphone: *PG Alert Podcast — {company}*
_Your feedback directly affects future episodes. Drop a :+1: or :-1:, or reply with details._

_DISCLAIMER: Use judgment before repeating statements heard in AI for Breakfast podcasts. AI hallucinates. Podcasts may include sensitive internal and/or customer information._ *_Do not share outside of dbt Labs._*"""

# --- Focus prompt templates ---

DIGEST_FOCUS_TEMPLATE = (
    "When discussing these articles, connect the industry trends to how dbt Labs' "
    "products and roadmap address these challenges. Speak as if briefing a go-to-market "
    "team at dbt Labs on why these trends matter for their customer conversations. "
    "Keep the conversation balanced -- don't over-index on product features, especially "
    "toward the end. Also weave in dbt's culture, community history, roadmap vision, "
    "and the analytics engineering movement -- not just feature callouts. Avoid overstating "
    "product capabilities; be accurate and measured. The first three-quarters should feel "
    "like an informed industry conversation; any dbt tie-ins should feel natural and not "
    "like a sales pitch."
    "{feedback_section}"
)

PG_ALERT_FOCUS_TEMPLATE = (
    "This article is about {company}. A dbt Labs rep named {rep_name} is actively in "
    "conversations with this customer. {gong_section}"
    "Connect the article's initiative to how dbt Labs can help, and suggest how this "
    "could inform the next call. Focus on how the article's themes might create "
    "opportunities for dbt Labs with this company."
)


def collect_feedback(state, config):
    """Read thread replies on recent notebooks and update accumulated_feedback."""
    channel = config.get("slack_channel_id", CHANNEL_ID)
    recent = get_recent_notebooks(state, days=3)

    new_feedback_parts = []
    for nb in recent:
        slack_ts = nb.get("slack_ts")
        if not slack_ts or slack_ts == "ok" or slack_ts == "unknown":
            continue
        try:
            replies = slack_reader.get_thread_replies(channel, slack_ts)
            for reply in replies:
                # Skip bot messages
                if reply.get("bot_id"):
                    continue
                text = reply.get("text", "").strip()
                if text:
                    new_feedback_parts.append(text)
        except Exception as e:
            log.warning("Failed to read thread %s: %s", slack_ts, e)

    if new_feedback_parts:
        combined = " | ".join(new_feedback_parts)
        update_feedback(state, f"Listener feedback: {combined}")
        log.info("Collected %d feedback replies", len(new_feedback_parts))
    else:
        log.info("No new feedback found")


def run_digest(urls, state, config):
    """Run the Daily Digest pipeline: create notebook, add sources, generate audio, upload."""
    token = config["slack_bot_token"]
    channel = config.get("slack_channel_id", CHANNEL_ID)
    today = date.today().strftime("%B %-d, %Y")

    log.info("=== Starting Daily Digest for %s ===", today)
    log.info("Articles: %d URLs", len(urls))

    # 1. Create notebook
    notebook_id = nlm.create_notebook(f"AI for Breakfast -- {today}")

    # 2. Add URL sources
    nlm.add_url_sources(notebook_id, urls)

    # 2a. Retry any paywalled/failed sources via archive fallback
    failed_urls = set(archiver.resolve_failed_sources(notebook_id, urls))
    resolved_urls = [u for u in urls if u not in failed_urls]

    # 3. Add dbt primer as file source
    nlm.add_file_source(notebook_id, PRIMER_PATH, "dbt Labs Context")

    # 4. Build focus prompt with feedback
    feedback = state.get("accumulated_feedback", "")
    feedback_section = ""
    if feedback:
        feedback_section = f"\n\nPrevious listener feedback to incorporate: {feedback}"
    focus = DIGEST_FOCUS_TEMPLATE.format(feedback_section=feedback_section)

    # 5. Generate audio
    nlm.create_audio(notebook_id, fmt="deep_dive", length="default", focus=focus)

    # 6. Poll until complete (deep_dive can take >10 min)
    nlm.poll_status(notebook_id, max_secs=1200)

    # 7. Download
    m4a_path = os.path.join(AUDIO_DIR, f"ai4breakfast-{date.today().isoformat()}.m4a")
    nlm.download_audio(notebook_id, m4a_path)

    # 8. Convert to MP3
    mp3_path = m4a_path.replace(".m4a", ".mp3")
    if not audio_mod.convert_to_mp3(m4a_path, mp3_path):
        # Fallback: try uploading m4a directly
        log.warning("MP3 conversion failed, uploading m4a")
        mp3_path = m4a_path

    # 9. Build Slack comment (only list articles that actually loaded)
    display_urls = resolved_urls if resolved_urls else urls
    bullets = "\n".join(f"* {url}" for url in display_urls)
    comment = DIGEST_COMMENT_TEMPLATE.format(
        date=today,
        n=len(display_urls),
        s="" if len(display_urls) == 1 else "s",
        bullets=bullets,
    )

    # 10. Upload to Slack
    upload_path = mp3_path
    title = f"AI for Breakfast -- {today}"
    slack_ts = slack_api.upload_file(token, channel, upload_path, title, comment)

    if not slack_ts:
        # Fallback: post notebook link
        log.warning("File upload failed, posting notebook link")
        nb_url = f"https://notebooklm.google.com/notebook/{notebook_id}"
        slack_ts = slack_api.post_message(
            token, channel,
            f"{comment}\n\nListen here: {nb_url}"
        )

    # 11. Record in state
    record_notebook(state, notebook_id, "digest", slack_ts or "unknown")

    # 12. Cleanup individual files
    for f in [m4a_path, mp3_path]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass

    log.info("=== Daily Digest complete ===")


def run_pg_alert(alert, state, config):
    """Run a PG Alert pipeline for a single alert."""
    token = config["slack_bot_token"]
    channel = config.get("slack_channel_id", CHANNEL_ID)
    today = date.today().strftime("%B %-d, %Y")

    url = alert["url"]
    tagged_user_id = alert["tagged_user_id"]
    message_ts = alert["message_ts"]

    log.info("=== Starting PG Alert: %s ===", url)

    # 1. Look up tagged user name (via Claude CLI + MCP Slack)
    rep_name = slack_reader.get_user_name(tagged_user_id)
    log.info("Rep: %s (%s)", rep_name, tagged_user_id)

    # 2. Extract company from URL
    company = extract_company(url)
    log.info("Company: %s", company)

    # 3. Gong/Glean lookup via Claude
    gong_context = gong.lookup_gong_context(rep_name, company)

    # 4. Create notebook
    notebook_id = nlm.create_notebook(f"PG Alert -- {company} -- {today}")

    # 5. Add article URL as source
    try:
        nlm.add_url_sources(notebook_id, [url])
        archiver.resolve_failed_sources(notebook_id, [url])
    except nlm.NLMError:
        log.warning("Failed to add article URL, continuing with primer only")

    # 6. Add dbt primer
    nlm.add_file_source(notebook_id, PRIMER_PATH, "dbt Labs Context")

    # 7. Add Gong context as text source if available
    if gong_context:
        try:
            nlm.add_text_source(
                notebook_id,
                gong_context,
                f"Gong Context -- {company}",
            )
        except nlm.NLMError:
            log.warning("Failed to add Gong context source")

    # 8. Build focus prompt
    gong_section = ""
    if gong_context:
        gong_section = (
            f"Recent conversation themes from Gong: {gong_context}. "
            "Connect the article's initiative to the themes from their existing "
            "conversations, and suggest how this could inform the next call. "
        )
    else:
        gong_section = (
            "No recent conversation history was available. "
        )

    focus = PG_ALERT_FOCUS_TEMPLATE.format(
        company=company,
        rep_name=rep_name,
        gong_section=gong_section,
    )

    # 9. Generate audio (brief/short)
    nlm.create_audio(notebook_id, fmt="brief", length="short", focus=focus)

    # 10. Poll until complete
    nlm.poll_status(notebook_id)

    # 11. Download
    safe_company = company.lower().replace(" ", "-").replace("&", "and")
    m4a_path = os.path.join(AUDIO_DIR, f"pg-alert-{safe_company}-{date.today().isoformat()}.m4a")
    nlm.download_audio(notebook_id, m4a_path)

    # 12. Convert to MP3
    mp3_path = m4a_path.replace(".m4a", ".mp3")
    if not audio_mod.convert_to_mp3(m4a_path, mp3_path):
        log.warning("MP3 conversion failed, uploading m4a")
        mp3_path = m4a_path

    # 13. Build Slack comment
    comment = PG_ALERT_COMMENT_TEMPLATE.format(company=company)

    # 14. Upload as thread reply
    title = f"PG Alert -- {company} -- {today}"
    upload_path = mp3_path
    slack_ts = slack_api.upload_file(token, channel, upload_path, title, comment, thread_ts=message_ts)

    if not slack_ts:
        log.warning("File upload failed, posting notebook link as thread reply")
        nb_url = f"https://notebooklm.google.com/notebook/{notebook_id}"
        slack_ts = slack_api.post_message(
            token, channel,
            f"{comment}\n\nListen here: {nb_url}",
            thread_ts=message_ts,
        )

    # 15. Record in state
    record_notebook(state, notebook_id, "pg_alert", message_ts, company=company)

    # 16. Cleanup
    for f in [m4a_path, mp3_path]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass

    log.info("=== PG Alert complete: %s ===", company)
