from datetime import datetime
import time
from database.models import chat_collection,brain_collection,journal_collection, get_current_time
import uuid
from bson.objectid import ObjectId
from utils.model_utils import create_chain,get_model
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from bson.errors import InvalidId

def is_first_user_message_today(messages):
    today = datetime.utcnow().date()
    for msg in messages:
        if msg["role"] == "User":
            msg_time = datetime.fromisoformat(msg["created_at"]).date()
            if msg_time == today:
                return False
    return True

def check_and_set_journal_start(user_doc, user_id_obj):
    if user_doc.get("journal_start_flag", 0) == 0:
        chat_collection.update_one(
            {"user_id": user_id_obj},
            {"$set": {"journal_start_flag": 1}}
        )

def is_important_message(text):
    # Simple logic to determine if a message is important
    important_keywords = ["important", "urgent", "help", "need", "problem"]
    return any(keyword in text.lower() for keyword in important_keywords)

def generate_ai_response(user_input: str, user_id: str) -> dict:
    start_time = time.time()    
    
    ai_response = create_chain(user_id).invoke(
        {"input": user_input, "user_id": user_id},
        config={"configurable": {"session_id": user_id}}
    )
    
    response_time = round(time.time() - start_time, 2)
    response_id = str(uuid.uuid4())
    current_time = get_current_time()
    
    ai_message = {
        "role": "AI",
        "content": ai_response,
        "created_at": current_time
    }

    # ✅ Push message to chat_collection with proper user_id handling
    try:
        chat_collection.update_one(
            {"user_id": ObjectId(user_id)},
            {"$push": {"messages": ai_message}}
        )
    except (InvalidId, TypeError):
        chat_collection.update_one(
            {"user_id": user_id},
            {"$push": {"messages": ai_message}}
        )

    return {
        "role": "AI",
        "response_id": response_id,
        "message": ai_response,
        "response_time": response_time
    }


def create_or_update_memory_card(user_id_str):
    try:
        model = get_model()
    except Exception as e:
        print(f"Error loading model: {e}")
        return

    user_id = user_id_str
    today_str = datetime.utcnow().date().isoformat()

    # Fetch journal entries
    user_journals = journal_collection.find_one({"user_id": user_id})
    user = brain_collection.find_one({"user_id": ObjectId(user_id)})

    if not user_journals or "journals" not in user_journals:
        print("No journal entries found for user.")
        return

    today_journal = next((j for j in user_journals["journals"] if j["date"] == today_str), None)
    if not today_journal:
        print("No journal for today.")
        return

    combined_messages = [msg["content"] for msg in today_journal["messages"] if msg.get("role") == "User"]
    if not combined_messages:
        print("No user messages to summarize.")
        return

    user_text = "\n".join(combined_messages)[-12000:]

    # Get gender from assessments
    assessments = user.get("assessments", [])
    user_gender = "The user"
    if assessments and "demographics" in assessments[-1]:
        user_gender = assessments[-1]["demographics"].get("gender", "The user")

    memory_timeline = user.get("memory_timeline", [])
    existing_memory = None

    for entry in memory_timeline:
        if entry["date"] == today_str:
            existing_memory = entry["memory"]
            break

    system_prompt = SystemMessage(content=f"""
    You are AIRA, an emotionally intelligent AI who remembers users deeply and personally.

    Your task is to extract emotionally meaningful memories from the user's journal messages. Do not summarize the chat. Do not interpret or explain. Only write factual, emotionally significant insights.

    Focus on:
    - Age, identity, or life stage if mentioned
    - Emotional states or mood patterns
    - Personal struggles, routines, or habits
    - Relationships, values, or coping mechanisms
    - Anything that matters deeply to the user

    Write each insight as a concise statement starting with He/She according to the user's gender. Each statement should capture a key emotional or personal detail and can include related information for context. Avoid transient details unless emotionally significant.

    **Output format:**
    List each memory insight on a new line. No headers, introductions, or extra text.
    Avoid these: 'Here are the rewritten memory insights:'
    """)

    if existing_memory:
        human_prompt = HumanMessage(content=f"""
        Earlier memory for today:
        {existing_memory}

        New journal messages:
        {user_text}

        Refine and rewrite the memory for today, incorporating new emotionally significant insights from the latest messages. List each insight as a concise, factual statement starting with {user_gender}.
        """)
    else:
        human_prompt = HumanMessage(content=f"""
        User's journal messages for today:
        {user_text}

        Write the key memory insights below, each as a concise, factual statement starting with {user_gender}.
        """)

    try:
        response = model.invoke([system_prompt, human_prompt])
        if isinstance(response, AIMessage) and response.content.strip():
            refined_memory = response.content.strip()
            print("Refined memory generated.")

            # Remove any previous entry for today
            memory_timeline = [entry for entry in memory_timeline if entry["date"] != today_str]

            # Add the new memory entry
            memory_timeline.append({
                "date": today_str,
                "last_message_time": datetime.utcnow().strftime("%H:%M:%S"),
                "memory": refined_memory
            })

            # Update the document with the new timeline
            brain_collection.update_one(
                {"user_id": ObjectId(user_id)},
                {"$set": {"memory_timeline": memory_timeline}}
            )

            print("Memory timeline updated at root level.")
        else:
            print("No valid memory returned.")

    except Exception as e:
        print(f"Error during memory generation: {e}")


def export_journal(user_id):
    today_str = datetime.utcnow().date().isoformat()
    print('📅 Exporting journal for user:', user_id, 'for date:', today_str)

    user_doc = chat_collection.find_one({"user_id": user_id})
    if not user_doc or "messages" not in user_doc:
        return

    # Filter today's messages
    today_messages = []
    for msg in user_doc["messages"]:
        msg_date = datetime.fromisoformat(msg["created_at"]).date().isoformat()
        print('📅 Checking message date:', msg_date)
        today_messages.append(msg)  # Store full message object
        print('📹Exporting journal for user:', user_id, 'for date:', today_str)

    if not today_messages:
        return  # No messages for today

    # Check if a journal already exists for today
    existing_doc = journal_collection.find_one({"user_id": user_id, "journals.date": today_str})

    if existing_doc:
        # Append messages to the existing journal for today
        journal_collection.update_one(
            {"user_id": user_id, "journals.date": today_str},
            {"$push": {"journals.$.messages": {"$each": today_messages}}}
        )
    else:
        # Create a new journal entry
        journal_entry = {
            "date": today_str,
            "title": f"Journal - {today_str}",
            "messages": today_messages,
            "exported_at": datetime.utcnow().isoformat()
        }
        journal_collection.update_one(
            {"user_id": user_id},
            {"$push": {"journals": journal_entry}},
            upsert=True
        )

    # Generate memory card based on combined journal data
    create_or_update_memory_card(str(user_id))

    # Reset journaling flags and clear chat history
    chat_collection.update_one(
        {"user_id": user_id},
        {"$set": {
            "messages": [],
            "journal_start_flag": 0,
            "journal_end_flag": 0
        }}
    )