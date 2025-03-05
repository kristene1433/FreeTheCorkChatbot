import os
import openai
import datetime
import requests
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("❌ Missing OpenAI API Key. Set it in a .env file.")

# Initialize Flask app with CORS enabled
app = Flask(__name__, template_folder="templates")
CORS(app)

openai.api_key = OPENAI_API_KEY

# Root Route
@app.route("/")
def home():
    return "✅ Welcome to the Free the Cork Wine Chatbot! Use /chat to talk to the AI or /chatbot for a web interface."

def get_ai_response(user_message):
    """
    AI Chat function referencing your Next.js site (not Shopify).
    You could statically list categories, product names, or dynamic fetch from your custom backend if you have one.
    """

    # Example static categories / products you'd like the agent to know about
    # (For real usage, you might fetch data from your local DB or another source.)
    product_info = [
        "Red Wines: Josh Cellars Cabernet, Domaine Chevillon Pinot Noir, etc.",
        "White Wines: Vincent Doucet Sancerre, etc.",
        "Rosé & Blush: Chateau Gigery, Pink Moscato, etc.",
        "Champagne & Sparkling: Billecart Salmon, Prosecco, etc.",
        "Dessert & Fortified: Osborne Pedro Ximenez, Port, etc.",
        "Accessories: Corkscrews, Decanters, Stoppers, Aerators.",
    ]
    # Convert list to a single string
    dynamic_info = " | ".join(product_info)

    system_prompt = f"""
    You are an AI assistant for 'Free the Cork', a wine bar and online wine store built with Next.js. 
    You have knowledge about different wines (red, white, rosé, sparkling, dessert) and also accessories. 
    Current offerings: {dynamic_info}

    IMPORTANT:
    - Answer questions about wine, tasting notes, regions, or accessories. 
    - If asked for product suggestions, recommend from the categories above.
    - Provide friendly, knowledgeable, and concise answers. 
    """

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"Error processing request: {str(e)}"

# Flask API Route for Chatbot (For API calls)
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "")
    if not user_message:
        return jsonify({"error": "❌ Message is required"}), 400

    ai_response = get_ai_response(user_message)

    # Log chat to a file
    with open("chat_logs.txt", "a") as log_file:
        log_file.write(f"{datetime.datetime.now()} - User: {user_message} | AI: {ai_response}\n")

    return jsonify({"reply": ai_response})

# Web Interface for Chatbot (For Browser)
@app.route("/chatbot", methods=["GET"])
def chatbot():
    try:
        return render_template("chat.html"), 200
    except Exception as e:
        return f"Error loading chatbot UI: {str(e)}", 500

# Run Flask app with Heroku's assigned PORT
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
