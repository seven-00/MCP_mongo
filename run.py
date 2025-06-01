from app import create_app
from config import Config

app = create_app()

if __name__ == '__main__':
    print(f"🚀 Starting Flask MongoDB API")
    print(f"📍 Server: http://{Config.HOST}:{Config.PORT}")
    app.run(debug=Config.DEBUG, host=Config.HOST, port=Config.PORT)
