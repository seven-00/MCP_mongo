from flask import Flask, request, jsonify
from database import db_instance
from config import Config
import atexit

app = Flask(__name__)

# Register cleanup function
atexit.register(lambda: db_instance.close_connection())

def build_filter_from_params(args):
    """Build MongoDB filter from query parameters"""
    filter_dict = {}
    excluded_params = ['limit', 'skip', 'sort']
    
    for key, value in args.items():
        if key not in excluded_params:
            # Try to convert to appropriate type
            if value.isdigit():
                filter_dict[key] = int(value)
            elif value.lower() in ['true', 'false']:
                filter_dict[key] = value.lower() == 'true'
            else:
                filter_dict[key] = value
    
    return filter_dict

def apply_sorting(cursor, sort_param):
    """Apply sorting to MongoDB cursor"""
    if sort_param:
        if sort_param.startswith('-'):
            return cursor.sort(sort_param[1:], -1)  # Descending
        else:
            return cursor.sort(sort_param, 1)  # Ascending
    return cursor

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        if db_instance.test_connection():
            return jsonify({
                "status": "healthy", 
                "database": "connected",
                "database_name": Config.DATABASE_NAME
            }), 200
        else:
            return jsonify({"status": "unhealthy", "database": "disconnected"}), 500
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

@app.route('/query/<collection_name>', methods=['GET'])
def query_collection(collection_name):
    """Query any collection with flexible filtering, pagination, and sorting"""
    try:
        collection = db_instance.get_collection(collection_name)
        
        # Get pagination parameters
        limit = min(request.args.get('limit', Config.DEFAULT_LIMIT, type=int), Config.MAX_LIMIT)
        skip = request.args.get('skip', 0, type=int)
        
        # Build filter from query parameters
        filter_dict = build_filter_from_params(request.args)
        
        # Execute query with pagination
        cursor = collection.find(filter_dict).skip(skip).limit(limit)
        
        # Apply sorting if specified
        sort_param = request.args.get('sort')
        cursor = apply_sorting(cursor, sort_param)
        
        # Convert to list and serialize ObjectIds
        results = list(cursor)
        results = db_instance.serialize_doc(results)
        
        # Get total count for pagination info
        total_count = collection.count_documents(filter_dict)
        
        response = {
            "success": True,
            "data": results,
            "pagination": {
                "count": len(results),
                "total": total_count,
                "skip": skip,
                "limit": limit,
                "has_more": (skip + limit) < total_count
            },
            "collection": collection_name
        }
        
        if filter_dict:
            response["filters"] = filter_dict
            
        return jsonify(response), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "collection": collection_name
        }), 500

@app.route('/collections', methods=['GET'])
def list_collections():
    """List all available collections"""
    try:
        collections = db_instance.db.list_collection_names()
        return jsonify({
            "success": True,
            "collections": collections,
            "count": len(collections)
        }), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "success": False,
        "error": "Endpoint not found"
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "success": False,
        "error": "Internal server error"
    }), 500

if __name__ == '__main__':
    print(f"🚀 Starting Flask app on {Config.HOST}:{Config.PORT}")
    print(f"📊 Database: {Config.DATABASE_NAME}")
    print(f"🔧 Debug mode: {Config.DEBUG}")
    
    app.run(
        debug=Config.DEBUG, 
        host=Config.HOST, 
        port=Config.PORT
    )