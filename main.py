import os
import openai
import requests
from fastapi import FastAPI, Request
from pydub import AudioSegment
from PIL import Image
from moviepy.editor import *
from dotenv import load_dotenv
import tempfile
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = "j9jfwdrw7BRfcR43Qohk"

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
app = FastAPI()

user_state = {}

script_styles = {
    "1": "Write a cinematic and emotionally powerful history short. Hook the viewer immediately, build suspense, and leave them with a memorable final message. Tone should be serious and bold.",
    "2": "Write a fast-paced, curiosity-driven historical short that opens with a bold fact or claim, then explains it quickly. Ideal for social media virality.",
    "3": "Write a first-person historical short where the narrator speaks as if they were living through the event. Use personal emotion and vivid storytelling.",
    "4": "Write a timeline-based historical short. Walk the viewer through the key moments in chronological order. Hook with the outcome, then go back to the beginning.",
    "5": "Write a myth-busting or controversial historical short that challenges what most people believe. Use bold claims and strong evidence."
}

def generate_script(prompt, style_number):
    openai.api_key = OPENAI_API_KEY
    system_prompt = script_styles.get(style_number, script_styles["1"])
    user_prompt = f"{system_prompt}\n\nTopic: {prompt}"
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=1,
        max_tokens=500
    )
    return response['choices'][0]['message']['content'].strip()

def generate_voice(script_text):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "text": script_text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.4,
            "similarity_boost": 1
        }
    }
    response = requests.post(url, headers=headers, json=data, timeout=45)
    if response.status_code == 200:
        temp_audio = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        temp_audio.write(response.content)
        temp_audio.close()
        return temp_audio.name
    else:
        raise Exception(f"Voice generation failed: {response.text}")

def generate_video_with_images(script_text):
    image_urls = [
        "https://images.pexels.com/photos/3765133/pexels-photo-3765133.jpeg",
        "https://images.pexels.com/photos/1054666/pexels-photo-1054666.jpeg",
        "https://images.pexels.com/photos/929778/pexels-photo-929778.jpeg"
    ]
    images = []
    for url in image_urls:
        img_response = requests.get(url)
        if img_response.status_code == 200:
            img_temp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            img_temp.write(img_response.content)
            img_temp.close()
            img = Image.open(img_temp.name)
            img = img.resize((1080, 1920), resample=Image.Resampling.LANCZOS)
            images.append(img)

    clips = []
    for img in images:
        img_temp_path = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg").name
        img.save(img_temp_path)
        clip = ImageClip(img_temp_path).set_duration(3)
        clips.append(clip)

    final_video = concatenate_videoclips(clips, method="compose")
    audio_path = generate_voice(script_text)
    audio = AudioFileClip(audio_path)
    final_video = final_video.set_audio(audio)

    output_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name
    final_video.write_videofile(output_path, codec="libx264", audio_codec="aac")
    return output_path

@bot.message_handler(commands=['start', 'newvideo'])
def start_message(message):
    user_id = message.chat.id
    user_state[user_id] = {"step": "choose_style"}
    markup = InlineKeyboardMarkup()
    for i in range(1, 6):
        markup.add(InlineKeyboardButton(f"Style {i}", callback_data=f"style_{i}"))
    bot.send_message(user_id, "Choose a script style:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("style_"))
def handle_style_selection(call):
    style_number = call.data.split("_")[1]
    user_id = call.message.chat.id
    user_state[user_id] = {
        "step": "awaiting_prompt",
        "style_number": style_number
    }
    bot.send_message(user_id, f"Great. Now send me your topic.")

@bot.message_handler(func=lambda message: user_state.get(message.chat.id, {}).get("step") == "awaiting_prompt")
def handle_prompt(message):
    user_id = message.chat.id
    style_number = user_state[user_id]["style_number"]
    prompt = message.text
    script = generate_script(prompt, style_number)
    user_state[user_id]["script"] = script
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✅ Approve", callback_data="approve"))
    markup.add(InlineKeyboardButton("✏️ Edit", callback_data="edit"))
    markup.add(InlineKeyboardButton("🔁 Regenerate", callback_data="regenerate"))
    bot.send_message(user_id, f"Here’s your script:\n\n{script}", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["approve", "edit", "regenerate"])
def handle_script_action(call):
    user_id = call.message.chat.id
    action = call.data

    if action == "approve":
        bot.send_message(user_id, "Script approved. Generating voice and visuals...")
        try:
            script = user_state[user_id]["script"]
            video_path = generate_video_with_images(script)
            with open(video_path, "rb") as f:
                bot.send_video(user_id, f)
        except Exception as e:
            bot.send_message(user_id, f"❌ Video generation failed: {e}")

    elif action == "edit":
        user_state[user_id]["step"] = "awaiting_prompt"
        bot.send_message(user_id, "Okay. Send me your revised topic or prompt.")

    elif action == "regenerate":
        style_number = user_state[user_id]["style_number"]
        prompt = user_state[user_id].get("prompt", "History")
        script = generate_script(prompt, style_number)
        user_state[user_id]["script"] = script
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("✅ Approve", callback_data="approve"))
        markup.add(InlineKeyboardButton("✏️ Edit", callback_data="edit"))
        markup.add(InlineKeyboardButton("🔁 Regenerate", callback_data="regenerate"))
        bot.send_message(user_id, f"Here’s a new version:\n\n{script}", reply_markup=markup)

@app.post("/")
async def webhook(req: Request):
    body = await req.body()
    bot.process_new_updates([telebot.types.Update.de_json(body.decode("utf-8"))])
    return {"ok": True}
