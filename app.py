# Flask backend (app.py)
import os
import datetime
import pdfplumber
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import openai

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("❌ 'OPENAI_API_KEY' is missing")

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# Load PDF menu
def load_pdf_text(pdf_path):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ''.join(page.extract_text() for page in pdf.pages)
        return text
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return "No menu information available."

PDF_PATH = 'menu.pdf'
menu_pdf_text = load_pdf_text(PDF_PATH)

# AI Response Logic
def get_ai_response(user_message):
    prompt = f"""
    You're Kristene, the AI Sommelier from Free the Cork.
    You offer personalized wine advice, pairings, tasting notes, and menu details.
    Menu Info: {menu_pdf_text}

    User: {user_message}
    Kristene (AI Sommelier):
    """
    response = openai.ChatCompletion.create(
        model='gpt-4-turbo',
        messages=[{"role": "system", "content": prompt}],
        max_tokens=800,
        temperature=0.7
    )
    return response.choices[0].message.content

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get('message')
    if not user_message:
        return jsonify({'error': '❌ Message field is required'}), 400

    ai_reply = get_ai_response(user_message)

    # Logging
    with open('chat_logs.txt', 'a') as log:
        timestamp = datetime.datetime.now().isoformat()
        log.write(f"[{timestamp}] User: {user_message}\nAI: {ai_reply}\n")

    return jsonify({'reply': ai_reply})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
