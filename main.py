import os
import tempfile
from fastapi import FastAPI, Request
from dotenv import load_dotenv
import httpx
import requests
from pexels_api import API as PexelsAPI
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, TextClip
from PIL import Image
from io import BytesIO

load_dotenv()
app = FastAPI()

# Environment variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_KEY = os.getenv("ELEVENLABS_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

user_states = {}

@app.on_event("startup")
async def set_webhook():
    async with httpx.AsyncClient() as client:
        await client.post(f"{TELEGRAM_API}/setWebhook", json={"url": WEBHOOK_URL})

@app.get("/")
def root():
    return {"status": "TruePast backend running."}

@app.post("/")
async def handle_webhook(req: Request):
    data = await req.json()
    message = data.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    if not chat_id or not text:
        return {"ok": True}

    state = user_states.get(chat_id)

    if text == "/start":
        user_states[chat_id] = None
        await send_message(chat_id, "Welcome to TruePast. Use /newvideo to begin.")

    elif text == "/newvideo":
        if user_states.get(chat_id) == "processing":
            await send_message(chat_id, "Still working on your last request. Please wait.")
        else:
            user_states[chat_id] = "awaiting_prompt"
            await send_message(chat_id, "What should this video be about?")

    elif state == "awaiting_prompt":
        user_states[chat_id] = "processing"
        await send_message(chat_id, f"Generating script for: {text}")
        script = await generate_script(text)
        user_states[chat_id] = {
            "stage": "awaiting_approval",
            "script": script,
            "prompt": text
        }
        await send_message(chat_id, f"Here’s your script:\n\n{script}\n\nReply ✅ to approve or ✏️ to edit.")

    elif isinstance(state, dict) and state.get("stage") == "awaiting_approval":
        if "✅" in text:
            await send_message(chat_id, "Script approved. Generating voice and visuals...")
            video_path = await create_video(state["script"], state["prompt"])
            await send_video(chat_id, video_path)
            user_states[chat_id] = None
        elif "✏️" in text:
            await send_message(chat_id, "Send your revised script.")
            user_states[chat_id] = "awaiting_revised_script"
        else:
            await send_message(chat_id, "Reply with ✅ to approve or ✏️ to edit.")

    elif state == "awaiting_revised_script":
        user_states[chat_id] = {
            "stage": "awaiting_approval",
            "script": text,
            "prompt": "custom revision"
        }
        await send_message(chat_id, f"Updated script received:\n\n{text}\n\nReply ✅ to approve or ✏️ to edit.")

    else:
        await send_message(chat_id, "Use /newvideo to start.")
        
    return {"ok": True}

# --- Helper Functions ---

async def send_message(chat_id, text):
    async with httpx.AsyncClient() as client:
        await client.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": text})

async def send_video(chat_id, video_path):
    with open(video_path, "rb") as f:
        files = {"video": f}
        requests.post(f"{TELEGRAM_API}/sendVideo", data={"chat_id": chat_id}, files=files)

async def generate_script(prompt):
    headers = {
        "Authorization": f"Bearer {OPENAI_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-4",
        "messages": [
            {"role": "system", "content": "You're a professional YouTube scriptwriter for a bold, emotionally powerful history channel. Every video should follow this arc: hook → context → tension → emotional payoff → resolution. Keep it cinematic, human, and memorable."},
            {"role": "user", "content": f"Write a 2-minute YouTube script about: {prompt}"}
        ]
    }
    async with httpx.AsyncClient() as client:
        response = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        return response.json()["choices"][0]["message"]["content"]

async def generate_voice(script):
    url = "https://api.elevenlabs.io/v1/text-to-speech/EXAVITQu4vr4xnSDxMaL"
    headers = {
        "xi-api-key": ELEVENLABS_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "text": script,
        "voice_settings": {"stability": 0.4, "similarity_boost": 0.75}
    }
    response = requests.post(url, headers=headers, json=data)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
        f.write(response.content)
        return f.name

async def get_visual(prompt):
    api = PexelsAPI(PEXELS_API_KEY)
    api.search(prompt, page=1, results_per_page=1)
    photos = api.get_entries()
    if photos:
        image_url = photos[0].original
        response = requests.get(image_url)
        image = Image.open(BytesIO(response.content))
        temp_path = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg").name
        image.save(temp_path)
        return temp_path
    return None

async def create_video(script, prompt):
    audio_path = await generate_voice(script)
    image_path = await get_visual(prompt)

    audioclip = AudioFileClip(audio_path)
    duration = audioclip.duration
    imgclip = ImageClip(image_path).set_duration(duration).resize(height=720).set_fps(24)
    imgclip = imgclip.set_audio(audioclip)

    title = TextClip(prompt, fontsize=40, color='white', font="Arial-Bold", size=(imgclip.w, 100))
    title = title.set_position(("center", "top")).set_duration(duration)
    final = CompositeVideoClip([imgclip, title])

    final_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name
    final.write_videofile(final_path, fps=24)
    return final_path
