from flask import Flask, request, Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
import os

app = Flask(__name__)

# ENV variables
websocket_url = os.environ.get("WS_STREAM_URL")  # e.g. wss://your-domain.com/ws

@app.route("/twiml-stream", methods=["POST"])
def twiml_stream():
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=websocket_url)
    response.append(connect)
    response.say("Connecting you to the AI agent.")
    return Response(str(response), mimetype="application/xml")

@app.route("/")
def health():
    return "✅ Flask server is live."

if __name__ == "__main__":
    app.run(port=5000)
