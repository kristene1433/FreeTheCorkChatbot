import os
import openai
import datetime
import pdfplumber
from flask import Flask, request, jsonify, render_template, make_response
from flask_cors import CORS
from dotenv import load_dotenv
from google.cloud import texttospeech  # <-- Google TTS library
import io

# ---------------------------------------
# 1) Load environment variables & config
# ---------------------------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("❌ Missing OPENAI_API_KEY in .env")

# Also ensure GOOGLE_APPLICATION_CREDENTIALS is set to your JSON key
openai.api_key = OPENAI_API_KEY

app = Flask(__name__, template_folder="templates")
CORS(app)

##################################
# 2) Parse the PDF at startup
##################################
PDF_PATH = "MyMenu.pdf"  # Path to your PDF menu on the server

def load_pdf_text(pdf_path):
    """
    Read all text from a small PDF using pdfplumber and return it as a single string.
    For large PDFs, you'd want a chunking or summarizing approach.
    """
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
        full_text = "\n".join(text_chunks)
        return full_text.strip()
    except Exception as e:
        print("Error reading PDF:", e)
        return None

menu_pdf_text = load_pdf_text(PDF_PATH)
if menu_pdf_text:
    print("✅ PDF menu loaded successfully.")
else:
    print("⚠️ No PDF menu text loaded or PDF missing.")

##################################
# 3) AI Chat Logic
##################################

def get_ai_response(user_message: str) -> str:
    """
    Create a system prompt referencing the PDF text if available,
    styled as a professional sommelier & site assistant who offers
    just a couple suggestions at a time and helps navigate the site.
    """
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
    3. If asked about site navigation (e.g., "Where do I find X?"), mention the relevant page
       (Wine Bar, Wines, Accessories, Experiences, etc.).
    4. If asked about the PDF menu, reference the text above but do NOT dump the entire menu;
       give an overview or a couple highlights, unless the user insists on more detail.

    Provide short, helpful answers. You are both a wine expert and a site guide.
    """

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4.5-preview",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        error_msg = f"Error processing request with OpenAI: {str(e)}"
        print(error_msg)
        return error_msg

##################################
# 4) Google TTS function
##################################

def synthesize_speech_gcp(text: str, voice_name="en-US-Wavenet-F") -> bytes:
    """
    Use Google Cloud TTS to convert 'text' to speech (MP3).
    voice_name can be found in GCP docs, e.g. en-GB-Wavenet-A, en-US-Wavenet-F, etc.
    """
    client = texttospeech.TextToSpeechClient()

    synthesis_input = texttospeech.SynthesisInput(text=text)
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
    return response.audio_content  # raw MP3 data

##################################
# 5) Flask Routes
##################################

@app.route("/")
def home():
    return "✅ Welcome to the Free The Cork Sommelier Chatbot! Visit /chatbot or POST /chat"

# AI route
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json() or {}
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "❌ 'message' field is required"}), 400

    ai_reply = get_ai_response(user_message)

    now = datetime.datetime.now().isoformat()
    with open("chat_logs.txt", "a", encoding="utf-8") as log_file:
        log_file.write(f"{now} - USER: {user_message} | AI: {ai_reply}\n")

    return jsonify({"reply": ai_reply})

# TTS route
@app.route("/tts", methods=["POST"])
def tts():
    data = request.get_json() or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        audio_content = synthesize_speech_gcp(text)
        # Return as MP3
        return send_mp3(audio_content)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def send_mp3(audio_data: bytes):
    # Convert bytes to a Flask response with audio/mpeg
    response = make_response(audio_data)
    response.headers.set('Content-Type', 'audio/mpeg')
    response.headers.set('Content-Disposition', 'inline; filename="tts.mp3"')
    return response

@app.route("/chatbot", methods=["GET"])
def chatbot():
    return render_template("chat.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
