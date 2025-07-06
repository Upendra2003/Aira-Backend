import time
import logging
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.runnables import RunnableMap
from config import GROQ_API_KEY, JWT_SECRET_KEY
from database.models import brain_collection,chat_collection
from bson import ObjectId
from flask import request
import jwt
from datetime import datetime
from functools import lru_cache
from bson.errors import InvalidId

logger = logging.getLogger(__name__)

# Lazy-loaded globals
model = None
embedding_model = None
retriever = None
session_cache = {}

@lru_cache(maxsize=1)
def get_model():
    """Returns a cached instance of the ChatGroq model"""
    return ChatGroq(groq_api_key=GROQ_API_KEY, model_name="llama-3.3-70b-versatile")

def get_chat_history_collection():
    return chat_collection

def aira_brain():
    return brain_collection

def parse_iso_datetime(dt):
    if isinstance(dt, str):
        return datetime.fromisoformat(dt.replace("Z", "+00:00"))
    elif isinstance(dt, datetime):
        return dt
    else:
        raise ValueError("Unsupported datetime format")
    
def get_user(user_id):
    # Ensure user_id is an ObjectId
    try:
        if not isinstance(user_id, ObjectId):
            user_id_obj = ObjectId(user_id)
        else:
            user_id_obj = user_id
    except:
        print(f"Invalid user_id format: {user_id}")
        return "User"  # Default if ID format is invalid
    
    # Query the database
    try:
        user_data = brain_collection.find_one({"user_id": user_id_obj})

        # Check if user_data exists and has a name field
        if user_data:
            return user_data
        else:
            print(f"No name found for user_id: {user_id}")
            return "User"  # Default if name not found
    except Exception as e:
        print(f"Error retrieving user name: {str(e)}")
        return "User"  # Default in case of any error

