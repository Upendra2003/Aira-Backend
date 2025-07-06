from flask import Blueprint, request, jsonify
from database.models import chat_collection, brain_collection, get_current_time, journal_collection
from utils.user_utils import get_user_id
from functions.chat_functions import (
    is_first_user_message_today,
    check_and_set_journal_start,
    is_important_message,
    generate_ai_response,
    export_journal
)
import uuid
from datetime import datetime 
import pytz
from bson.objectid import ObjectId
from twilio.twiml.messaging_response import MessagingResponse
from config import SYSTEM_SECRET

chat_bp = Blueprint("chat", __name__, url_prefix="/api/chat")

@chat_bp.route("/send", methods=["POST"])
def chat():
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid token"}), 401
    
    user_id_str = get_user_id(auth_header)
    if not user_id_str:
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        user_id_obj = user_id_str
    except:
        return jsonify({"error": "Invalid user ID"}), 400
    
    user_doc = chat_collection.find_one({"user_id": user_id_obj})
    if not user_doc:
        user_doc = {
            "user_id": user_id_obj,
            "messages": [],
            "typing_flag": 0,
            "journal_start_flag": 0,
            "journal_end_flag": 0
        }
        chat_collection.insert_one(user_doc)

    messages = user_doc["messages"]
    typing_flag = user_doc.get("typing_flag", 0)
    data = request.get_json()
    user_input = data.get("message", "").strip()
    current_time = get_current_time()

    # Automatically start journal if first message of the day
    if user_doc.get("journal_start_flag", 0) == 0 and is_first_user_message_today(messages):
        check_and_set_journal_start(user_doc, user_id_obj)

    if not user_input:
        return jsonify({"error": "Message required for chat"}), 400

    # Analyze user message for importance
    key_data_flag = 1 if is_important_message(user_input) else 0
    user_message = {
        "role": "User",
        "content": user_input,
        "created_at": current_time,
        "key_data_flag": key_data_flag
    }
    messages.append(user_message)

    # Reset typing_flag if necessary
    if typing_flag == 1:
        chat_collection.update_one(
            {"user_id": user_id_obj},
            {"$set": {"typing_flag": 0}}
        )

    # Generate AI response
    response_data = generate_ai_response(user_input, user_id_obj)
    ai_response = response_data.get("message", "").strip()
    message_chunks = [part.strip() for part in ai_response.split("|||")]
    response_id = response_data.get("response_id", "").strip()
    
    ai_message = {
        "role": "AI",
        "response_id": response_id,
        "message_chunks": message_chunks,
        "content": ai_response,
        "created_at": current_time
    }
    messages.append(ai_message)

    chat_collection.update_one({"user_id": user_id_obj}, {"$set": {"messages": messages}})
    
    return jsonify({
        "role": "AI",
        "message": ai_response,
        "response_id": response_id,
        "created_at": current_time,
        "message_chunks": message_chunks
    }), 200

@chat_bp.route("/whatsapp", methods=["POST"])
def whatsapp_chat():
    from_number = request.form.get("From")
    user_input = request.form.get("Body")

    # After receiving user's message
    if user_input.lower().startswith("join"):
        # Optionally respond with a welcome message
        welcome_message = "Hi! I’m AIRA 🌱 Your AI mental health assistant. Feel free to share anything with me."
        twilio_resp.message(welcome_message)
        return str(twilio_resp), 200
    
    if not user_input:
        return "No message", 200

    user_id_obj = from_number

    user_doc = chat_collection.find_one({"user_id": user_id_obj})
    if not user_doc:
        user_doc = {
            "user_id": user_id_obj,
            "messages": [],
            "typing_flag": 0,
            "journal_start_flag": 0,
            "journal_end_flag": 0
        }
        chat_collection.insert_one(user_doc)

    messages = user_doc["messages"]
    current_time = get_current_time()

    if user_doc.get("journal_start_flag", 0) == 0 and is_first_user_message_today(messages):
        check_and_set_journal_start(user_doc, user_id_obj)

    key_data_flag = 1 if is_important_message(user_input) else 0
    user_message = {
        "role": "User",
        "content": user_input,
        "created_at": current_time,
        "key_data_flag": key_data_flag
    }
    messages.append(user_message)

    # Generate AI response
    response_data = generate_ai_response(user_input, user_id_obj)
    ai_response = response_data.get("message", "").strip()
    message_chunks = [part.strip() for part in ai_response.split("|||") if part.strip()]

    ai_message = {
        "role": "AI",
        "response_id": response_data.get("response_id", "").strip(),
        "message_chunks": message_chunks,
        "content": ai_response,
        "created_at": current_time
    }
    messages.append(ai_message)

    chat_collection.update_one({"user_id": user_id_obj}, {"$set": {"messages": messages}})

    # Send each chunk as a separate WhatsApp message
    twilio_resp = MessagingResponse()
    for chunk in message_chunks:
        twilio_resp.message(chunk)

    return str(twilio_resp), 200


