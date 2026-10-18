# get_chat_id.py - run once to find your Telegram chat ID
import os
import requests
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("TELEGRAM_BOT_TOKEN")
if not token:
    raise SystemExit("TELEGRAM_BOT_TOKEN is missing from .env")

base = f"https://api.telegram.org/bot{token}"

# 1. Which bot does this token belong to?
me = requests.get(f"{base}/getMe", timeout=30).json()
if not me.get("ok"):
    raise SystemExit(f"Token problem: {me.get('description')}")
print(f"This token belongs to: @{me['result']['username']}")

# 2. Are there any messages waiting?
data = requests.get(f"{base}/getUpdates", timeout=30).json()
if not data.get("ok"):
    raise SystemExit(f"Telegram error: {data.get('description')}")

results = data.get("result", [])
print(f"Messages waiting: {len(results)}")
for update in results:
    msg = update.get("message")
    if msg:
        print("Chat ID:", msg["chat"]["id"], "| from:", msg["from"].get("username"))