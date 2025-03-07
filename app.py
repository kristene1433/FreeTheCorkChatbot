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
# 2) PDF loading logic (if you have a PDF menu)
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
# 3) Global conversation history (simple demo). For production, store per-user.
##############################################################################
conversation_history = []  # We'll keep the last N messages here

##############################################################################
# 4) TTS with SSML for natural pacing
##############################################################################
def build_ssml_with_breaks(text: str) -> str:
    # Remove markdown asterisks so they're not spoken
    text = re.sub(r"\*\*", "", text)

    # Insert <break> after punctuation for more natural pacing
    sentences = re.split(r'([.?!])', text)
    ssml_parts = []
    for i in range(0, len(sentences), 2):
        part = sentences[i].strip()
        punc = sentences[i+1] if i+1 < len(sentences) else ''
        if part:
            combined = part + punc
            ssml_parts.append(f"<s>{combined.strip()}</s> <break time=\"500ms\"/>")
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
# 5) Routes
##############################################################################
@app.route("/")
def home():
    return "✅ Welcome to the Free The Cork Sommelier Chatbot! Visit /chatbot or POST /chat"

@app.route("/chat", methods=["POST"])
def chat():
    """
    The main chat endpoint:
      - Appends the user's message to a global conversation history.
      - Builds an OpenAI request with system prompt + last messages.
      - Returns the AI's reply and saves it to conversation history.
    """
    global conversation_history

    data = request.get_json() or {}
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "❌ 'message' field is required"}), 400

    # Add user message to conversation
    conversation_history.append({"role": "user", "content": user_message})

    # Build a system prompt that includes your PDF's text
    pdf_info = menu_pdf_text if menu_pdf_text else "(No PDF menu text available)"
    system_prompt = f"""
    You are a professional sommelier and website assistant for 'Free The Cork', a
    stylish wine bar & online shop. You have extensive wine knowledge (regions,
    producers, wine scores, tasting notes) AND you understand the layout of the website:
      - Home, Wine Bar, Wines, Accessories, Experiences, Account, Menu PDF, etc.
    You can guide customers around the site, telling them about each section if asked.
    
    You also have a PDF menu with in-house offerings:
    {pdf_info}

    IMPORTANT GUIDELINES:
    1. Always keep responses friendly, refined, and approachable.
    2. If a user requests wine or menu suggestions, only provide 2 or 3 recommendations
       at a time, unless they explicitly ask for more.
    3. If asked about site navigation (e.g., "Where do I find X?"), mention the relevant page.
    4. If asked about the PDF menu, reference it but do NOT dump the entire menu.

    Provide short, helpful answers. You are both a wine expert and a site guide.
    """

    # Build final messages array:
    # Start with system, then only last 10 messages to avoid large tokens
    messages = [{"role": "system", "content": system_prompt}] + conversation_history[-10:]

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4.5-preview",
            messages=messages,
            temperature=0.7,
            max_tokens=1000
        )
        ai_reply = response["choices"][0]["message"]["content"].strip()

        # Append the assistant's reply to the conversation
        conversation_history.append({"role": "assistant", "content": ai_reply})

        # Log
        now = datetime.datetime.now().isoformat()
        with open("chat_logs.txt", "a", encoding="utf-8") as log_file:
            log_file.write(f"{now} - USER: {user_message} | AI: {ai_reply}\n")

        return jsonify({"reply": ai_reply})

    except Exception as e:
        error_msg = f"Error processing request with OpenAI: {str(e)}"
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
    # This renders your updated chat.html
    return render_template("chat.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
