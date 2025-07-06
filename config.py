import os
from dotenv import load_dotenv
from cryptography.fernet import Fernet

load_dotenv()

MONGO_URI = os.getenv("MONGO_CONNECTION_STRING")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
CLIENT_ID=os.getenv("CLIENT_ID")
CLIENT_SECRET=os.getenv("CLIENT_SECRET")
ENCRYPTION_KEY=os.getenv("ENCRYPTION_KEY")
SENDER_EMAIL=os.getenv("SENDER_EMAIL")
PASSWORD=os.getenv("PASSWORD")
SYSTEM_SECRET = "my_secret_key_aira"
PORT = int(os.getenv("PORT", 5000))
print(f"🔍 Loaded MONGO_URI: {MONGO_URI}")

fernet = Fernet(ENCRYPTION_KEY)