@chat_bp.route("/set_typing_flag", methods=["POST"])
def set_typing_flag():
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid token"}), 401

    user_id_obj = get_user_id(auth_header)
    chat_collection.update_one(
        {"user_id": user_id_obj},
        {"$set": {"typing_flag": 1}}
    )
    return jsonify({"message": "Typing flag set to 1"}), 200

@chat_bp.route("/check_typing_flag", methods=["GET"])
def check_typing_flag():
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid token"}), 401

    user_id_obj = get_user_id(auth_header)
    chat_collection.update_one(
        {"user_id": user_id_obj},
        {"$set": {"typing_flag": 1}}
    )
    
    user_doc = chat_collection.find_one({"user_id": user_id_obj})

    if not user_doc or user_doc.get("typing_flag") != 1:
        return jsonify({"message": "No action needed"}), 200

    messages = user_doc.get("messages", [])
    last_message = messages[-1] if messages else {}
    current_time = get_current_time()

    # Message templates
    default_message = "I noticed you’re taking a moment to reply—don’t worry, take all the time you need. I’m here when you’re ready."
    alt_message = "You seem to be taking your time—no rush. I’ll be right here when you're ready to continue."

    # Only send follow-up if last message is from AI (waiting for user)
    if last_message.get("role") == "AI":
        ai_message = default_message
    elif last_message.get("role") == "User":
        ai_message = alt_message
    else:
        ai_message = default_message  # fallback

    # Push message with both content and message_chunks
    chat_collection.update_one(
        {"user_id": user_id_obj},
        {
            "$push": {
                "messages": {
                    "role": "AI",
                    "response_id": str(uuid.uuid4()),
                    "message_chunks": [ai_message],
                    "content": ai_message,
                    "created_at": current_time
                }
            },
            "$set": {"typing_flag": 0}
        }
    )

    return jsonify({
                    "role": "AI",
                    "response_id": str(uuid.uuid4()),
                    "message_chunks": [ai_message],
                    "content": ai_message,
                    "created_at": current_time
                }), 200

@chat_bp.route("/end_journal", methods=["POST"])
def end_journal():
    system_secret = request.headers.get("System-Secret")
    user_id = request.headers.get("User-ID")

    # If scheduler is calling this
    if system_secret == SYSTEM_SECRET and user_id:
        user_doc = chat_collection.find_one({"user_id": user_id})
        if not user_doc:
            return jsonify({"error": "User not found"}), 404

        chat_collection.update_one(
            {"user_id": user_id},
            {"$set": {"journal_end_flag": 1}}
        )

        if user_doc.get("journal_start_flag") == 1:
            print(f"📅 Ending journal for user {user_id} by scheduler...")
            export_journal(user_id)

        return jsonify({"message": "Journal ended by scheduler."}), 200

    # If API is called by frontend, check token
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid token"}), 401

    user_id = get_user_id(auth_header)
    user_doc = chat_collection.find_one({"user_id": user_id})

    if not user_doc:
        return jsonify({"error": "User not found"}), 404

    chat_collection.update_one(
        {"user_id": user_id},
        {"$set": {"journal_end_flag": 1}}
    )

    if user_doc.get("journal_start_flag") == 1:
        export_journal(user_id)

    return jsonify({"message": "Journal ended successfully."}), 200


@chat_bp.route('/get_journals', methods=['GET'])
def get_journals():
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid token"}), 401

    user_id = get_user_id(auth_header)
    journal_doc = journal_collection.find_one({"user_id": user_id})

    if not journal_doc or not journal_doc.get("journals"):
        return jsonify({"journals": []})

    journals = journal_doc["journals"]
    return jsonify({"journals": journals})

