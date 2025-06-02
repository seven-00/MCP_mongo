import requests
import atexit
import re
import os
from datetime import datetime
from bson import ObjectId
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from database import db_instance
from config import Config
from flask_swagger_ui import get_swaggerui_blueprint

import json

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend integration

SWAGGER_URL = '/docs'
API_URL = '/static/swagger.json'  # Path to the OpenAPI JSON spec

swaggerui_blueprint = get_swaggerui_blueprint(SWAGGER_URL, API_URL)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

# Register cleanup function
atexit.register(lambda: db_instance.close_connection())


@app.route('/gemini/analyze', methods=['POST'])
def analyze_data_with_gemini():
    """
    Analyze all data in a specified MongoDB collection with context provided dynamically.
    """
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'your_default_key')
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {'Content-Type': 'application/json'}

    try:
        # Get collection name from request
        collection_name = request.json.get('collection_name')
        analysis_goals = request.json.get(
            'analysis_goals', "Find trends, patterns, or anomalies.")

        if not collection_name:
            return jsonify({"error": "Collection name is required"}), 400

        # Fetch all data from the specified MongoDB collection
        collection = db_instance.get_collection(collection_name)
        data_cursor = collection.find()
        data_list = list(data_cursor)

        if not data_list:
            return jsonify({"error": "No data found in the specified collection"}), 404

        # Derive metadata from the data
        example_data = data_list[:5]  # Use first 5 documents as examples
        fields = list(data_list[0].keys()) if data_list else []
        total_records = len(data_list)

        # Construct a detailed prompt
        prompt = (
            f"The data contains {total_records} records with the following fields: {', '.join(fields)}. "
            f"Here are a few example rows: {json.dumps(example_data, default=str)}. "
            f"{analysis_goals} Please provide insights based on this data."
        )

        # Limit prompt size for Gemini
        prompt = prompt[:10000]

        # Prepare payload for Gemini
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ]
        }

        # Call Gemini API
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        gemini_response = response.json()

        return jsonify({
            "success": True,
            "analysis": gemini_response,
            "data_used": total_records,
            "collection": collection_name
        }), 200

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Gemini API Error: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def build_filter_from_params(args):
    """Build MongoDB filter from query parameters with advanced operators"""
    filter_dict = {}
    excluded_params = ['limit', 'skip', 'sort', 'fields', 'search']
    
    for key, value in args.items():
        if key not in excluded_params:
            # Handle operators in field names (e.g., age__gte=25)
            if '__' in key:
                field, operator = key.split('__', 1)
                parsed_value = parse_value(value)
                
                if operator == 'gte':
                    filter_dict[field] = {'$gte': parsed_value}
                elif operator == 'lte':
                    filter_dict[field] = {'$lte': parsed_value}
                elif operator == 'gt':
                    filter_dict[field] = {'$gt': parsed_value}
                elif operator == 'lt':
                    filter_dict[field] = {'$lt': parsed_value}
                elif operator == 'ne':
                    filter_dict[field] = {'$ne': parsed_value}
                elif operator == 'in':
                    # Handle comma-separated values
                    values = [parse_value(v.strip()) for v in value.split(',')]
                    filter_dict[field] = {'$in': values}
                elif operator == 'nin':
                    values = [parse_value(v.strip()) for v in value.split(',')]
                    filter_dict[field] = {'$nin': values}
                elif operator == 'regex':
                    filter_dict[field] = {'$regex': value, '$options': 'i'}
                elif operator == 'exists':
                    filter_dict[field] = {'$exists': value.lower() == 'true'}
                else:
                    # Unknown operator, treat as regular field
                    filter_dict[key] = parse_value(value)
            else:
                # Regular field matching
                filter_dict[key] = parse_value(value)
    
    return filter_dict

