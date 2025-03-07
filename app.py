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
# 3) Global conversation history (simple demo). 
#    For production, store per-user (session or database).
##############################################################################
conversation_history = []

##############################################################################
# 4) TTS with SSML for more natural pacing
##############################################################################
def build_ssml_with_breaks(text: str) -> str:
    """
    Convert plain text to SSML:
    - Remove asterisks
    - Insert breaks after punctuation
    """
    text = re.sub(r"\*\*", "", text)  # remove markdown bold
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
# 5) POST-PROCESSING HELPERS (to remove numeric bullets, reduce commas, etc.)
##############################################################################
def remove_numeric_bullets(text: str) -> str:
    """
    Strips lines beginning with "1) ", "1. ", "1)", etc.
    Also merges repeated commas like ",," -> ","
    """
    lines = text.split('\n')
    new_lines = []
    for line in lines:
        # Remove numeric bullet patterns at the start of each line
        line = re.sub(r'^\d+[\).]\s*', '', line.strip())
        new_lines.append(line)

    # Merge them back
    no_bullets = '\n'.join(new_lines)
    # Replace repeated commas with a single comma
    no_dbl_commas = re.sub(r',+', ',', no_bullets)
    return no_dbl_commas.strip()

##############################################################################
# 6) Routes
##############################################################################
@app.route("/")
def home():
    return "✅ Welcome to the Free The Cork Sommelier Chatbot! Visit /chatbot or POST /chat"

@app.route("/chat", methods=["POST"])
def chat():
    """
    The main chat endpoint:
      - Appends the user's message to a global conversation history
      - Builds an OpenAI request with system prompt + last messages
      - Returns the AI's reply (post-processed for readability)
    """
    global conversation_history

    data = request.get_json() or {}
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "❌ 'message' field is required"}), 400

    conversation_history.append({"role": "user", "content": user_message})

    # 1) Our system prompt with PDF info
    #    => We instruct the AI to produce easy-to-read text, no numeric bullets, fewer commas.
    pdf_info = menu_pdf_text if menu_pdf_text else "(No PDF menu text available)"
    system_prompt = f"""
    You are a professional sommelier and website assistant for 'Free The Cork'.
    You have extensive wine knowledge, plus the PDF menu:

    {pdf_info}

    ** GUIDELINES **
    1. Be friendly, refined, and approachable.
    2. Provide only 2-3 suggestions unless user asks for more.
    3. Avoid numeric bullet points. Use short lines or simple paragraphs instead.
    4. Keep punctuation light. Use fewer commas and short sentences so it's easy to read and sounds natural for audio.
    5. Provide concise, direct answers. Use line breaks or short paragraphs for lists.
    6. If asked about the PDF menu, do not dump it entirely—just summarize or highlight relevant items.
    """

    # 2) Build final messages array with system + last 10 messages
    messages = [{"role": "system", "content": system_prompt}] + conversation_history[-10:]

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4.5-preview",
            messages=messages,
            temperature=0.7,
            max_tokens=1000
        )
        raw_ai_reply = response["choices"][0]["message"]["content"].strip()

        # 3) Post-processing: remove bullet points, repeated commas, etc.
        ai_reply = remove_numeric_bullets(raw_ai_reply)

        # 4) Save final AI reply to conversation
        conversation_history.append({"role": "assistant", "content": ai_reply})

        # 5) Logging
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
    We'll rely on our post-processing in /chat to ensure
    the text is already fairly clean for TTS.
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
    # Renders the updated chat.html 
    return render_template("chat.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
