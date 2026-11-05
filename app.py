from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/api/search', methods=['GET'])
def search_sneaker():
    sku = request.args.get('sku')
    
    # QA Implementation: Error & Null fallback
    if not sku:
        return jsonify({"error": "No results found"}), 400
    
    # TODO: Execute concurrent calls to fetch_stockx() and fetch_goat()
    
    return jsonify({
        "status": "success",
        "message": f"Backend initialized. Ready to fetch cross-platform pricing for SKU: {sku}"
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)