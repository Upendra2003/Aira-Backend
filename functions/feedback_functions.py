import logging
from flask import jsonify
from bson import ObjectId
from datetime import datetime
from database.models import chat_collection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def validate_feedback_data(data):
    """Validate feedback submission data."""
    response_id = data.get("response_id")
    feedback_type = data.get("feedback_type")
    comment = data.get("comment", "").strip()
    
    # Updated valid feedback types
    valid_types = ["like", "dislike", "comment"]
    
    if not response_id or feedback_type not in valid_types:
        logger.warning(f"Invalid feedback data: response_id={response_id}, feedback_type={feedback_type}")
        return False, (jsonify({
            "error": "Invalid feedback data",
            "details": f"response_id and feedback_type {valid_types} are required."
        }), 400)
    
    if feedback_type == "comment" and not comment:
        return False, (jsonify({"error": "Comment required", "details": "Comment cannot be empty."}), 400)
    return True, None

def get_user_feedback(feedback_collection, user_id):
    """Fetch or initialize user feedback document."""
    user_feedback = feedback_collection.find_one({"_id": ObjectId(user_id)})
    if not user_feedback:
        user_feedback = {
            "_id": ObjectId(user_id), 
            "feedback": []
        }
    
    return user_feedback

def handle_like_dislike(user_feedback, response_id, feedback_type):
    """Handle like or dislike feedback."""
    feedback_entry = next((f for f in user_feedback["feedback"] if f["response_id"] == response_id), None)
    if feedback_entry:
        feedback_entry["feedback_type"] = feedback_type
    else:
        user_feedback["feedback"].append({
            "response_id": response_id,
            "feedback_type": feedback_type,
            "timestamp": datetime.utcnow(),
            "comments": []
        })

def handle_comment(user_feedback, response_id, comment):
    """Handle comment feedback."""
    feedback_entry = next((f for f in user_feedback["feedback"] if f["response_id"] == response_id), None)
    if feedback_entry:
        feedback_entry["comments"].append({"text": comment, "timestamp": datetime.utcnow()})
    else:
        user_feedback["feedback"].append({
            "response_id": response_id,
            "feedback_type": "comment",
            "timestamp": datetime.utcnow(),
            "comments": [{"text": comment, "timestamp": datetime.utcnow()}]
        })

def update_user_feedback(feedback_collection, user_id, user_feedback):
    """Update or insert user feedback in the database."""
    try:
        feedback_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": user_feedback},
            upsert=True
        )
        return True, None
    except Exception as e:
        logger.error(f"Database error in update_user_feedback: {str(e)}")
        return False, (jsonify({"error": "Database error", "details": str(e)}), 500)
    
def get_remembered_messages(user_id, response_id):
    """Retrieve user message and AI response from chat-based message data."""

    chat_data = chat_collection.find_one({
        "user_id": str(user_id),
        "messages": {
            "$elemMatch": {
                "role": "AI",
                "response_id": {"$regex": response_id}
            }
        }
    })

    if not chat_data:
        return None, None, (jsonify({"error": "Chat data not found"}), 404)

    messages = chat_data.get("messages", [])
    for i in range(len(messages)):
        msg = messages[i]
        if msg["role"] == "AI" and response_id in msg.get("response_id", ""):
            aira_response = msg.get("content", "")
            # Check the previous message for user input
            if i > 0 and messages[i - 1]["role"] == "User":
                user_message = messages[i - 1].get("content", "")
            else:
                user_message = None
            if user_message and aira_response:
                return user_message, aira_response, None
            else:
                return None, None, (jsonify({"error": "Incomplete message pair"}), 400)

    return None, None, (jsonify({"error": "Response ID not found"}), 404)


def insert_daily_feedback(collection, user_id, rating, comment):
    """Insert or update daily feedback into the feedback collection."""
    try:
        today_str = datetime.now().strftime("%Y-%m-%d")

        daily_feedback_entry = {
            "date": today_str,
            "rating": rating,
            "comment": comment,
            "timestamp": datetime.utcnow()
        }

        # Optional: prevent multiple feedbacks per day
        collection.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$pull": {"daily_feedbacks": {"date": today_str}}  # Remove existing feedback for the day
            }
        )

        # Add new one
        collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$push": {"daily_feedbacks": daily_feedback_entry}},
            upsert=True
        )

        return True, None
    except Exception as e:
        return False, (jsonify({"error": str(e)}), 500)
