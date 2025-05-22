# Simple Flask MongoDB Query API
# Install: pip install flask pymongo

from flask import Flask, request, jsonify
from pymongo import MongoClient
from bson import ObjectId
import json

app = Flask(__name__)

# MongoDB connection
client = MongoClient('mongodb+srv://sambitmohanty342:5XiRZ7gAi2dPoN6e@david1.saqjywi.mongodb.net/?retryWrites=true&w=majority')  # Change to your MongoDB URI
db = client['sample_mflix']  # Change to your database name

# Helper function to convert ObjectId to string
def serialize_doc(doc):
    if isinstance(doc, list):
        return [serialize_doc(item) for item in doc]
    if isinstance(doc, dict):
        for key, value in doc.items():
            if isinstance(value, ObjectId):
                doc[key] = str(value)
            elif isinstance(value, (dict, list)):
                doc[key] = serialize_doc(value)
    return doc

@app.route('/query/<collection_name>', methods=['GET'])
def query_collection(collection_name):
    try:
        collection = db[collection_name]
        
        # Get query parameters
        limit = request.args.get('limit', 10, type=int)
        skip = request.args.get('skip', 0, type=int)
        
        # Build filter from query parameters
        filter_dict = {}
        for key, value in request.args.items():
            if key not in ['limit', 'skip', 'sort']:
                # Try to convert to appropriate type
                if value.isdigit():
                    filter_dict[key] = int(value)
                elif value.lower() in ['true', 'false']:
                    filter_dict[key] = value.lower() == 'true'
                else:
                    filter_dict[key] = value
        
        # Execute query
        cursor = collection.find(filter_dict).skip(skip).limit(limit)
        
        # Sort if specified
        sort_param = request.args.get('sort')
        if sort_param:
            if sort_param.startswith('-'):
                cursor = cursor.sort(sort_param[1:], -1)  # Descending
            else:
                cursor = cursor.sort(sort_param, 1)  # Ascending
        
        # Convert to list and serialize
        results = list(cursor)
        results = serialize_doc(results)
        
        # Get total count for pagination info
        total_count = collection.count_documents(filter_dict)
        
        return jsonify({
            "data": results,
            "count": len(results),
            "total": total_count,
            "skip": skip,
            "limit": limit
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    try:
        # Test MongoDB connection
        client.admin.command('ping')
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

# Usage Examples:
# GET /query/users - Get all users
# GET /query/users?limit=5 - Get first 5 users
# GET /query/users?name=John - Get users where name=John
# GET /query/users?age=25&city=NYC - Get users where age=25 AND city=NYC
# GET /query/users?skip=10&limit=5 - Pagination (skip 10, get next 5)
# GET /query/users?sort=name - Sort by name ascending
# GET /query/users?sort=-created_at - Sort by created_at descending