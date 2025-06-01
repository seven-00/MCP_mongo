import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    MONGODB_URI = os.getenv("MONGODB_URI")
    DATABASE_NAME = os.getenv("DATABASE_NAME")
    DEBUG = os.getenv("FLASK_DEBUG").lower() == "true"
    HOST = os.getenv('FLASK_HOST', '127.0.0.1')

    PORT = int(os.getenv("FLASK_PORT"))
    DEFAULT_LIMIT = int(os.getenv("DEFAULT_LIMIT", 10))
    MAX_LIMIT = int(os.getenv("MAX_LIMIT", 100))
