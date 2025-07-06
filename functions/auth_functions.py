import datetime
import jwt
from config import JWT_SECRET_KEY,SENDER_EMAIL,PASSWORD
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

# Token generation and decoding
def generate_token(user_id, session_id, expiration_delta):
    payload = {
        "user_id": str(user_id),
        "session_id": session_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm="HS256")

def decode_token(token, verify_exp=True):
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"], options={"verify_exp": verify_exp})
    except jwt.ExpiredSignatureError:
        return None if verify_exp else jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False})
    except jwt.InvalidTokenError:
        return None
    

def verify_jwt_token(token):
    """Decode the JWT token and return the user_id if valid."""
    try:
        decoded_token = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
        return decoded_token.get("user_id")  # Ensure this key exists in the token payload
    except jwt.ExpiredSignatureError:
        print("Token has expired")
        return None
    except jwt.InvalidTokenError:
        print("Invalid token")
        return None

def send_welcome_email(email, username):
    sender_email = SENDER_EMAIL
    password = PASSWORD

    # Load HTML template from file
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # print("\n\n base dir ; ", base_dir)
    file_path = os.path.join(base_dir, "Email_Page", "index.html")

    with open(file_path, "r", encoding="utf-8") as f:
        html_template = f.read()

    # Replace placeholder with actual username
    html_content = html_template.replace("{{username}}", username.capitalize())

    # Create email message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Aira Welcomes You 🌿"
    msg["From"] = sender_email
    msg["To"] = email

    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, email, msg.as_string())
        # print(f"Welcome email sent to {email}")
    except Exception as e:
        print(f"Error sending welcome email: {e}")
