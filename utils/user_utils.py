import jwt
from datetime import datetime, timedelta
from config import JWT_SECRET_KEY
from utils.model_utils import get_model

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

def get_user_id(auth_header):
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    try:
        token = auth_header.split(" ")[1]
        user_id = verify_jwt_token(token)
        return user_id  # Returns string if valid, None if invalid
    except:
        return None
    
def generate_user_story(user_data):
    """Generates a personalized user story based on the new schema"""
    model = get_model()

    # Extract name and personal details from assessments → demographics
    demographics = user_data.get("assessments", [{}])[0].get("demographics", {})
    name = demographics.get("name", "This user")
    occupation = demographics.get("occupation", "an individual")
    hobbies = demographics.get("hobbies", "unspecified interests")
    education = demographics.get("education", "")
    age = demographics.get("age", "")

    # Extract goals
    goals = [g.get("data", "") for g in user_data.get("goals", []) if g.get("data")]

    # Construct story context
    story_context = f"""
    You are AIRA, a thoughtful assistant. Write a short, inspiring 3-5 sentence story about the user's journey based on the data below.
    The tone should feel hopeful and motivating. This story will be shown in a welcome card on the user's dashboard.

    - Name: {name}
    - Age: {age}
    - Occupation: {occupation}
    - Hobbies: {hobbies}
    - Education: {education}
    - Goals: {', '.join(goals) if goals else 'None'}

    Only output the short story. Do not include headings or explanations.
    """

    try:
        result = model.invoke(story_context)
        return result.content.strip() if hasattr(result, 'content') else str(result).strip()
    except Exception as e:
        print(f"Error generating user story: {e}")
        return f"Welcome, {name}! We're here to help you on your journey."

from operator import itemgetter

def generate_motivational_message_from_chat_history(journal_data):
    journals = journal_data.get("journals", [])

    # 1. Skip empty journals
    valid_journals = [j for j in journals if j.get("messages")]

    if not valid_journals:
        return "Wishing you a peaceful day ahead 🌼 – AIRA"

    # 2. Sort journals by date descending (latest first)
    sorted_journals = sorted(valid_journals, key=itemgetter("date"), reverse=True)

    # 3. Collect messages from the most recent journals
    all_messages = []
    for journal in sorted_journals:
        all_messages.extend(journal.get("messages", []))

    # 4. Filter out empty or missing content
    filtered_messages = [m for m in all_messages if m.get("content")]

    # 5. Take the last 10 relevant messages (User + AI)
    last_10_messages = filtered_messages[-10:]

    # 6. Format the messages for the prompt
    chat_text = "\n".join([
        f"{msg['role']}: {msg['content']}" for msg in last_10_messages
    ])

    # 7. Prompt AIRA for a motivational message
    prompt = f"""
    You are AIRA, a friendly and supportive AI therapist. Based on the user’s recent messages, generate a **very short motivational message** (max 8 words) that reflects their passions, struggles, or energy.

    Guidelines:
    - Keep it extremely concise: **3–5 words only**
    - Make it feel personal and warm
    - Add 1 relevant emoji at most
    - Sound like AIRA: casual, kind, uplifting
    - Avoid generic phrases like “Have a nice day” and also these starters "Here's a short motivational message for the user:"

    Here are the recent messages:
    {chat_text}

    Now, generate a short motivational line:
    """

    model = get_model()
    try:
        result = model.invoke(prompt)
        return result.content.strip() if hasattr(result, 'content') else str(result).strip()
    except Exception as e:
        print(f"Error generating motivation: {e}")
        return "Keep going, you're doing beautifully 💪 – AIRA"
