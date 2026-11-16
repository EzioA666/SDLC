# ==============================================================================
# Module: app.py
# Author: Yunzhe Yu (Backend & DevOps)
# Description: Flask REST API server handling user authentication (/api/signup, 
#              /api/login) and asynchronous sneaker price aggregation (/api/search).
# ==============================================================================

from flask import Flask, request, jsonify
from flask_cors import CORS
from scraper import aggregate_prices

app = Flask(__name__)
CORS(app)

users_db = {} 

@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({"error": "Missing credentials"}), 400
    if username in users_db:
        return jsonify({"error": "Username already exists"}), 409
    users_db[username] = password
    return jsonify({"message": "Signup successful"}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    if users_db.get(username) == password:
        return jsonify({"message": "Login successful", "token": "mock-jwt-token"}), 200
    return jsonify({"error": "Invalid credentials"}), 401

@app.route('/api/search', methods=['GET'])
async def search_sneaker():
    sku = request.args.get('sku')
    if not sku:
        return jsonify({"error": "No results found"}), 400
    
    pricing_data = await aggregate_prices(sku)
    if not pricing_data:
        return jsonify({"error": "No results found", "results": []}), 404
        
    return jsonify({
        "status": "success",
        "results": pricing_data
    }), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)