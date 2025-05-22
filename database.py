# database.py
from pymongo import MongoClient
from bson import ObjectId
from config import Config
import sys

class MongoDB:
    def __init__(self):
        self.client = None
        self.db = None
        self.connected = False
        self.connect()
    
    def connect(self):
        """Connect to MongoDB with better error handling"""
        try:
            print(f"🔄 Attempting to connect to MongoDB...")
            # print(f"📍 URI: {Config.MONGODB_URI}")
            print(f"🗄️  Database: {Config.DATABASE_NAME}")
            
            # Set connection timeout to avoid hanging
            self.client = MongoClient(
                Config.MONGODB_URI,
                serverSelectionTimeoutMS=5000,  # 5 second timeout
                connectTimeoutMS=5000,
                socketTimeoutMS=5000
            )
            
            self.db = self.client[Config.DATABASE_NAME]
            
            # Test connection
            self.client.admin.command('ping')
            self.connected = True
            print(f"✅ Successfully connected to MongoDB: {Config.DATABASE_NAME}")
            
        except Exception as e:
            self.connected = False
            print(f"❌ MongoDB connection failed!")
            print(f"🔧 Error details: {str(e)}")
            print(f"\n💡 Troubleshooting tips:")
            print(f"   1. Make sure MongoDB is running on your system")
            print(f"   2. Check if the connection URI is correct: {Config.MONGODB_URI}")
            print(f"   3. Verify MongoDB is accessible on the specified port")
            print(f"   4. For local MongoDB, try: mongod --dbpath /path/to/your/db")
            print(f"\n⚠️  The app will start but database operations will fail until MongoDB is available.")
            # Don't raise the exception - let the app start
    
    def get_collection(self, collection_name):
        """Get a specific collection"""
        if not self.connected:
            raise Exception("MongoDB is not connected. Please check your MongoDB server.")
        return self.db[collection_name]
    
    def test_connection(self):
        """Test if MongoDB connection is alive"""
        if not self.connected:
            return False
        try:
            self.client.admin.command('ping')
            return True
        except Exception:
            self.connected = False
            return False
    
    def close_connection(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            print("🔌 MongoDB connection closed")

    @staticmethod
    def serialize_doc(doc):
        """Convert ObjectId to string for JSON serialization"""
        if isinstance(doc, list):
            return [MongoDB.serialize_doc(item) for item in doc]
        if isinstance(doc, dict):
            for key, value in doc.items():
                if isinstance(value, ObjectId):
                    doc[key] = str(value)
                elif isinstance(value, (dict, list)):
                    doc[key] = MongoDB.serialize_doc(value)
        return doc

# Create global database instance
db_instance = MongoDB()
