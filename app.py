import os
import csv
import io
import time
import threading
from flask import Flask, request, render_template, Response, send_from_directory
from twilio.rest import Client as TwilioClient
from twilio.twiml.voice_response import VoiceResponse, Play, Gather
import requests
from openai import OpenAI  # ✅ fixed import

app = Flask(__name__)
app.secret_key = "supersecretkey"

# === Environment variables ===
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_CALLER_ID")
FLASK_DOMAIN = os.getenv("PUBLIC_FLASK_URL")
VOICE_DIR = "static/audio"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")

# ✅ Clients
twilio_client = TwilioClient(TWILIO_SID, TWILIO_AUTH)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

call_queue = []
is_calling = False

# === Routes ===

@app.route("/", methods=["GET", "POST"])
def index():
    global call_queue, is_calling

    if request.method == "POST":
        file = request.files.get("file")
        if file and file.filename.endswith(".csv"):
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            reader = csv.DictReader(stream)
            call_queue = [row["number"].strip() for row in reader if row.get("number")]
            threading.Thread(target=call_next).start()
            return render_template("upload.html", status=f"✅ {len(call_queue)} numbers queued.")
        return render_template("upload.html", status="❌ Invalid file.")
    return render_template("upload.html")


@app.route("/voice", methods=["POST"])
def voice():
    print("📢 AI Intro started")
    ai_text = (
        "Hi there! We offer affordable dispatch services to truckers like you. "
        "For example, on a load paying $4000, we charge just $50. "
        "If you have any questions, just ask now."
    )
    mp3_url = generate_tts_mp3(ai_text)
    
    response = VoiceResponse()
    if mp3_url:
        response.play(mp3_url)
    else:
        response.say(ai_text)
    
    gather = Gather(input="speech", action="/process", timeout=6)
    gather.say("How can I help you?")
    response.append(gather)
    response.say("Thank you for your time. Goodbye.")
    response.hangup()
    return Response(str(response), mimetype="application/xml")


@app.route("/process", methods=["POST"])
def process():
    speech = request.form.get("SpeechResult", "")
    print(f"🗣️ Customer asked: {speech}")

    if speech:
        reply = gpt_response(speech)
        mp3_url = generate_tts_mp3(reply)

        response = VoiceResponse()
        if mp3_url:
            response.play(mp3_url)
        else:
            response.say(reply)
        response.hangup()
        return Response(str(response), mimetype="application/xml")
    else:
        res = VoiceResponse()
        res.say("Sorry, I didn't catch that. Goodbye.")
        res.hangup()
        return Response(str(res), mimetype="application/xml")



@app.route("/callback", methods=["POST"])
def callback():
    print("📞 Call ended.")
    call_next()
    return "OK"


@app.route("/audio/<filename>")
def serve_audio(filename):
    return send_from_directory(VOICE_DIR, filename)


# === Utility Functions ===

def call_next():
    global is_calling
    if is_calling or not call_queue:
        return
    is_calling = True
    while call_queue:
        number = call_queue.pop(0)
        print(f"📞 Calling {number}")
        try:
            twilio_client.calls.create(
                to=number,
                from_=TWILIO_NUMBER,
                url=f"{FLASK_DOMAIN}/voice",
                status_callback=f"{FLASK_DOMAIN}/callback",
                status_callback_method="POST",
                status_callback_event=["completed"]
            )
        except Exception as e:
            print(f"❌ Failed to call {number}: {e}")
    is_calling = False


def gpt_response(prompt):
    try:
        res = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You're a dispatch assistant. Explain your low-cost dispatch service and how it works."},
                {"role": "user", "content": prompt}
            ]
        )
        return res.choices[0].message.content
    except Exception as e:
        print(f"❌ GPT error: {e}")
        return "Sorry, I had trouble understanding that."


def generate_tts_mp3(text):
    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }

        start = time.time()
        res = requests.post(url, headers=headers, json=payload, timeout=30)
        print(f"🕒 ElevenLabs TTS took {time.time() - start:.2f}s")

        if res.status_code == 200:
            filename = f"audio_{int(time.time() * 1000)}.mp3"
            full_path = os.path.join(VOICE_DIR, filename)
            with open(full_path, "wb") as f:
                f.write(res.content)
            return f"{FLASK_DOMAIN}/audio/{filename}"
        else:
            print("❌ ElevenLabs error:", res.text)

    except requests.exceptions.Timeout:
        print("❌ ElevenLabs request timed out.")
    except Exception as e:
        print(f"❌ TTS generation failed: {type(e).__name__}: {e}")

    return None



if __name__ == "__main__":
    os.makedirs(VOICE_DIR, exist_ok=True)
    app.run(debug=True, port=5000)
