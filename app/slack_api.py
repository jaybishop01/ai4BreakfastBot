"""Slack Web API client using urllib (no external dependencies)."""

import json
import os
import time
import urllib.error
import urllib.request

from .config import SLACK_API_BASE
from .log import log


def _slack_get(token, method, params=None):
    """Make a GET request to the Slack API."""
    url = f"{SLACK_API_BASE}/{method}"
    if params:
        qs = urllib.parse.urlencode(params)
        url = f"{url}?{qs}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    return _do_request(req)


def _slack_post_json(token, method, payload):
    """Make a POST request to the Slack API with JSON body."""
    url = f"{SLACK_API_BASE}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    return _do_request(req)


def _do_request(req, retries=1):
    """Execute a urllib request with retry on 429/5xx."""
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read())
                if not body.get("ok"):
                    log.warning("Slack API error: %s", body.get("error", "unknown"))
                return body
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < retries:
                retry_after = int(e.headers.get("Retry-After", "2"))
                log.warning("Slack %d, retrying in %ds...", e.code, retry_after)
                time.sleep(retry_after)
                continue
            log.error("Slack HTTP error %d: %s", e.code, e.read().decode()[:200])
            raise
        except urllib.error.URLError as e:
            log.error("Slack URL error: %s", e.reason)
            raise


# Need to import urlencode
import urllib.parse


def get_history(token, channel, oldest):
    """Fetch channel messages since oldest timestamp. Handles pagination."""
    messages = []
    cursor = None
    while True:
        params = {"channel": channel, "oldest": oldest, "limit": "100"}
        if cursor:
            params["cursor"] = cursor
        data = _slack_get(token, "conversations.history", params)
        if not data or not data.get("ok"):
            break
        messages.extend(data.get("messages", []))
        meta = data.get("response_metadata", {})
        cursor = meta.get("next_cursor")
        if not cursor:
            break
    log.info("Fetched %d messages from channel %s since %s", len(messages), channel, oldest)
    return messages


def get_replies(token, channel, thread_ts):
    """Fetch thread replies for a given parent message."""
    params = {"channel": channel, "ts": thread_ts, "limit": "200"}
    data = _slack_get(token, "conversations.replies", params)
    if not data or not data.get("ok"):
        return []
    # First message is the parent; return only replies
    msgs = data.get("messages", [])
    return msgs[1:] if len(msgs) > 1 else []


def get_user_name(token, user_id):
    """Look up a Slack user's real name."""
    params = {"user": user_id}
    data = _slack_get(token, "users.info", params)
    if data and data.get("ok"):
        user = data.get("user", {})
        return user.get("real_name") or user.get("name") or user_id
    return user_id


def upload_file(token, channel, filepath, title, comment, thread_ts=None):
    """Upload a file to Slack using the 3-step external upload flow.

    Returns the message_ts of the posted message, or None on failure.
    """
    filename = os.path.basename(filepath)
    filesize = os.path.getsize(filepath)

    # Step 1: Get upload URL
    log.info("Requesting upload URL for %s (%d bytes)", filename, filesize)
    params = {"filename": filename, "length": str(filesize)}
    data = _slack_get(token, "files.getUploadURLExternal", params)
    if not data or not data.get("ok"):
        log.error("Failed to get upload URL: %s", data.get("error") if data else "no response")
        return None

    upload_url = data["upload_url"]
    file_id = data["file_id"]

    # Step 2: Upload file bytes
    log.info("Uploading file to Slack (file_id=%s)", file_id)
    with open(filepath, "rb") as f:
        file_data = f.read()

    upload_req = urllib.request.Request(
        upload_url,
        data=file_data,
        method="POST",
        headers={"Content-Type": "audio/mpeg"},
    )
    try:
        with urllib.request.urlopen(upload_req, timeout=120) as resp:
            resp.read()
            log.info("File uploaded successfully (status=%d)", resp.status)
    except urllib.error.HTTPError as e:
        log.error("File upload failed: HTTP %d", e.code)
        return None

    # Step 3: Complete the upload
    log.info("Completing upload to channel %s", channel)
    payload = {
        "files": [{"id": file_id, "title": title}],
        "channel_id": channel,
        "initial_comment": comment,
    }
    if thread_ts:
        payload["thread_ts"] = thread_ts

    data = _slack_post_json(token, "files.completeUploadExternal", payload)
    if data and data.get("ok"):
        log.info("File posted to Slack successfully")
        # Try to extract message_ts from response
        files = data.get("files", [])
        if files:
            shares = files[0].get("shares", {})
            for ch_type in ("public", "private"):
                ch_shares = shares.get(ch_type, {}).get(channel, [])
                if ch_shares:
                    return ch_shares[0].get("ts")
        return "ok"
    else:
        log.error("Complete upload failed: %s", data.get("error") if data else "no response")
        return None


def post_message(token, channel, text, thread_ts=None):
    """Post a text message to a channel (fallback when upload fails)."""
    payload = {"channel": channel, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    data = _slack_post_json(token, "chat.postMessage", payload)
    if data and data.get("ok"):
        return data.get("ts")
    log.error("post_message failed: %s", data.get("error") if data else "no response")
    return None