def parse_value(value):
    """Parse string value to appropriate type"""
    if not isinstance(value, str):
        return value
        
    # Try to parse as ObjectId
    if len(value) == 24 and re.match(r'^[0-9a-fA-F]{24}$', value):
        try:
            return ObjectId(value)
        except:
            pass
    
    # Try to parse as integer
    if value.isdigit() or (value.startswith('-') and value[1:].isdigit()):
        return int(value)
    
    # Try to parse as float
    try:
        if '.' in value:
            return float(value)
    except ValueError:
        pass
    
    # Try to parse as boolean
    if value.lower() in ['true', 'false']:
        return value.lower() == 'true'
    
    # Try to parse as datetime (ISO format)
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        pass
    
    # Return as string
    return value

def apply_sorting(cursor, sort_param):
    """Apply sorting to MongoDB cursor with multiple field support"""
    if sort_param:
        sort_fields = []
        for field in sort_param.split(','):
            field = field.strip()
            if field.startswith('-'):
                sort_fields.append((field[1:], -1))  # Descending
            else:
                sort_fields.append((field, 1))  # Ascending
        return cursor.sort(sort_fields)
    return cursor

def build_projection(fields_param):
    """Build MongoDB projection from fields parameter"""
    if not fields_param:
        return None
    
    projection = {}
    for field in fields_param.split(','):
        field = field.strip()
        if field.startswith('-'):
            projection[field[1:]] = 0  # Exclude field
        else:
            projection[field] = 1  # Include field
    
    return projection

