from flask import Blueprint, request, jsonify
from functions.sentiment_functions import process_daily_messages
from database.models import get_collection
from bson import ObjectId
from database.models import sentiment_collection, journal_collection
from datetime import datetime, timedelta
from utils.user_utils import get_user_id

sentiment_bp = Blueprint("sentiment", __name__, url_prefix="/api/sentiment")

@sentiment_bp.route('/analyze', methods=['GET'])
def analyze():
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid token"}), 401

    user_id = get_user_id(auth_header)
    if not user_id:
        return jsonify({"error": "Invalid user authentication"}), 401

    user_chat_history = journal_collection.find_one({"user_id": user_id})

    if not user_chat_history:
        return jsonify({"message": "No chat history found"}), 404
    
    journals = user_chat_history.get("journals", [])
    result = process_daily_messages(journals, user_id)
    # print(result)
    return jsonify({"message": "Sentiment analysis completed successfully."}), 200

@sentiment_bp.route('/get_sentiments', methods=['GET'])
def get_sentiments():
    """
    Get sentiment data for a user over time.
    
    Query parameters:
    - user_id: required, the id of the user
    - days: optional, number of days to look back (default: 30)
    - format: optional, 'full' or 'chart' (default: 'chart')
    
    Returns:
    - For 'chart' format: Array of {date, mental_score, emotional_state, reflection_text, supporting_text, suggestions, message_count}
    - For 'full' format: All sentiment data
    """
    try:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid token"}), 401

        user_id = get_user_id(auth_header)
        if not user_id:
            return jsonify({"error": "Invalid user authentication"}), 401
        
        days_back = int(request.args.get('days', 30))
        data_format = request.args.get('format', 'chart')
        
        cutoff_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        
        user_doc = sentiment_collection.find_one({"user_id": str(user_id)})
        if not user_doc or 'sentiments' not in user_doc:
            return jsonify({"data": []}), 200
        
        sentiments = [s for s in user_doc.get('sentiments', []) if s.get('date', '') >= cutoff_date]
        sentiments.sort(key=lambda x: x.get('date', ''))
        
        if data_format == 'chart':
            chart_data = [
                {
                    "date": s.get('date'),
                    "mental_score": s.get('mental_score', 80),
                    "emotional_state": s.get('emotional_state', 'None'),
                    "reflection_text": s.get('reflection_text', ''),
                    "supporting_text": [text for text in s.get('supporting_text', [])],
                    "suggestions": s.get('suggestions', []),
                    "message_count": s.get('message_count', 0)
                }
                for s in sentiments
            ]
            return jsonify({"data": chart_data}), 200
            
        else:  # 'full' format
            return jsonify({"data": sentiments}), 200
            
    except Exception as e:
        print(f"Error retrieving sentiment data: {e}")
        return jsonify({"error": "Failed to retrieve sentiment data", "details": str(e)}), 500

@sentiment_bp.route('/summary', methods=['GET'])
def get_sentiment_summary():
    """
    Get a summary of sentiment data for a user.
    
    Query parameters:
    - user_id: required, the id of the user
    - days: optional, number of days to look back (default: 30)
    - threshold: optional, score threshold for counting stress types (default: 70)
    
    Returns:
    - average_score: Average mental score over the period
    - stress_types: Frequency count of different stress types (only below threshold)
    - trend: 'improving', 'declining', or 'stable'
    - below_threshold_days: Count of days below threshold
    - total_days: Total days with data
    """
    try:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid token"}), 401

        user_id = get_user_id(auth_header)
        if not user_id:
            return jsonify({"error": "Invalid user authentication"}), 401
        
        days_back = int(request.args.get('days', 30))
        threshold = float(request.args.get('threshold', 70))
        
        cutoff_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        
        user_doc = sentiment_collection.find_one({"user_id": str(user_id)})
        if not user_doc or 'sentiments' not in user_doc:
            return jsonify({
                "average_score": 80,
                "stress_types": {},
                "trend": "stable",
                "below_threshold_days": 0,
                "total_days": 0
            }), 200
        
        sentiments = [s for s in user_doc.get('sentiments', []) if s.get('date', '') >= cutoff_date]
        sentiments.sort(key=lambda x: x.get('date', ''))
        
        if not sentiments:
            return jsonify({
                "average_score": 80,
                "stress_types": {},
                "trend": "stable",
                "below_threshold_days": 0,
                "total_days": 0
            }), 200
        
        scores = [s.get('mental_score', 80) for s in sentiments]
        average_score = sum(scores) / len(scores) if scores else 80
        below_threshold_days = sum(1 for score in scores if score < threshold)
        
        stress_types = {}
        for s in sentiments:
            if s.get('mental_score', 80) < threshold:
                stress_type = s.get('emotional_state', 'None')
                if stress_type != 'None':
                    stress_types[stress_type] = stress_types.get(stress_type, 0) + 1
        
        trend = "stable"
        if len(scores) >= 7:
            first_week = scores[:min(7, len(scores)//2)]
            last_week = scores[-min(7, len(scores)//2):]
            first_avg = sum(first_week) / len(first_week)
            last_avg = sum(last_week) / len(last_week)
            diff = last_avg - first_avg
            if diff > 5:
                trend = "improving"
            elif diff < -5:
                trend = "declining"
            elif diff > 2:
                trend = "slightly_improving"
            elif diff < -2:
                trend = "slightly_declining"
        
        recent_change = None
        if len(scores) >= 2:
            recent_change = scores[-1] - scores[-2]
        
        primary_stress = None
        if stress_types:
            primary_stress = max(stress_types.items(), key=lambda x: x[1])[0]
        
        return jsonify({
            "average_score": round(average_score, 1),
            "stress_types": stress_types,
            "trend": trend,
            "below_threshold_days": below_threshold_days,
            "total_days": len(scores),
            "threshold": threshold,
            "recent_change": round(recent_change, 1) if recent_change is not None else None,
            "primary_stress_type": primary_stress
        }), 200
            
    except Exception as e:
        print(f"Error retrieving sentiment summary: {e}")
        return jsonify({"error": "Failed to retrieve sentiment summary", "details": str(e)}), 500