# telegram_bot.py - chat with your assistant from Telegram (long polling)
import os
import time

import requests
from dotenv import load_dotenv

from assistant import get_reply
from tools import setup_database, take_pending_draft
from outlook import send_email

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_CHAT_ID = os.getenv("TELEGRAM_ALLOWED_CHAT_ID")
API = f"https://api.telegram.org/bot{TOKEN}"
MAX_HISTORY = 30   # how many past messages to keep sending to Claude


def telegram(method, **params):
    """Call the Telegram Bot API without ever leaking the token into errors or logs."""
    try:
        resp = requests.post(f"{API}/{method}", json=params, timeout=60)
    except requests.RequestException as e:
        # The original error message contains the full URL, token included, so hide it
        raise RuntimeError(f"Network error calling Telegram {method}: {type(e).__name__}") from None
    if not resp.ok:
        raise RuntimeError(f"Telegram {method} failed: {resp.status_code} {resp.text[:200]}")
    return resp.json()["result"]


def send_text(chat_id, text):
    """Send a reply, split into pieces because Telegram allows 4096 characters per message."""
    text = text or "(no reply)"
    for start in range(0, len(text), 4000):
        telegram("sendMessage", chat_id=chat_id, text=text[start:start + 4000])


def trim_history(messages):
    """Keep the conversation from growing forever, without splitting a tool call from its result."""
    if len(messages) <= MAX_HISTORY:
        return messages
    cut = len(messages) - MAX_HISTORY
    # Move forward to a plain text message from Lee, so the trimmed history starts cleanly
    while cut < len(messages) and not (
        messages[cut]["role"] == "user" and isinstance(messages[cut]["content"], str)
    ):
        cut += 1
    return messages[cut:]


def main():
    if not TOKEN or not ALLOWED_CHAT_ID:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_CHAT_ID in .env")

    setup_database()
    messages = []
    waiting_draft = None   # a draft waiting for Lee's YES
    app_note = None
    offset = None          # tells Telegram which messages we've already handled
    print("Telegram bot running. Press Ctrl+C to stop.")

    while True:
        try:
            updates = telegram("getUpdates", offset=offset, timeout=50)
        except Exception as e:
            print(f"[poll error] {e}")
            time.sleep(5)
            continue

        for update in updates:
            offset = update["update_id"] + 1
            msg = update.get("message")
            if not msg or "text" not in msg:
                continue

            chat_id = str(msg["chat"]["id"])
            text = msg["text"].strip()

            # ALLOWLIST: ignore everyone except Lee, and don't reply at all
            if chat_id != ALLOWED_CHAT_ID:
                print(f"[blocked] message from unknown chat {chat_id}")
                continue

            print(f"\nLee (Telegram): {text}")
            try:
                # HARD GUARDRAIL: a waiting draft consumes this message as the answer
                if waiting_draft:
                    draft, waiting_draft = waiting_draft, None
                    if text.upper() == "YES":
                        try:
                            send_email(draft["to"], draft["subject"], draft["body"])
                            send_text(chat_id, "Sent.")
                            app_note = f"Lee confirmed, and the email to {draft['to']} was sent."
                        except Exception as e:
                            send_text(chat_id, "Sending failed. Check the terminal.")
                            print(f"[send error] {e}")
                            app_note = f"Sending failed: {e}"
                    else:
                        send_text(chat_id, "Cancelled. Nothing was sent.")
                        app_note = "Lee cancelled the draft. It was NOT sent."
                    continue

                if text == "/start":
                    send_text(chat_id, "Hi Lee, I'm ready. Send /reset to clear our conversation.")
                    continue
                    
                if text == "/reset":
                    messages.clear()
                    app_note = None
                    waiting_draft = None
                    send_text(chat_id, "Conversation cleared.")
                    continue

                content = text
                if app_note:
                    content = f"[App note: {app_note}]\n{text}"
                    app_note = None
                messages.append({"role": "user", "content": content})
                messages[:] = trim_history(messages)

                reply = get_reply(messages)
                print(f"Assistant: {reply}")
                send_text(chat_id, reply)

                draft = take_pending_draft()
                if draft:
                    waiting_draft = draft
                    send_text(
                        chat_id,
                        "EMAIL READY TO SEND\n"
                        f"To: {draft['to']}\n"
                        f"Subject: {draft['subject']}\n\n"
                        f"{draft['body']}\n\n"
                        "Reply YES to send. Anything else cancels.",
                    )

            except Exception as e:
                print(f"[error] {e}")
                messages.clear()   # start fresh rather than keep a half-finished conversation
                send_text(chat_id, "Something went wrong, so I reset our conversation. Check the terminal for details.")


if __name__ == "__main__":
    main()