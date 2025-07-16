import os
import csv
import io
import time
import threading
from flask import Flask, request, render_template, Response, send_from_directory
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Play, Gather
import requests
import openai

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Load env vars
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_CALLER_ID")
FLASK_DOMAIN = os.getenv("PUBLIC_FLASK_URL")
openai.api_key = os.getenv("OPENAI_API_KEY")
eleven_key = os.getenv("ELEVENLABS_API_KEY")
voice_id = os.getenv("ELEVENLABS_VOICE_ID")

client = Client(TWILIO_SID, TWILIO_AUTH)

# Call queue
call_queue = []
is_calling = False

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

def call_next():
    global is_calling
    if is_calling or not call_queue:
        return
    is_calling = True
    while call_queue:
        number = call_queue.pop(0)
        print(f"📞 Calling {number}")
        try:
            client.calls.create(
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

@app.route("/voice", methods=["POST"])
def voice():
    print("📢 AI Intro started")
    intro_text = (
        "Hi! This is your dispatch assistant. "
        "We offer affordable dispatch services for truckers. "
        "For example, if a load pays four thousand dollars, we charge only fifty dollars. "
        "Do you have any questions?"
    )

    mp3_url = generate_tts_mp3(intro_text)

    response = VoiceResponse()
    if mp3_url:
        response.play(mp3_url)
    else:
        response.say(intro_text)

    gather = Gather(input="speech", action="/process", timeout=5)
    gather.say("You can ask any questions about our dispatch service.")
    response.append(gather)

    response.say("Thank you. Goodbye.")
    response.hangup()
    return Response(str(response), mimetype="application/xml")

@app.route("/process", methods=["POST"])
def process():
    speech = request.form.get("SpeechResult", "")
    print(f"🗣️ Customer said: {speech}")

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
        response = VoiceResponse()
        response.say("Sorry, I didn't catch that. Goodbye.")
        response.hangup()
        return Response(str(response), mimetype="application/xml")

@app.route("/callback", methods=["POST"])
def callback():
    print("📞 Call ended.")
    call_next()
    return "OK"

def gpt_response(prompt):
    res = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful dispatch assistant. Explain dispatch service charges to truckers clearly and politely."},
            {"role": "user", "content": prompt}
        ]
    )
    return res.choices[0].message.content

def generate_tts_mp3(text):
    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": eleven_key,
            "Content-Type": "application/json"
        }
        payload = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.4,
                "similarity_boost": 0.75
            }
        }

        res = requests.post(url, headers=headers, json=payload)
        if res.status_code == 200:
            filename = f"audio_{int(time.time())}.mp3"
            filepath = os.path.join("audio", filename)
            with open(filepath, "wb") as f:
                f.write(res.content)
            return f"{FLASK_DOMAIN}/audio/{filename}"
        else:
            print("❌ TTS failed:", res.text)
    except Exception as e:
        print("❌ TTS error:", e)
    return None

@app.route("/audio/<filename>")
def serve_audio(filename):
    return send_from_directory("audio", filename)

if __name__ == "__main__":
    if not os.path.exists("audio"):
        os.makedirs("audio")
    app.run(debug=True, port=5000)
