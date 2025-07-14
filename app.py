from flask import Flask, request, render_template, redirect, url_for, flash, Response
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
from collections import deque
import pandas as pd
import os
import csv
import io

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ✅ Load credentials and URLs from environment
account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
from_number = os.environ.get("TWILIO_PHONE_NUMBER")
websocket_url = os.environ.get("WS_STREAM_URL")               # e.g. wss://your-media-server.onrender.com/ws
public_flask_domain = os.environ.get("PUBLIC_FLASK_URL")     # e.g. https://your-flask-app.onrender.com

client = Client(account_sid, auth_token)

# Call queue
call_queue = deque()
current_call_active = False

@app.route("/", methods=["GET", "POST"])
def upload_file():
    global call_queue, current_call_active

    if request.method == "POST":
        if "file" not in request.files:
            flash("No file part")
            return redirect(request.url)

        file = request.files["file"]
        if file.filename == "":
            flash("No selected file")
            return redirect(request.url)

        if file and file.filename.endswith(".csv"):
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_input = csv.DictReader(stream)

            for row in csv_input:
                number = str(row.get("number", "")).strip()

                # Auto prepend country code if needed
                if number and not number.startswith("+") and number.isdigit():
                    if number.startswith("1") and len(number) == 11:
                        number = "+" + number
                    elif number.startswith("91") and len(number) == 12:
                        number = "+" + number

                if number.startswith("+"):
                    call_queue.append(number)

            if not current_call_active and call_queue:
                next_number = call_queue.popleft()
                place_call(next_number)
                current_call_active = True

            flash("✅ CSV uploaded. Calling numbers one by one.")
            return redirect(url_for("upload_file"))

        flash("❌ Please upload a valid CSV file.")
        return redirect(request.url)

    return render_template("upload.html")


def place_call(to_number):
    print(f"📞 Calling {to_number}")
    call = client.calls.create(
        to=to_number,
        from_=from_number,
        url=f"{public_flask_domain}/twiml-stream",
        status_callback=f"{public_flask_domain}/status-callback",
        status_callback_event=["completed"],
        status_callback_method="POST"
    )
    print(f"✅ Call SID: {call.sid}")


@app.route("/twiml-stream", methods=["POST"])
def twiml_stream():
    print("✅ Generating TwiML stream")
    print(f"🔗 WebSocket URL: {websocket_url}")

    response = VoiceResponse()
    connect = Connect()
    stream = Stream(url=websocket_url, track="outbound")  # ✅ Correct and supported
    connect.append(stream)
    response.append(connect)

    print(f"📝 TwiML Response:\n{str(response)}")
    return Response(str(response), mimetype="application/xml")



@app.route("/status-callback", methods=["POST"])
def status_callback():
    global current_call_active

    print("🛑 Call ended. Starting next.")
    current_call_active = False

    if call_queue:
        next_number = call_queue.popleft()
        place_call(next_number)
        current_call_active = True

    return "OK", 200


if __name__ == "__main__":
    app.run(debug=True, port=5000)
