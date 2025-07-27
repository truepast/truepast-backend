import os
import tempfile
import httpx
from fastapi import FastAPI, Request
from dotenv import load_dotenv
from pexels_api import API as PexelsAPI
from moviepy.editor import *
from PIL import Image
from io import BytesIO

load_dotenv()
app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
ELEVEN_KEY = os.getenv("ELEVENLABS_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

user_states = {}
library = []

@app.on_event("startup")
async def startup():
    async with httpx.AsyncClient() as client:
        await client.post(f"{TELEGRAM_API}/setWebhook", json={"url": WEBHOOK_URL})

@app.get("/")
def root():
    return {"status": "TruePast backend is live."}

@app.post("/")
async def telegram_webhook(req: Request):
    data = await req.json()
    message = data.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")
    state = user_states.get(chat_id)

    if not chat_id or not text:
        return {"ok": True}

    if text == "/start":
        user_states[chat_id] = None
        await send_message(chat_id, "Welcome to TruePast. Use /newvideo to start or /library to view saved topics.")

    elif text == "/library":
        if not library:
            await send_message(chat_id, "📚 Library is empty for now.")
        else:
            entries = "\n\n".join([f"• {item['title']}" for item in library])
            await send_message(chat_id, f"📚 Saved Topics:\n\n{entries}")

    elif text == "/newvideo":
        user_states[chat_id] = "awaiting_type"
        await send_message(chat_id, "Choose a video style:\n\n1️⃣ Classic\n2️⃣ Conspiracy\n3️⃣ Forgotten Heroes\n4️⃣ Lost Civilizations\n5️⃣ Suppressed Truth")

    elif state == "awaiting_type" and text in ["1", "2", "3", "4", "5"]:
        styles = {
            "1": "Classic TruePast format — bold, cinematic, and emotionally powerful.",
            "2": "Conspiracy edge — hook-driven with shadowy, intriguing tones.",
            "3": "Underdog heroes who changed history — inspiring tone.",
            "4": "Lost Civilizations — mystery, ancient wonders, and epic collapses.",
            "5": "Suppressed Truth — controversial, hidden, redacted history."
        }
        user_states[chat_id] = {"stage": "awaiting_prompt", "style": text}
        await send_message(chat_id, f"{styles[text]}\n\nNow send the video topic.")

    elif isinstance(state, dict) and state.get("stage") == "awaiting_prompt":
        style = state["style"]
        user_states[chat_id] = {"stage": "generating", "style": style, "prompt": text}
        await send_message(chat_id, f"📝 Writing your cinematic script for: {text}")
        script = await generate_script(text, style)
        if not script:
            await send_message(chat_id, "❌ Script failed. Try again.")
            user_states[chat_id] = None
            return {"ok": True}

        user_states[chat_id] = {
            "stage": "awaiting_script_approval",
            "script": script,
            "style": style,
            "prompt": text
        }

        await send_message(chat_id, f"🧠 Script:\n\n{script}\n\nReply ✅ to approve, ✏️ to edit, or ♻️ to regenerate.")

    elif isinstance(state, dict) and state.get("stage") == "awaiting_script_approval":
        if text == "✅":
            await send_message(chat_id, "🎙 Generating voice and visuals...")
            try:
                video_path = await create_video(state["script"], state["prompt"])
                await send_video(chat_id, video_path)
                library.append({"title": state['prompt'], "script": state['script']})
                user_states[chat_id] = {"stage": "awaiting_upload"}
                await send_message(chat_id, "⬆️ Upload video to all platforms? (yes/no)")
            except Exception as e:
                await send_message(chat_id, f"❌ Error during video creation:\n{str(e)}")
                user_states[chat_id] = None

        elif text == "✏️":
            user_states[chat_id] = {"stage": "awaiting_revised_script", **state}
            await send_message(chat_id, "✍️ Send your revised script.")

        elif text == "♻️":
            await send_message(chat_id, "🔁 Regenerating script...")
            script = await generate_script(state["prompt"], state["style"])
            if script:
                user_states[chat_id]["script"] = script
                await send_message(chat_id, f"🧠 New Script:\n\n{script}\n\nReply ✅ to approve, ✏️ to edit, or ♻️ to regenerate.")
            else:
                await send_message(chat_id, "❌ Regeneration failed.")

    elif isinstance(state, dict) and state.get("stage") == "awaiting_revised_script":
        user_states[chat_id]["script"] = text
        user_states[chat_id]["stage"] = "awaiting_script_approval"
        await send_message(chat_id, f"Updated Script:\n\n{text}\n\nReply ✅ to approve, ✏️ to edit, or ♻️ to regenerate.")

    elif isinstance(state, dict) and state.get("stage") == "awaiting_upload":
        if text.lower() == "yes":
            await send_message(chat_id, "🚀 (Simulated) Uploading to YouTube Shorts, TikTok, IG Reels, Facebook Reels...")
        else:
            await send_message(chat_id, "✅ Video ready for manual download.")
        user_states[chat_id] = None

    return {"ok": True}

# === Helper Functions ===

async def send_message(chat_id, text):
    async with httpx.AsyncClient() as client:
        await client.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": text})

async def send_video(chat_id, video_path):
    async with httpx.AsyncClient() as client:
        with open(video_path, "rb") as f:
            await client.post(f"{TELEGRAM_API}/sendVideo", data={"chat_id": chat_id}, files={"video": f})

async def generate_script(prompt, style_id):
    style_prompts = {
        "1": "bold, emotionally powerful history video in cinematic tone.",
        "2": "conspiracy-driven script with mystery and dramatic shadows.",
        "3": "script about a forgotten hero with an inspiring arc.",
        "4": "lost civilization mystery with epic visuals.",
        "5": "truth that’s been hidden or suppressed, controversial tone."
    }

    full_prompt = (
        f"You are a master scriptwriter. Write a short-form video script in the following tone: {style_prompts[style_id]}\n"
        f"Structure: Hook → Background → Tension → Turning Point → Resolution.\n"
        f"Topic: {prompt}"
    )

    headers = {"Authorization": f"Bearer {OPENAI_KEY}"}
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": full_prompt}]
    }

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            res = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            return res.json()["choices"][0]["message"]["content"]
        except Exception as e:
            return None

