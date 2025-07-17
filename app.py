import os
import csv
import io
import time
import threading
from flask import Flask, request, render_template, Response
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
import pandas as pd

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ✅ Load environment variables
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_CALLER_ID")
FLASK_DOMAIN = os.getenv("PUBLIC_FLASK_URL")
MEDIA_SERVER_URL = os.getenv("MEDIA_SERVER_WSS")  # e.g. wss://your-domain.onrender.com/ws

client = Client(TWILIO_SID, TWILIO_AUTH)

# ✅ Home page to upload CSV
@app.route("/")
def index():
    return render_template("index.html")

# ✅ Upload CSV and start calls
@app.route("/upload", methods=["POST"])
def upload():
    file = request.files["file"]
    if not file:
        return "No file uploaded"

    stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
    csv_input = csv.reader(stream)
    numbers = [row[0] for row in csv_input if row]

    threading.Thread(target=initiate_calls, args=(numbers,)).start()
    return "Calls initiated."

# ✅ Initiate outbound calls

def initiate_calls(numbers):
    for number in numbers:
        print(f"📞 Calling {number}...")
        try:
            call = client.calls.create(
                to=number,
                from_=TWILIO_NUMBER,
                url=f"{FLASK_DOMAIN}/voice"
            )
            print(f"✅ Call initiated: {call.sid}")
        except Exception as e:
            print(f"❌ Failed to call {number}: {e}")
        time.sleep(2)  # space out calls

# ✅ TwiML that streams audio to media.py
@app.route("/voice", methods=["POST"])
def voice():
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=MEDIA_SERVER_URL)
    response.append(connect)
    return Response(str(response), mimetype="application/xml")

# ✅ Run Flask app
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
