from fastapi import FastAPI, Request
import os
import httpx

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

@app.get("/")
def home():
    return {"message": "TruePast backend is live."}

@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()

    chat_id = data["message"]["chat"]["id"]
    text = data["message"].get("text", "")

    if text == "/start":
        reply = "Welcome to TruePast!"
    elif text == "/newvideo":
        reply = "Generating your video... (placeholder)"
    else:
        reply = f"You said: {text}"

    async with httpx.AsyncClient() as client:
        await client.post(
            TELEGRAM_API_URL,
            json={"chat_id": chat_id, "text": reply}
        )

    return {"ok": True}