async def generate_voice(script):
    headers = {"xi-api-key": ELEVEN_KEY}
    data = {
        "text": script,
        "voice_settings": {"stability": 0.4, "similarity_boost": 0.75}
    }
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post("https://api.elevenlabs.io/v1/text-to-speech/EXAVITQu4vr4xnSDxMaL", headers=headers, json=data)
            audio_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
            with open(audio_path, "wb") as f:
                f.write(response.content)
            return audio_path
    except Exception as e:
        raise RuntimeError(f"Voice generation failed: {e}")

async def get_visual(prompt):
    api = PexelsAPI(PEXELS_API_KEY)
    api.search(prompt, page=1, results_per_page=1)
    photos = api.get_entries()
    if photos:
        async with httpx.AsyncClient() as client:
            response = await client.get(photos[0].original)
            image = Image.open(BytesIO(response.content))
            path = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg").name
            image.save(path)
            return path
    return None

async def create_video(script, prompt):
    audio = await generate_voice(script)
    image = await get_visual(prompt)

    audioclip = AudioFileClip(audio)
    imgclip = ImageClip(image).set_duration(audioclip.duration).resize(height=720).set_audio(audioclip)
    
    title_font = "BebasNeue-Regular"  # Requires installing this TTF font file
    title = TextClip(prompt, fontsize=70, font=title_font, color="white", size=(imgclip.w, 120)).set_position(("center", "top")).set_duration(audioclip.duration)
    watermark = TextClip("TruePast", fontsize=40, font=title_font, color="white").set_position(("right", "bottom")).set_duration(audioclip.duration)

    final = CompositeVideoClip([imgclip, title, watermark])
    path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name
    final.write_videofile(path, fps=24)
    return path
