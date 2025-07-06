from flask import Blueprint, request, jsonify
from datetime import datetime
from bson.objectid import ObjectId
from utils.user_utils import get_user_id
from database.models import brain_collection, users_collection
from functions.gsheet import append_to_google_sheet

assessment_bp = Blueprint("assessment", __name__, url_prefix="/api/assessment")

def store_assessment(user_id, answers, score, demographics):
    assessment_data = {
        "answers": answers,
        "score": score,
        "timestamp": datetime.utcnow()
    }
    brain_collection.update_one(
    {"user_id": ObjectId(user_id)},
    {
        "$setOnInsert": {"demographics": demographics},
        "$push": {"assessments": assessment_data}
    },
    upsert=True
)

@assessment_bp.route('/mental_health', methods=['POST'])
def mental_health_assessment():
    # Get JSON data from request
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid token"}), 401

    user_id = get_user_id(auth_header)
    data = request.get_json()
    answers = data.get('answers')

    # Validate total number of answers
    if not answers or len(answers) < 22:
        return jsonify({"status": "error", "message": "At least 22 answers required"}), 400

    # Split into sections
    demographics_answers = answers[0:7]
    scored_answers = answers[7:19]     # 12 answers for scoring
    reflection_questions = answers[19:22]  # Last 3 reflective responses

    # Scoring map
    option_scores = {
        "always": 4,
        "most of the time": 3,
        "sometimes": 1,
        "never": 0,
        "neutral": 2
    }

    try:
        scores = [option_scores[ans.lower()] for ans in scored_answers]
    except KeyError:
        return jsonify({"status": "error", "message": "Invalid option provided in assessment"}), 400

    total_score = sum(scores)

    # Classify mental state
    if total_score <= 12:
        mental_state = "Low"
    elif 13 <= total_score <= 24:
        mental_state = "Moderate"
    else:
        mental_state = "High"

    demographics = {
        "name": demographics_answers[0],
        "age": demographics_answers[1],
        "gender": demographics_answers[2],
        "occupation": demographics_answers[3],
        "income": demographics_answers[4] if demographics_answers[3] == "working professional" else None,
        "education": demographics_answers[5],
        "hobbies": demographics_answers[6]
    }

    # Build full assessment structure
    assessment_data = {
        "demographics": demographics,
        "assessment": {
            "answers": scored_answers,
            "score": total_score,
            "mental_state": mental_state
        },
        "reflections": {
            "questions": reflection_questions
        },
        "timestamp": datetime.utcnow()
    }

    # Store in brain collection
    brain_collection.update_one(
        {"user_id": ObjectId(user_id)},
        {"$push": {"assessments": assessment_data}},
        upsert=True
    )

    # Set assessment_flag in users collection
    users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"assessment_flag": 1}}
    )

    # Call Google Sheets logger
    append_to_google_sheet({
        **demographics,
        "assessment": {
            "answers": scored_answers,
            "score": total_score,
            "mental_state": mental_state
        },
        "reflections": {
            "questions": reflection_questions
        }
    })

    return jsonify({"status": "success", "score": total_score})



