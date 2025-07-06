from flask import Blueprint, request, jsonify
import logging
from database.models import get_collection
from datetime import datetime
import uuid
from bson import ObjectId

logger = logging.getLogger(__name__)

visionboard_bp = Blueprint("visionboard", __name__, url_prefix="/api/visionboard")
 
@visionboard_bp.route("/add_custom_goal", methods=["POST"])
def add_custom_goal():
    data = request.get_json()
    user_id = data.get("user_id")
    goal_text = data.get("goal")
    value=data.get("value")

    if not user_id or not goal_text or not value:
        return jsonify({"error": "Missing required fields"}), 400

    brain_collection = get_collection("brain")

    try:
        user_object_id = ObjectId(user_id)
    except Exception as e:
        return jsonify({"error": "Invalid user_id format"}), 400

    user = brain_collection.find_one({"user_id": user_object_id})
    if not user:
        return jsonify({"error": "User not found in AIRA's Brain"}), 404

    existing_goals = [g["data"].strip().lower() for g in user.get("goals", []) if g["data"]]
    if goal_text.strip().lower() in existing_goals:
        return jsonify({"message": "Goal already exists."}), 200

    encrypted_goal = goal_text.strip()
    if not encrypted_goal:
        return jsonify({"error": "Failed to encrypt goal"}), 500

    goal_id = str(uuid.uuid4())
    new_goal = {
        "goal_id": goal_id,
        "timestamp": datetime.utcnow(),
        "data": encrypted_goal,
        "value": value  
    }

    brain_collection.update_one(
        {"user_id": user_object_id},
        {"$push": {"goals": new_goal}}
    )

    return jsonify({"message": "Custom goal added to AIRA's Brain.", "goal": goal_text, "goal_id": goal_id}), 200

@visionboard_bp.route("/get_goals", methods=["GET"])
def get_goals():
    # Get user_id from query parameters
    user_id = request.args.get("user_id")
    
    if not user_id:
        return jsonify({"error": "Missing user_id parameter"}), 400

    brain_collection = get_collection("brain")

    user = brain_collection.find_one({"user_id": ObjectId(user_id)})

    if not user:
        return jsonify({"error": "User not found in AIRA's Brain"}), 404

    # Get goals or an empty list if none exist
    goals = user.get("goals", [])

    # Format the goals for frontend consumption
    formatted_goals = [
        {
            "id": goal.get("goal_id"),
            "text": goal.get("data"),
            "timestamp": goal.get("timestamp").isoformat() if goal.get("timestamp") else None,
            "value": goal.get("value")  # Include the value field
        }
        for goal in goals
    ]

    return jsonify({
        "message": "Goals retrieved successfully",
        "goals": formatted_goals,
        "count": len(formatted_goals)
    }), 200

@visionboard_bp.route("/delete_goal", methods=["DELETE"])
def delete_goal():
    data = request.get_json()
    user_id = data.get("user_id")
    goal_id = data.get("goal_id")  # response_id of the goal

    if not user_id or not goal_id:
        return jsonify({"error": "Missing user_id or goal_id parameter"}), 400

    brain_collection = get_collection("brain")

    # Find and update the user's document by pulling the goal with matching response_id
    result = brain_collection.update_one(
        {"user_id": ObjectId(user_id)},
        {"$pull": {"goals": {"goal_id": goal_id}}}
    )

    if result.matched_count == 0:
        return jsonify({"error": "User not found"}), 404

    if result.modified_count == 0:
        return jsonify({"error": "Goal not found for the user"}), 404

    return jsonify({
        "message": "Goal deleted successfully",
        "goal_id": goal_id
    }), 200