@chat_bp.route('/should_initiate_message', methods=['POST'])
def should_initiate_message():
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid token"}), 401

    user_id = get_user_id(auth_header)
    user = brain_collection.find_one({"user_id": ObjectId(user_id)})

    if not user or not user.get("memory_timeline"):
        return jsonify({"should_initiate": False})

    latest_memory = user["memory_timeline"][-1]
    last_msg_date = latest_memory.get("date")
    last_msg_time = latest_memory.get("last_message_time")
    memory = latest_memory.get("memory", "")

    # ✅ Updated: Get name from demographics inside assessments[]
    try:
        name = user.get("assessments", [])[-1]["demographics"].get("name", "there")
    except (IndexError, AttributeError):
        name = "there"

    try:
        last_interaction = datetime.strptime(f"{last_msg_date} {last_msg_time}", "%Y-%m-%d %H:%M:%S")
    except:
        return jsonify({"should_initiate": False})

    now = get_current_time(return_str=False)
    last_interaction_ist = last_interaction.astimezone(pytz.timezone("Asia/Kolkata"))
    hours_passed = (now - last_interaction_ist).total_seconds() / 3600

    if hours_passed >= 6:
        current_hour = now.hour
        if 5 <= current_hour < 12:
            greeting = "Good morning"
        elif 12 <= current_hour < 17:
            greeting = "Good afternoon"
        elif 17 <= current_hour < 21:
            greeting = "Good evening"
        else:
            greeting = "It's late, hope you're getting some rest"

        ejournal_doc = journal_collection.find_one(
            {"user_id": user_id},
            sort=[("journals.exported_at", -1)]
        )

        recent_message = None
        if ejournal_doc and ejournal_doc.get("journals"):
            latest_journal = ejournal_doc["journals"][-1]
            for msg in reversed(latest_journal.get("messages", [])):
                if msg["role"] == "User":
                    recent_message = msg["content"]
                    break

        if not recent_message:
            recent_message = "something you shared last time."

        message = f"Hey {name}, it’s been a while since we last talked. ||| I remember you said: \"{recent_message}\". ||| I’ve been thinking about you and wondering how you’ve been feeling since then. ||| Whenever you’re ready, I’m here to listen—whether you want to pick up where we left off or talk about something new."
        message_parts = [part.strip() for part in message.split("|||")]

        current_time_str = now.strftime("%Y-%m-%d %H:%M:%S")
        chat_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {"journal_start_flag": 1},
                "$push": {
                    "messages": {
                        "role": "AI",
                        "message_chunks": message_parts,
                        "content": message,
                        "created_at": current_time_str
                    }
                }
            },
            upsert=True
        )

        return jsonify({
            "should_initiate": True,
            "message": message,
            "message_chunks": message_parts
        })

    return jsonify({"should_initiate": False})

@chat_bp.route("/welcome_back", methods=["POST"])
def welcome_back():
    import random
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid token"}), 401

    user_id_str = get_user_id(auth_header)
    if not user_id_str:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        user_id_obj = ObjectId(user_id_str)
    except:
        return jsonify({"error": "Invalid user ID"}), 400

    user = brain_collection.find_one({"user_id": user_id_obj})

    # ✅ Get name from updated schema
    try:
        name = user.get("assessments", [])[-1]["demographics"].get("name", "there")
    except (IndexError, AttributeError):
        name = "there"

    # 🕒 Determine time-based greeting
    now = get_current_time(return_str=False)
    current_hour = now.hour
    if 5 <= current_hour < 12:
        time_greeting = "Good morning"
    elif 12 <= current_hour < 17:
        time_greeting = "Good afternoon"
    elif 17 <= current_hour < 21:
        time_greeting = "Good evening"
    else:
        time_greeting = "Hey, up late?"

    # ✨ List of random welcome messages
    message_templates = [
        f"{time_greeting}, {name}! So great to see you back. ||| What's on your mind today? I'm all ears... or rather, all text!",
        f"{time_greeting}, {name}. I'm happy you're here again. ||| Ready to catch up?",
        f"Hey {name}, welcome back! ||| Want to continue from where we left off or start fresh?",
        f"{time_greeting}, {name}. It’s always a good moment when you stop by. ||| What would you like to explore today?",
        f"Hi {name}, I was just thinking about you! ||| What’s been on your mind lately?",
        f"Look who’s back! Hi {name}! ||| Let’s check in—how have things been?",
        f"Hey there {name}! I'm here and ready to dive into anything you want to talk about. ||| What’s new?",
        f"{time_greeting}, {name}. I’m glad to see you again. ||| How are you feeling right now?",
        f"{time_greeting}! Seeing you again made my day, {name}. ||| What would you like to chat about?",
        f"Hi {name}, it’s always a pleasure to reconnect. ||| Let's take a moment—how are you really doing?"
    ]

    # 🎲 Randomly choose one message
    message = random.choice(message_templates)

    current_time = get_current_time()
    response_id = str(uuid.uuid4())
    message_chunks = [part.strip() for part in message.split("|||")]

    ai_message = {
        "role": "AI",
        "response_id": response_id,
        "message_chunks": message_chunks,
        "content": message,
        "created_at": current_time
    }

    chat_collection.update_one(
        {"user_id": user_id_str},
        {"$push": {"messages": ai_message}},
        upsert=True
    )

    return jsonify({
        "role": "AI",
        "response_id": response_id,
        "message": message,
        "created_at": current_time,
        "message_chunks": message_chunks
    }), 200

@chat_bp.route("/get_messages", methods=["GET"])
def get_messages(): 
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid token"}), 401

    user_id_str = get_user_id(auth_header)
    if not user_id_str:
        return jsonify({"error": "Unauthorized"}), 401

    user_doc = chat_collection.find_one({"user_id": user_id_str})
    if not user_doc:
        return jsonify({"messages": []})

    messages = user_doc.get("messages", [])
    return jsonify({"messages": messages}), 200