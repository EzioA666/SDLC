# ==============================================================================
# Module: app.py
# Author: Yunzhe Yu (Backend & DevOps)
# Description: Flask REST API server handling SQLite-backed user authentication,
#              saved search history, and asynchronous sneaker price aggregation.
# ==============================================================================

from flask import Flask, request, jsonify
from flask_cors import CORS
from scraper import aggregate_prices
import database

app = Flask(__name__)
CORS(app, allow_headers=["Content-Type", "Authorization"])

database.init_db()


def extract_bearer_token():
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return None


@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or len(password) < 4:
        return jsonify({"error": "Username and a password (min 4 chars) are required"}), 400

    if not database.create_user(username, password):
        return jsonify({"error": "Username already exists"}), 409

    user = database.authenticate_user(username, password)
    return jsonify({
        "message": "Signup successful",
        "username": user["username"],
        "token": user["token"]
    }), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return jsonify({"error": "Missing credentials"}), 400

    user = database.authenticate_user(username, password)
    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({
        "message": "Login successful",
        "username": user["username"],
        "token": user["token"]
    }), 200


@app.route('/api/logout', methods=['POST'])
def logout():
    token = extract_bearer_token()
    database.revoke_token(token)
    return jsonify({"message": "Logged out"}), 200


@app.route('/api/history', methods=['GET', 'DELETE'])
def history():
    token = extract_bearer_token()
    user = database.get_user_by_token(token)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    if request.method == 'DELETE':
        database.clear_search_history(user["id"])
        return jsonify({"status": "cleared"}), 200

    items = database.get_search_history(user["id"])
    return jsonify({"status": "success", "history": items}), 200


@app.route('/api/search', methods=['GET'])
async def search_sneaker():
    sku = (request.args.get('sku') or '').strip()
    if not sku:
        return jsonify({"error": "No results found. Please enter a valid SKU."}), 400

    pricing_data = await aggregate_prices(sku)
    if not pricing_data:
        return jsonify({"error": "No results found", "results": []}), 404

    token = extract_bearer_token()
    user = database.get_user_by_token(token)
    if user:
        best_offer = pricing_data[0]
        database.save_search(
            user["id"],
            sku,
            best_offer.get("price"),
            best_offer.get("platform")
        )

    return jsonify({
        "status": "success",
        "results": pricing_data
    }), 200

@app.route('/api/profile', methods=['GET'])
def profile():
    token = extract_bearer_token()
    user = database.get_user_by_token(token)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    profile_data = database.get_user_profile(user["id"])
    if not profile_data:
        return jsonify({"error": "User not found"}), 404

    return jsonify({"status": "success", "profile": profile_data}), 200


@app.route('/api/favorites', methods=['GET', 'POST'])
def favorites():
    token = extract_bearer_token()
    user = database.get_user_by_token(token)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        query = (data.get('query') or '').strip()
        if not query:
            return jsonify({"error": "Query is required"}), 400

        fav_id = database.add_favorite(
            user["id"],
            query,
            data.get("lowest_price"),
            data.get("platform"),
            data.get("url")
        )
        return jsonify({"status": "saved", "id": fav_id}), 201

    return jsonify({"status": "success", "favorites": database.get_favorites(user["id"])}), 200


@app.route('/api/favorites/<int:fav_id>', methods=['DELETE'])
def delete_favorite(fav_id):
    token = extract_bearer_token()
    user = database.get_user_by_token(token)
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    deleted = database.remove_favorite(user["id"], fav_id)
    if not deleted:
        return jsonify({"error": "Favorite not found"}), 404

    return jsonify({"status": "deleted"}), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)