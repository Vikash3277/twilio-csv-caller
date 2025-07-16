import os
import csv
import io
import threading
from flask import Flask, request, render_template, Response
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Play, Gather
import requests

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Env vars
TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.environ.get("TWILIO_CALLER_ID")
FLASK_DOMAIN = os.environ.get("PUBLIC_FLASK_URL")  # e.g. https://your-app.onrender.com
VOICE_MP3_URL = os.environ.get("AI_PITCH_MP3_URL")  # e.g. from ElevenLabs

client = Client(TWILIO_SID, TWILIO_AUTH)

# Store numbers and call state
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
    response = VoiceResponse()
    if VOICE_MP3_URL:
        response.play(VOICE_MP3_URL)
    gather = Gather(input="speech", action="/process", timeout=5)
    gather.say("If you have any questions about our dispatch service, feel free to ask.")
    response.append(gather)
    response.say("Thank you for your time. Goodbye!")
    response.hangup()
    return Response(str(response), mimetype="application/xml")


@app.route("/process", methods=["POST"])
def process():
    speech = request.form.get("SpeechResult", "")
    print(f"🗣️ Customer asked: {speech}")

    if speech:
        # Call GPT-4o to generate response
        reply = gpt_response(speech)
        # Use ElevenLabs to get TTS audio
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
    call_next()  # Trigger next call if any
    return "OK"


def gpt_response(prompt):
    import openai
    openai.api_key = os.getenv("OPENAI_API_KEY")
    res = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful dispatch assistant. Explain dispatch service charges to truckers."},
            {"role": "user", "content": prompt}
        ]
    )
    return res.choices[0].message.content


def generate_tts_mp3(text):
    eleven_key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": eleven_key,
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
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            filename = f"audio_{int(time.time())}.mp3"
            with open(filename, "wb") as f:
                f.write(response.content)
            return f"{FLASK_DOMAIN}/audio/{filename}"
        else:
            print("❌ TTS failed:", response.text)
    except Exception as e:
        print("❌ TTS error:", e)
    return None


@app.route("/audio/<filename>")
def serve_audio(filename):
    return app.send_static_file(filename)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
