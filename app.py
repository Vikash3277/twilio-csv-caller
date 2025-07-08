from flask import Flask, request, render_template, redirect, url_for, flash
import pandas as pd
from twilio.rest import Client
import os

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ✅ Read environment variables directly (Render will inject them)
account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
from_number = os.environ.get("TWILIO_PHONE_NUMBER")
ai_agent_url = "https://render-vps-ypjh.onrender.com/twilio-voice"

# ✅ Log for debugging
print("✅ Twilio SID:", account_sid)
print("✅ FROM number:", from_number)

client = Client(account_sid, auth_token)

@app.route("/", methods=["GET", "POST"])
def upload_file():
    print("📥 / route hit")
    if request.method == "POST":
        if "file" not in request.files:
            flash("No file part")
            return redirect(request.url)

        file = request.files["file"]
        if file.filename == "":
            flash("No selected file")
            return redirect(request.url)

        if file and file.filename.endswith(".csv"):
            df = pd.read_csv(file)

            results = []
            for index, row in df.iterrows():
                number = str(row["number"]).strip()
                prompt = str(row["prompt"]).strip()

                # Append prompt as a query parameter
                dynamic_url = f"{ai_agent_url}?prompt={prompt.replace(' ', '+')}"

                try:
                    call = client.calls.create(
                        to=number,
                        from_=from_number,
                        url=dynamic_url
                    )
                    results.append((number, "✅ Success", call.sid))
                except Exception as e:
                    results.append((number, "❌ Failed", str(e)))

            return render_template("results.html", results=results)

        else:
            flash("Please upload a valid CSV file.")
            return redirect(request.url)

    return render_template("upload.html")

# ✅ Start the server
if __name__ == "__main__":
    app.run(debug=True)
