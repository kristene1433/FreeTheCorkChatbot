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
SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL")  # e.g., https://your-store.myshopify.com
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")

if not OPENAI_API_KEY:
    raise ValueError("❌ Missing OpenAI API Key. Set it in a .env file.")
if not SHOPIFY_STORE_URL or not SHOPIFY_ACCESS_TOKEN:
    raise ValueError("❌ Missing Shopify API credentials. Set SHOPIFY_STORE_URL and SHOPIFY_ACCESS_TOKEN in your .env file.")

# Initialize Flask app with CORS enabled
app = Flask(__name__, template_folder="templates")
CORS(app)  # Allow Shopify to load chatbot in an iframe

# Root Route (Prevents 404 Error)
@app.route("/")
def home():
    return "✅ Welcome to the Free the Cork Wine Chatbot! Use /chat to talk to the AI or /chatbot for a web interface."

def get_shopify_products():
    """Fetches wine products from your Shopify store via the Admin API."""
    endpoint = f"{SHOPIFY_STORE_URL}/admin/api/2023-10/products.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }
    try:
        response = requests.get(endpoint, headers=headers)
        if response.status_code == 200:
            products = response.json().get("products", [])
            return products
        else:
            print("Error fetching products:", response.text)
            return []
    except Exception as e:
        print("Exception fetching products:", e)
        return []

# AI Chatbot Function (with dynamic Shopify wine product info and enhanced prompt)
def get_ai_response(user_message):
    # Fetch wine products from Shopify
    products = get_shopify_products()
    if products:
        # Get a list of product titles (assuming these are your wines)
        product_titles = [p.get("title") for p in products if p.get("title")]
        dynamic_info = "Current Inventory: " + ", ".join(product_titles)
    else:
        dynamic_info = "Current Inventory: (No products available)"

    # Updated system prompt with explicit instructions for wine products
    system_prompt = f"""
    You are an AI assistant for a Shopify store called 'Free the Cork', a premier wine retailer.
    Your role is to answer any questions about wine, including tasting notes, pairing suggestions, wine regions,
    and detailed product information.
    {dynamic_info}

    IMPORTANT:
    - When a customer asks about wine products, reference only the products listed above.
    - Do not invent or mention any product that is not part of the current inventory.
    - When suggesting products, list only 2 or 3 suggestions unless the customer explicitly asks for more.
    - For all other wine-related questions, provide detailed, knowledgeable, and complete responses.
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
        return response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except Exception as e:
        return f"Error processing request: {str(e)}"

# Flask API Route for Chatbot (For API Calls)
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

# Web Interface for Chatbot (For Browser & Shopify)
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