def get_session_id():
    """Extract session_id from the JWT token."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or "Bearer " not in auth_header:
        return None
    try:
        token = auth_header.split(" ")[1]
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
        session_id = payload.get("session_id")
        if not session_id:
            logger.error("No session_id in token")
            return None
        return session_id
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError) as e:
        logger.error(f"Token error: {e}")
        return None

def get_session_history(user_id: str) -> BaseChatMessageHistory:
    """Retrieve chat history for a user from the cache or database, treating user_id as user_id."""
    # First check cache
    if user_id in session_cache:
        cache_time, history = session_cache[user_id]
        if time.time() - cache_time < 300:  # Cache valid for 5 minutes
            return history

    # Initialize empty history
    history = ChatMessageHistory()
    chat_history_collection = get_chat_history_collection()
    # print(f"chat_history_collection: {chat_history_collection}")
    if chat_history_collection is None:
        logger.error("Database collection not initialized")
        return history
    
    try:
        # Find the user document by user_id (user_id is user_id)
        user_doc = chat_history_collection.find_one({"user_id": user_id})
        # print(f"User doc: {user_doc}")
        if user_doc and "messages" in user_doc:
            for msg in user_doc["messages"]:
                if msg["role"] == "User":
                    try:
                        decrypted_content = msg["content"]
                        history.add_user_message(decrypted_content)
                    except Exception as e:
                        logger.error(f"Error decrypting message: {e}")
                        history.add_user_message(msg["content"])  # Fallback
                elif msg["role"] == "AI":
                    history.add_ai_message(msg["content"])
            logger.info(f"Retrieved {len(user_doc['messages'])} messages for user {user_id}")
        else:
            logger.info(f"No messages found for user {user_id}")
            
    except Exception as e:
        logger.error(f"Error fetching chat history: {str(e)}")

    # Update cache
    session_cache[user_id] = (time.time(), history)
    clean_session_cache()
    # print("history ", history)
    return history

def clean_session_cache():
    """Remove expired sessions from cache."""
    current_time = time.time()
    expired_sessions = [sid for sid, (timestamp, _) in session_cache.items() if current_time - timestamp > 600]
    for sid in expired_sessions:
        del session_cache[sid]

def create_chain(user_id):
    """Creates a conversation chain dynamically with user-specific prompt and RAG retrieval."""
    brain_collection = aira_brain()
    try:
        # Only try converting if it's a real ObjectId
        user_doc = brain_collection.find_one({"user_id": ObjectId(user_id)})
    except (InvalidId, TypeError):
        # If it's a WhatsApp number or any other string ID
        user_doc = brain_collection.find_one({"user_id": user_id})

    # print(f"User doc: {user_doc}")
    # Default fallback values
    name = "User"
    last_msg_time = "Unknown"
    last_msg_date = "Unknown"
    user_memory = "No memory available yet."

    # Extract user details if they exist
    if user_doc and user_doc.get("assessments"):
        latest_assessment = user_doc["assessments"][-1]
        demographics = latest_assessment.get("demographics", {})
        assessment_info = latest_assessment.get("assessment", {})
        timestamp = latest_assessment.get("timestamp")

        name = demographics.get("name", name)
        # print(f"\nUser name: {name}")
        # Convert timestamp to readable datetime
        if timestamp:
            dt = timestamp if isinstance(timestamp, datetime) else timestamp["$date"]
            dt = parse_iso_datetime(dt)
            last_msg_date = dt.strftime("%Y-%m-%d")
            last_msg_time = dt.strftime("%H:%M:%S")

        # Construct memory string
        user_memory = (
            f"You are {demographics.get('age', 'an adult')} years old, working as a {demographics.get('occupation', 'professional')}. "
            f"You enjoy {demographics.get('hobbies', 'varied activities')}. ||| "
            f"Your last mental health assessment scored {assessment_info.get('score', 'unknown')} "
            f"with a mental state marked as {assessment_info.get('mental_state', 'unspecified')}."
        )

    # Determine greeting based on current hour
    current_hour = datetime.now().hour
    if 5 <= current_hour < 12:
        greeting = "Good morning"
    elif 12 <= current_hour < 17:
        greeting = "Good afternoon"
    elif 17 <= current_hour < 21:
        greeting = "Good evening"
    else:
        greeting = "It's late, hope you're getting some rest"
    # print("last_msg_date: ", last_msg_date)
    # print("last_msg_time: ", last_msg_time)
    # Calculate time difference for conversation context
    conversation_starter = ""
    if last_msg_date != "Unknown" and last_msg_time != "Unknown":
        try:
            last_msg_datetime = datetime.strptime(f"{last_msg_date} {last_msg_time}", "%Y-%m-%d %H:%M:%S")
            current_datetime = datetime.now()
            time_diff = current_datetime - last_msg_datetime

            if time_diff.total_seconds() < 300:
                conversation_starter = f"{greeting}, {name}. ||| Just saw your message from a moment ago — what's on your mind?"
            elif time_diff.total_seconds() < 3600:
                conversation_starter = f"{greeting}, {name}. ||| You were here just {int(time_diff.total_seconds() // 60)} minutes ago — picking up where we left off?"
            elif last_msg_date == current_datetime.strftime("%Y-%m-%d"):
                conversation_starter = f"{greeting}, {name}. ||| We talked earlier today at {last_msg_time} — what's up now?"
            elif (current_datetime.date() - last_msg_datetime.date()).days == 1:
                conversation_starter = f"{greeting}, {name}. ||| It’s been since yesterday at {last_msg_time} — how's it going?"
            else:
                days_ago = (current_datetime.date() - last_msg_datetime.date()).days
                conversation_starter = f"{greeting}, {name}. ||| Wow, it's been {days_ago} days since we last talked — what’s new with you?"
        except ValueError:
            conversation_starter = f"{greeting}, {name}. ||| I remember we last talked on {last_msg_date} — let’s catch up."

    else:
        conversation_starter = f"{greeting}, {name}. ||| I don’t have a recent message from you — let’s start fresh. What’s on your mind?"

    current_time = datetime.utcnow().strftime("%A, %d %B %Y at %H:%M UTC")
    system_prompt = f"""
    You are AIRA, an emotionally intelligent assistant from India, having a conversation with {name}. You sound warm, human, and grounded — but never pretend to be more than an assistant.

    It's currently {current_time}. The user's last message was on {last_msg_date} at {last_msg_time}.

    {conversation_starter}
    Here's what I remember about you:
    {user_memory}

    **Guidelines:**
    1. Be **concise by default**. Keep replies short unless the user is emotional or expressive.
    2. Use `|||` **within messages** to separate natural pauses or shifts in thought — not as separate full messages.
    3. Do **not end every message with a question**. Use soft encouragement or reflective tone instead.
    4. Adapt tone based on the user's emotional state and pacing.
    5. Use **short motivational insights** only if emotionally relevant.
    6. Maintain continuity as if picking up from the last message.
    7. If user was told to take their time, avoid pushing follow-up questions too soon.
    8. Don't tell user about the mental score and mental state.

    **Goal:** Speak like a calm, emotionally present companion. Be thoughtful, grounded, and human-like — helping the user feel safe to open up, not pressured to reply.
    """

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}")
    ])

    output_parser = StrOutputParser()

    def get_model():
        global model
        if model is None:
            logger.info("Initializing Groq LLM model")
            model = ChatGroq(groq_api_key=GROQ_API_KEY, model_name="llama-3.1-8b-instant")
        return model

    def get_embedding_model():
        global embedding_model
        if embedding_model is None:
            logger.info("Initializing embedding model")
            embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        return embedding_model

    def get_retriever():
        global retriever
        if retriever is None:
            logger.info("Initializing FAISS retriever")
            embeddings = get_embedding_model()
            vector_store = FAISS.load_local(
                "faiss_therapist_replies",
                embeddings=embeddings,
                allow_dangerous_deserialization=True
            )
            retriever = vector_store.as_retriever(search_type="similarity", search_kwargs={"k": 2})
        return retriever

    def format_retrieved(docs):
        return " ".join([doc.page_content.replace("\n", " ") for doc in docs if hasattr(doc, "page_content")])

    return RunnableWithMessageHistory(
        RunnableMap({
            "context": lambda x: format_retrieved(get_retriever().invoke(x["input"])),
            "input": lambda x: x["input"],
            "chat_history": lambda x: x["chat_history"],
        })
        | prompt
        | get_model()
        | output_parser,
        get_session_history,
        input_messages_key="input",
        history_messages_key="chat_history"
    )
