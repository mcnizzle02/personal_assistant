# outlook.py - signs in to Microsoft and reads mail through Microsoft Graph
import os
from datetime import datetime
from pathlib import Path

import msal
import requests
from dotenv import load_dotenv

load_dotenv()
CLIENT_ID = os.getenv("MS_CLIENT_ID")
AUTHORITY = "https://login.microsoftonline.com/consumers"   # personal accounts only
SCOPES = ["Mail.Read", "Mail.Send"]                                      # read-only, least privilege
CACHE_FILE = Path(__file__).parent / "token_cache.json"     # pathlib works on Mac and Windows
GRAPH = "https://graph.microsoft.com/v1.0"


def _load_cache():
    cache = msal.SerializableTokenCache()
    if CACHE_FILE.exists():
        cache.deserialize(CACHE_FILE.read_text())
    return cache


def _save_cache(cache):
    if cache.has_state_changed:
        CACHE_FILE.write_text(cache.serialize())


def get_access_token():
    """Return a valid access token, signing in only if needed."""
    if not CLIENT_ID:
        raise RuntimeError("MS_CLIENT_ID is missing from .env")

    cache = _load_cache()
    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)

    # 1. Try the saved token first, so no sign-in is needed
    result = None
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])

    # 2. Nothing saved (or it expired): sign in with a device code
    if not result:
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(f"Could not start sign-in: {flow.get('error_description')}")
        print(flow["message"])                        # tells you where to go and what code to enter
        result = app.acquire_token_by_device_flow(flow)   # waits until you finish signing in

    _save_cache(cache)
    if "access_token" not in result:
        raise RuntimeError(f"Sign-in failed: {result.get('error_description')}")
    return result["access_token"]


def _to_local_time(utc_string):
    """Graph returns times in UTC like '2026-10-17T15:04:00Z'. Convert to your time zone."""
    dt = datetime.fromisoformat(utc_string.replace("Z", "+00:00"))
    return dt.astimezone().strftime("%a %b %d, %I:%M %p")


def get_recent_emails(count=10, unread_only=False):
    """Fetch recent inbox messages: sender, subject, time, and a short preview."""
    token = get_access_token()
    params = {
        "$top": count,
        "$select": "subject,from,receivedDateTime,isRead,bodyPreview",
        "$orderby": "receivedDateTime desc",
    }
    if unread_only:
        # Graph requires the sort field to also appear in the filter, hence the date condition
        params["$filter"] = "receivedDateTime ge 2000-01-01T00:00:00Z and isRead eq false"

    resp = requests.get(
        f"{GRAPH}/me/mailFolders/inbox/messages",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=30,
    )
    resp.raise_for_status()   # turns an HTTP error (401, 403, etc.) into a Python error

    emails = []
    for m in resp.json()["value"]:
        sender = (m.get("from") or {}).get("emailAddress", {})
        emails.append({
            "from": f"{sender.get('name', 'Unknown')} <{sender.get('address', '?')}>",
            "subject": m.get("subject") or "(no subject)",
            "received": _to_local_time(m["receivedDateTime"]),
            "unread": not m.get("isRead", True),
            "preview": m.get("bodyPreview", ""),
        })
    return emails

def send_email(to, subject, body):
    """Send a plain-text email from Lee's account. Only the app calls this, never Claude."""
    token = get_access_token()
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to}}],
        },
        "saveToSentItems": True,
    }
    resp = requests.post(
        f"{GRAPH}/me/sendMail",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()