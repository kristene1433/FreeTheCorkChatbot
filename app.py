# app.py
import os
import openai
import datetime
import pdfplumber
from flask import Flask, request, jsonify, render_template, make_response
from flask_cors import CORS
from dotenv import load_dotenv
from google.cloud import texttospeech
import io
import re


from scraper import scrape_experiences  # <-- Our new scraper code

##############################################################################
# 1) Load environment variables & config
##############################################################################
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("❌ Missing OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY

app = Flask(__name__, template_folder="templates")
CORS(app)

##############################################################################
# 2) PDF loading logic (like before)
##############################################################################
PDF_PATH = "MyMenu.pdf"

def load_pdf_text(pdf_path):
    if not os.path.isfile(pdf_path):
        print(f"PDF not found at {pdf_path}. Proceeding without menu text.")
        return None
    text_chunks = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text_chunks.append(extracted)
        return "\n".join(text_chunks).strip()
    except Exception as e:
        print("Error reading PDF:", e)
        return None

menu_pdf_text = load_pdf_text(PDF_PATH)
if menu_pdf_text:
    print("✅ PDF menu loaded successfully.")
else:
    print("⚠️ No PDF menu text loaded or PDF missing.")

##############################################################################
# 3) Global conversation history & experiences data
#    (For a multi-user production site, store these per-user or in a DB.)
##############################################################################
conversation_history = []
EXPERIENCES_DATA = "No experiences data loaded yet."

##############################################################################
# 4) TTS with SSML for natural pacing
##############################################################################
def build_ssml_with_breaks(text: str) -> str:
    # Remove double asterisks
    text = re.sub(r"\*\*", "", text)

    sentences = re.split(r'([.?!])', text)
    ssml_parts = []
    for i in range(0, len(sentences), 2):
        part = sentences[i].strip()
        punc = sentences[i+1] if i+1 < len(sentences) else ''
        if part:
            combined = part + punc
            ssml_parts.append(f"<s>{combined.strip()}</s> <break time='500ms'/>")
    return "<speak>" + " ".join(ssml_parts) + "</speak>"

def synthesize_speech_gcp_ssml(ssml: str, voice_name="en-US-Wavenet-F") -> bytes:
    client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput(ssml=ssml)
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        name=voice_name
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    )
    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config
    )
    return response.audio_content

##############################################################################
# 5) Scrape experiences on startup (or a schedule)
##############################################################################
@app.before_first_request
def load_data():
    global EXPERIENCES_DATA
    # Example: scraping your "Experiences" page
    # Adjust these to match your actual site & selectors
    experiences_url = "http://192.168.4.62:3000/experiences"
    experiences_selector = "div.event-item"  # or whatever
    try:
        events_text = scrape_experiences(experiences_url, experiences_selector)
        EXPERIENCES_DATA = events_text if events_text else "No experiences found on that page."
        print("Loaded EXPERIENCES_DATA:\n", EXPERIENCES_DATA)
    except Exception as e:
        print("Error scraping experiences:", e)

##############################################################################
# 6) Routes
##############################################################################
@app.route("/")
def home():
    return "✅ Welcome to the Free The Cork Sommelier Chatbot! Visit /chatbot or POST /chat"

@app.route("/chat", methods=["POST"])
def chat():
    """
    The main chat endpoint.
    Uses conversation memory + PDF text + scraped experiences in the system prompt.
    """
    global conversation_history, EXPERIENCES_DATA

    data = request.get_json() or {}
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "❌ 'message' field is required"}), 400

    conversation_history.append({"role": "user", "content": user_message})

    # PDF text
    pdf_info = menu_pdf_text if menu_pdf_text else "(No PDF menu text available)"

    # Build system prompt
    system_prompt = f"""
    You are a professional sommelier and website assistant for 'Free The Cork'.
    You have:
      1) Extensive wine knowledge
      2) A PDF menu with in-house offerings:
         {pdf_info}
      3) Updated experiences (events) info from the site:
         {EXPERIENCES_DATA}

    IMPORTANT GUIDELINES:
    - Keep responses friendly, refined, and approachable.
    - If asked about experiences, reference the experiences above.
    - Provide short, helpful answers. If asked for wine or menu suggestions, share only 2-3 at a time.
    """

    # Only keep last 10 messages to avoid large token usage
    messages = [{"role": "system", "content": system_prompt}] + conversation_history[-10:]

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4.5-preview",
            messages=messages,
            temperature=0.7,
            max_tokens=1000
        )

        ai_reply = response["choices"][0]["message"]["content"].strip()

        # Add the assistant's reply to memory
        conversation_history.append({"role": "assistant", "content": ai_reply})

        # Log
        now = datetime.datetime.now().isoformat()
        with open("chat_logs.txt", "a", encoding="utf-8") as log_file:
            log_file.write(f"{now} - USER: {user_message} | AI: {ai_reply}\n")

        return jsonify({"reply": ai_reply})

    except Exception as e:
        error_msg = f"Error: {str(e)}"
        print(error_msg)
        return jsonify({"error": error_msg}), 500

@app.route("/tts", methods=["POST"])
def tts():
    """
    Converts a given 'text' field to spoken audio (MP3).
    """
    data = request.get_json() or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        ssml = build_ssml_with_breaks(text)
        audio_content = synthesize_speech_gcp_ssml(ssml)
        return send_mp3(audio_content)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def send_mp3(audio_data: bytes):
    resp = make_response(audio_data)
    resp.headers.set('Content-Type', 'audio/mpeg')
    resp.headers.set('Content-Disposition', 'inline; filename=\"tts.mp3\"')
    return resp

@app.route("/chatbot", methods=["GET"])
def chatbot():
    # Renders your updated chat.html (the front-end with black box, etc.)
    return render_template("chat.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
