from flask import Blueprint, request, jsonify
import logging
from utils.user_utils import get_user_id
from functions.feedback_functions import (
    validate_feedback_data,
    get_user_feedback,
    handle_comment,
    handle_like_dislike,
    update_user_feedback,
    get_remembered_messages,
    insert_daily_feedback
)
from database.models import feedback_collection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

feedback_bp = Blueprint("feedback", __name__, url_prefix="/api/feedback")

@feedback_bp.route("/submit", methods=["POST"])
def submit_feedback():
    """Submit structured feedback for chatbot responses."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid token"}), 401

    user_id = get_user_id(auth_header)
    if not user_id:
        return jsonify({"error": "Invalid user token"}), 401

    data = request.json
    is_valid, error = validate_feedback_data(data)
    if not is_valid:
        return error

    feedback_type = data.get("feedback_type")
    response_id = data.get("response_id")
    comment = data.get("comment", "").strip()

    # Get user messages for the response
    user_message, aira_response, error = get_remembered_messages(user_id, response_id)
    if error:
        return error

    user_feedback = get_user_feedback(feedback_collection, user_id)

    # Handle different feedback types
    if feedback_type in ["like", "dislike"]:
        handle_like_dislike(user_feedback, response_id, feedback_type)
        success, error = update_user_feedback(feedback_collection, user_id, user_feedback)

    elif feedback_type == "comment":
        handle_comment(user_feedback, response_id, comment)
        success, error = update_user_feedback(feedback_collection, user_id, user_feedback)

    else:
        return jsonify({"error": "Unknown feedback type"}), 400

    if not success:
        return error

    return jsonify({"message": "Feedback recorded successfully"}), 200

@feedback_bp.route("/daily", methods=["POST"])
def submit_daily_feedback():
    """Submit daily feedback on AIRA's performance."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid token"}), 401

    user_id = get_user_id(auth_header)
    if not user_id:
        return jsonify({"error": "Invalid user token"}), 401

    data = request.json
    rating = data.get("rating")
    comment = data.get("comment", "")

    if rating is None or not (1 <= int(rating) <= 5):
        return jsonify({"error": "Rating must be between 1 and 5"}), 400

    success, error = insert_daily_feedback(
        feedback_collection, user_id, rating, comment
    )

    if not success:
        return error

    return jsonify({"message": "Daily feedback recorded successfully"}), 200
