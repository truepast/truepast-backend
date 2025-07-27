import os
import tempfile
from fastapi import FastAPI, Request
from dotenv import load_dotenv
import httpx
from pexels_api import API as PexelsAPI
from moviepy.editor import *
from PIL import Image
from io import BytesIO

load_dotenv()
app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_KEY = os.getenv("ELEVENLABS_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

user_states = {}
library = []

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
        await send_message(chat_id, "Welcome to TruePast. Use /newvideo to begin or /library to view saved topics.")

    elif text == "/library":
        if not library:
            await send_message(chat_id, "ð Library is empty for now.")
        else:
            entries = "\n\n".join([f"â¢ {item['title']}" for item in library])
            await send_message(chat_id, f"ð Saved Topics:\n\n{entries}")

    elif text == "/newvideo":
        user_states[chat_id] = "awaiting_style"
        await send_message(chat_id, "Choose video style:\n1ï¸â£ Classic\n2ï¸â£ Conspiracy\n3ï¸â£ Forgotten Heroes\n4ï¸â£ Lost Civilizations\n5ï¸â£ Suppressed Truth")

    elif state == "awaiting_style" and text in ["1", "2", "3", "4", "5"]:
        user_states[chat_id] = {"stage": "awaiting_prompt", "style": text}
        await send_message(chat_id, "Great. Now send the topic.")

    elif isinstance(state, dict) and state.get("stage") == "awaiting_prompt":
        style = state["style"]
        user_states[chat_id] = {"stage": "generating", "style": style, "prompt": text}
        await send_message(chat_id, f"ð Writing script for: {text}")
        script = await generate_script(text, style)
        if not script:
            await send_message(chat_id, "â Script failed. Try again.")
            user_states[chat_id] = None
        else:
            user_states[chat_id].update({"stage": "script_approval", "script": script})
            await send_message(chat_id, f"ð Script:\n\n{script}\n\nâ to approve, âï¸ to edit, â»ï¸ to regenerate")

    elif isinstance(state, dict) and state.get("stage") == "script_approval":
        if text == "â":
            await send_message(chat_id, "ð Generating voice & visuals...")
            try:
                video_path = await create_video(state["script"], state["prompt"])
                await send_video(chat_id, video_path)
                library.append({"title": state["prompt"], "script": state["script"]})
                user_states[chat_id] = {"stage": "upload_prompt"}
                await send_message(chat_id, "â¬ï¸ Upload video to YouTube, TikTok, IG & FB? (yes/no)")
            except Exception as e:
                await send_message(chat_id, f"â Error during video creation: {str(e)}")
                user_states[chat_id] = None
        elif text == "âï¸":
            user_states[chat_id]["stage"] = "awaiting_edit"
            await send_message(chat_id, "Send your revised script.")
        elif text == "â»ï¸":
            await send_message(chat_id, "â»ï¸ Regenerating script...")
            script = await generate_script(state["prompt"], state["style"])
            if script:
                user_states[chat_id]["script"] = script
                await send_message(chat_id, f"ð New Script:\n\n{script}\n\nâ to approve, âï¸ to edit, â»ï¸ to regenerate")
            else:
                await send_message(chat_id, "â Regeneration failed.")

    elif isinstance(state, dict) and state.get("stage") == "awaiting_edit":
        user_states[chat_id]["script"] = text
        user_states[chat_id]["stage"] = "script_approval"
        await send_message(chat_id, f"Updated Script:\n\n{text}\n\nâ to approve, âï¸ to edit, â»ï¸ to regenerate")

    elif isinstance(state, dict) and state.get("stage") == "upload_prompt":
        if text.lower() == "yes":
            await send_message(chat_id, "ð Simulated upload to all platforms complete.")
        else:
            await send_message(chat_id, "â Video ready for manual download.")
        user_states[chat_id] = None

    return {"ok": True}

async def send_message(chat_id, text):
    async with httpx.AsyncClient() as client:
        await client.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": text})

async def send_video(chat_id, video_path):
    async with httpx.AsyncClient() as client:
        with open(video_path, "rb") as f:
            await client.post(f"{TELEGRAM_API}/sendVideo", data={"chat_id": chat_id}, files={"video": f})

async def generate_script(prompt, style_id):
    styles = {
        "1": "bold, emotionally powerful history video in cinematic tone.",
        "2": "conspiracy-driven script with mystery and dramatic shadows.",
        "3": "script about a forgotten hero with an inspiring arc.",
        "4": "lost civilization mystery with epic visuals.",
        "5": "truth thatâs been hidden or suppressed, controversial tone."
    }
    full_prompt = f"Write a cinematic script with structure: Hook â Context â Tension â Resolution.
Tone: {styles[style_id]}
Topic: {prompt}"
    headers = {"Authorization": f"Bearer {OPENAI_KEY}"}
    payload = {"model": "gpt-3.5-turbo", "messages": [{"role": "user", "content": full_prompt}]}
    async with httpx.AsyncClient() as client:
        res = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        return res.json()["choices"][0]["message"]["content"]

async def generate_voice(script):
    headers = {"xi-api-key": ELEVENLABS_KEY}
    data = {"text": script, "voice_settings": {"stability": 0.4, "similarity_boost": 0.75}}
    async with httpx.AsyncClient(timeout=45) as client:
        res = await client.post("https://api.elevenlabs.io/v1/text-to-speech/EXAVITQu4vr4xnSDxMaL", headers=headers, json=data)
        audio_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
        with open(audio_path, "wb") as f:
            f.write(res.content)
        return audio_path

async def get_visual(prompt):
    api = PexelsAPI(PEXELS_API_KEY)
    api.search(prompt, page=1, results_per_page=1)
    photos = api.get_entries()
    if photos:
        async with httpx.AsyncClient() as client:
            img_data = await client.get(photos[0].original)
            img = Image.open(BytesIO(img_data.content))
            path = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg").name
            img.save(path)
            return path
    return None

async def create_video(script, prompt):
    audio_path = await generate_voice(script)
    image_path = await get_visual(prompt)

    audioclip = AudioFileClip(audio_path)
    imgclip = ImageClip(image_path).set_duration(audioclip.duration).resize(height=720).set_audio(audioclip)

    title = TextClip(prompt, fontsize=70, font="BebasNeue-Regular", color="white", size=(imgclip.w, 120)).set_position(("center", "top")).set_duration(audioclip.duration)
    watermark = TextClip("TruePast", fontsize=40, font="BebasNeue-Regular", color="white").set_position(("right", "bottom")).set_duration(audioclip.duration)

    final = CompositeVideoClip([imgclip, title, watermark])
    output_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name
    final.write_videofile(output_path, fps=24)
    return output_path
