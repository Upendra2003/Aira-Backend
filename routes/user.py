from flask import Blueprint, request, jsonify
from database.models import get_database
from bson import ObjectId
from werkzeug.security import generate_password_hash
from routes.auth import verify_jwt_token
import logging
from utils.user_utils import generate_user_story
from database.models import get_collection
from database.models import journal_collection
from utils.user_utils import generate_motivational_message_from_chat_history

logger = logging.getLogger(__name__)

user_bp = Blueprint("user", __name__, url_prefix="/api/user")

@user_bp.route("/profile", methods=["GET"])
def get_profile():
    """Retrieve user profile safely."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid token"}), 401
    
    token = auth_header.split(" ")[1]
    user_id = verify_jwt_token(token)
    if not user_id:
        return jsonify({"error": "Unauthorized. Please log in."}), 401

    try:
        db = get_database()
        users_collection = db["users"]
        user = users_collection.find_one({"_id": ObjectId(user_id)}, {"password": 0})
    except Exception as e:
        logger.error(f"Database error while retrieving profile: {e}")
        return jsonify({"error": "Database error", "details": str(e)}), 500

    if not user:
        return jsonify({"error": "User not found"}), 404

    user["user_id"] = str(user["_id"])
    del user["_id"]

    logger.info(f"Profile retrieved for user {user_id}")
    return jsonify({"profile": user}), 200

@user_bp.route("/update", methods=["PUT"])
def update_profile():
    """Update user profile safely."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid token"}), 401
    
    token = auth_header.split(" ")[1]
    user_id = verify_jwt_token(token)
    if not user_id:
        return jsonify({"error": "Unauthorized. Please log in."}), 401

    data = request.json
    new_username = data.get("username")
    new_email = data.get("email")
    new_password = data.get("password")

    if not new_username or not new_email:
        return jsonify({"error": "Username and email are required."}), 400

    try:
        db = get_database()
        users_collection = db["users"]

        # Check if email already exists
        existing_user = users_collection.find_one({"email": new_email, "_id": {"$ne": ObjectId(user_id)}})
        if existing_user:
            return jsonify({"error": "Email is already in use."}), 400

        update_data = {
            "username": new_username,
            "email": new_email
        }

        # Handle password update
        if new_password:
            update_data["password"] = generate_password_hash(new_password)

        result = users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": update_data}
        )
    except Exception as e:
        logger.error(f"Database error while updating profile: {e}")
        return jsonify({"error": "Database error", "details": str(e)}), 500

    if result.modified_count == 0:
        return jsonify({"message": "No changes made or user not found."}), 400

    logger.info(f"Profile updated for user {user_id}")
    return jsonify({"message": "Profile updated successfully"}), 200

@user_bp.route('/generate_story', methods=['GET'])
def generate_story():
    user_id = request.args.get("user_id")
    # print("\n user : ", user_id)
    brain_collection = get_collection("brain")

    try:
        user_object_id = ObjectId(user_id)
    except Exception as e:
        logger.error(f"Invalid user_id format: {str(e)}")
        return jsonify({"error": "Invalid user_id format"}), 400

    # Find the user and their goals
    user = brain_collection.find_one({"user_id": user_object_id})
    if not user:
        return jsonify({"error": "User not found in AIRA's Brain"}), 404
    
    # print("\n user : ", user)


    story = generate_user_story(user)
    return jsonify({"story": story})

@user_bp.route('/send_motivation', methods=['GET'])
def send_motivation():
    user_id = request.args.get("user_id")
    user_chat_history = journal_collection.find_one({"user_id": user_id})
    if not user_chat_history:
        return jsonify({"message": "No chat history found"}), 404

    motivation = generate_motivational_message_from_chat_history(user_chat_history)

    return jsonify({
        "message": motivation
    })

@user_bp.route('/add_streak', methods=['GET'])
def add_streak():
    user_id = request.args.get("user_id")
    streak_days = request.args.get("streak_days", type=int)

    if not user_id or not streak_days:
        return jsonify({"error": "User ID and streak days are required"}), 400

    # Update the user's streak in the database
    try:
        users_collection = get_collection("users")
        result = users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$inc": {"streak": streak_days}}
        )
    except Exception as e:
        logger.error(f"Database error while adding streak: {e}")
        return jsonify({"error": "Database error", "details": str(e)}), 500

    if result.modified_count == 0:
        return jsonify({"message": "No changes made or user not found."}), 400

    logger.info(f"Streak updated for user {user_id}")
    return jsonify({"message": "Streak updated successfully"}), 200

@user_bp.route("/get_streak", methods=["GET"])
def get_streak():
    user_id = request.args.get("user_id")

    if not user_id:
        return jsonify({"error": "User ID is required"}), 400

    try:
        users_collection = get_collection("users")
        user = users_collection.find_one({"_id": ObjectId(user_id)})
    except Exception as e:
        logger.error(f"Database error while retrieving streak: {e}")
        return jsonify({"error": "Database error", "details": str(e)}), 500

    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({"streak": user.get("streak", 0)}), 200