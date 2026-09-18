# Helpers for Telegram Bot API calls
import json

async def send_message(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    headers = {"Content-Type": "application/json"}
    body = json.dumps({"chat_id": chat_id, "text": text})
    # Fetch call inside worker context
    pass
