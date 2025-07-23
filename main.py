from fastapi import FastAPI, Request
import os
import requests

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

@app.post("/webhook")
async def telegram_webhook(req: Request):
    data = await req.json()
    message = data.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    if text == "/start":
        send_message(chat_id, "Welcome to TruePast.")
    elif text == "/newvideo":
        send_message(chat_id, "Generating your video... (placeholder)")
    return {"ok": True}

@app.get("/")
def root():
    return {"message": "Bot is running"}

@app.get("/set-webhook")
def set_webhook():
    webhook_url = os.getenv("WEBHOOK_URL")
    response = requests.get(f"{BASE_URL}/setWebhook?url={webhook_url}/webhook")
    return response.json()

def send_message(chat_id, text):
    requests.post(f"{BASE_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": text
    })