def build_text_search_filter(search_term):
    """Build text search filter for multiple common fields"""
    if not search_term:
        return {}
    
    # Common searchable fields - adjust based on your collections
    search_fields = ['name', 'title', 'description', 'email', 'username', 'content']
    
    search_conditions = []
    for field in search_fields:
        search_conditions.append({
            field: {'$regex': search_term, '$options': 'i'}
        })
    
    return {'$or': search_conditions}

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint with detailed database info"""
    try:
        if db_instance.test_connection():
            # Get database stats
            stats = db_instance.db.command("dbStats")
            collections = db_instance.db.list_collection_names()
            
            return jsonify({
                "status": "healthy", 
                "database": "connected",
                "database_name": Config.DATABASE_NAME,
                "collections_count": len(collections),
                "database_size_mb": round(stats.get('dataSize', 0) / (1024 * 1024), 2),
                "timestamp": datetime.utcnow().isoformat()
            }), 200
        else:
            return jsonify({"status": "unhealthy", "database": "disconnected"}), 500
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

@app.route('/query/<collection_name>', methods=['GET'])
def query_collection(collection_name):
    """Query any collection with advanced filtering, pagination, and sorting"""
    try:
        collection = db_instance.get_collection(collection_name)
        
        # Get pagination parameters
        limit = min(request.args.get('limit', Config.DEFAULT_LIMIT, type=int), Config.MAX_LIMIT)
        skip = request.args.get('skip', 0, type=int)
        
        # Build filter from query parameters
        filter_dict = build_filter_from_params(request.args)
        
        # Add text search if provided
        search_term = request.args.get('search')
        if search_term:
            search_filter = build_text_search_filter(search_term)
            if filter_dict:
                filter_dict = {'$and': [filter_dict, search_filter]}
            else:
                filter_dict = search_filter
        
        # Build projection for field selection
        projection = build_projection(request.args.get('fields'))
        
        # Execute query with pagination and projection
        cursor = collection.find(filter_dict, projection).skip(skip).limit(limit)
        
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
                "has_more": (skip + limit) < total_count,
                "page": (skip // limit) + 1 if limit > 0 else 1,
                "total_pages": (total_count + limit - 1) // limit if limit > 0 else 1
            },
            "collection": collection_name
        }
        
        # Add applied filters to response
        if filter_dict:
            response["filters_applied"] = str(filter_dict)
        if search_term:
            response["search_term"] = search_term
        if projection:
            response["fields_selected"] = list(projection.keys())
            
        return jsonify(response), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "collection": collection_name
        }), 500

@app.route('/collections', methods=['GET'])
def list_collections():
    """List all available collections with document counts"""
    try:
        collection_names = db_instance.db.list_collection_names()
        collections_info = []
        
        for name in collection_names:
            try:
                count = db_instance.db[name].count_documents({})
                # Get sample document to show structure
                sample = db_instance.db[name].find_one()
                sample_fields = list(sample.keys()) if sample else []
                
                collections_info.append({
                    "name": name,
                    "count": count,
                    "sample_fields": sample_fields[:10]  # First 10 fields
                })
            except Exception as e:
                collections_info.append({
                    "name": name,
                    "count": 0,
                    "error": str(e)
                })
        
        return jsonify({
            "success": True,
            "collections": collections_info,
            "total_collections": len(collections_info)
        }), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/collection/<collection_name>/schema', methods=['GET'])
def get_collection_schema(collection_name):
    """Get schema information for a collection"""
    try:
        collection = db_instance.get_collection(collection_name)
        
        # Get sample documents to infer schema
        sample_size = min(request.args.get('sample_size', 100, type=int), 1000)
        samples = list(collection.find().limit(sample_size))
        
        if not samples:
            return jsonify({
                "success": True,
                "collection": collection_name,
                "schema": {},
                "document_count": 0
            }), 200
        
        # Analyze field types
        schema = {}
        for doc in samples:
            for field, value in doc.items():
                if field not in schema:
                    schema[field] = {
                        "types": set(),
                        "sample_values": [],
                        "null_count": 0,
                        "total_count": 0
                    }
                
                schema[field]["total_count"] += 1
                
                if value is None:
                    schema[field]["null_count"] += 1
                    schema[field]["types"].add("null")
                else:
                    value_type = type(value).__name__
                    schema[field]["types"].add(value_type)
                    
                    # Add sample values (limit to 5)
                    if len(schema[field]["sample_values"]) < 5:
                        if isinstance(value, (str, int, float, bool)):
                            schema[field]["sample_values"].append(value)
        
        # Convert sets to lists for JSON serialization
        for field_info in schema.values():
            field_info["types"] = list(field_info["types"])
        
        return jsonify({
            "success": True,
            "collection": collection_name,
            "schema": schema,
            "document_count": collection.count_documents({}),
            "sample_size": len(samples)
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "collection": collection_name
        }), 500


@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/collection/<collection_name>/aggregate', methods=['POST'])
def aggregate_collection(collection_name):
    """Execute aggregation pipeline on collection"""
    try:
        collection = db_instance.get_collection(collection_name)
        
        # Get pipeline from request body
        pipeline = request.json.get('pipeline', [])
        
        if not isinstance(pipeline, list):
            return jsonify({
                "success": False,
                "error": "Pipeline must be a list of aggregation stages"
            }), 400
        
        # Execute aggregation
        results = list(collection.aggregate(pipeline))
        results = db_instance.serialize_doc(results)
        
        return jsonify({
            "success": True,
            "data": results,
            "count": len(results),
            "collection": collection_name,
            "pipeline": pipeline
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "collection": collection_name
        }), 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "success": False,
        "error": "Endpoint not found",
        "available_endpoints": [
            "/health",
            "/collections", 
            "/query/<collection>",
            "/collection/<collection>/schema",
            "/collection/<collection>/aggregate",
            "/docs"
        ]
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "success": False,
        "error": "Internal server error"
    }), 500


if __name__ == '__main__':
    # Only print logs if this is the main process, not the reloader
    if os.getenv('WERKZEUG_RUN_MAIN') == 'true':
        print(f"🚀 Starting Enhanced Flask MongoDB API")
        print(f"📍 Server accessible at:")
        print(f"   - Local: http://127.0.0.1:{Config.PORT}")
        print(f"📊 Database: {Config.DATABASE_NAME}")
        print(f"🔧 Debug mode: {Config.DEBUG}")
        print(f"📚 API Docs: http://127.0.0.1:{Config.PORT}/docs")

    app.run(
        debug=Config.DEBUG,
        host=Config.HOST,
        port=Config.PORT
    )
