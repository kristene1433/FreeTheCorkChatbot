# Updated app.py with minor improvements while maintaining the original structure

import os
import openai
import datetime
import pdfplumber
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv

# ---------------------------------------
# 1) Load environment variables & config
# ---------------------------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("❌ Missing OPENAI_API_KEY in .env")

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
    Create a system prompt referencing the PDF text if available.
    Then send the user's message to OpenAI.
    """
    pdf_info = menu_pdf_text if menu_pdf_text else "(No PDF menu text available)"

    system_prompt = f"""
    You are a knowledgeable sommelier with extensive wine expertise:
    - Regions, producers, wine scores, tasting notes, etc.
    - You also have a real PDF menu for 'Free the Cork' with in-house offerings.
    - Provide detailed info from the PDF text below if a user asks about it.

    PDF MENU CONTENT:
    {pdf_info}

    IMPORTANT:
    1. If asked about the menu, use the PDF text to answer specifically.
    2. Provide wine info, pairing suggestions, tasting notes, etc. from your broad knowledge.
    3. If the user wants an overview of the menu, reference details from the PDF text.
    4. Keep responses professional yet approachable.
    """

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4.5-preview",  # Keep the same model you specified
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        # Return a user-friendly error if OpenAI call fails
        error_msg = f"Error processing request with OpenAI: {str(e)}"
        print(error_msg)
        return error_msg

##################################
# 4) Flask Routes
##################################

@app.route("/")
def home():
    # Minimal landing page text or redirect to the chatbot
    # If you want to show the chat UI directly, use:
    # return render_template("chat.html")
    return "✅ Welcome to the Free The Cork Sommelier Chatbot! Visit /chatbot or POST /chat"


@app.route("/chat", methods=["POST"])
def chat():
    # This endpoint handles AJAX POST requests from chat.html
    data = request.get_json() or {}
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"error": "❌ 'message' field is required"}), 400

    # Get AI's reply
    ai_reply = get_ai_response(user_message)

    # Append to chat logs
    now = datetime.datetime.now().isoformat()
    with open("chat_logs.txt", "a", encoding="utf-8") as log_file:
        log_file.write(f"{now} - USER: {user_message} | AI: {ai_reply}\n")

    return jsonify({"reply": ai_reply})


@app.route("/chatbot", methods=["GET"])
def chatbot():
    # Render the chat.html template from the 'templates' folder
    return render_template("chat.html")


if __name__ == "__main__":
    # Host set to 0.0.0.0 so it's accessible externally if on a server
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
