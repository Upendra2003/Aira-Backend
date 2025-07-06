import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize, sent_tokenize
from afinn import Afinn
from collections import defaultdict
import json
import re
from utils.model_utils import get_model
from database.models import sentiment_collection
from datetime import datetime, timedelta
import random

# Download NLTK data
nltk.download('punkt')
nltk.download('stopwords')

emotional_states = [
    # Negative/Stress-related
    "Burnout", "Overthinking", "Anxiety", "Social Stress", "Low Mood",
    "Perfectionism", "Imposter Syndrome", "Decision Fatigue", "Grief/Loss",
    "Financial Stress", "Health Anxiety", "Identity Stress", "Time Pressure",
    "Caregiver Fatigue", "Adjustment Stress", "Academic/Performance Stress",
    "Environmental Stress", "Future Uncertainty", "Loneliness", "Conflict Distress",
    # Positive/Well-being
    "Happy", "Grateful", "Motivated", "Peaceful", "Content", "Excited",
    "Proud", "Hopeful", "Loved", "Inspired",
    # Neutral / Fallback
    "None"
]

def extract_json_from_text(text):
    """Extract valid JSON from model response."""
    json_pattern = r'({[\s\S]*})'
    matches = re.findall(json_pattern, text)
    for match in matches:
        try:
            data = json.loads(match)
            if isinstance(data, dict) and all(k in data for k in ["mental_score", "emotional_state", "reflection_text", "suggestions"]):
                return match
        except json.JSONDecodeError:
            continue
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return text
    except json.JSONDecodeError:
        pass
    return None

def analyze_single_message(message, model, previous_scores=None):
    """Analyze a single user message for mental wellness indicators."""
    if not message.strip():
        return {
            "mental_score": 80,
            "emotional_state": "None",
            "reflection_text": "This message is too short to analyze. Keep sharing how you're feeling! 🌱",
            "suggestions": ["Try sharing a bit more about your day to help me understand how you're feeling."],
            "supporting_text": ""
        }

    afinn = Afinn()
    sentiment_score = afinn.score(message)
    previous_context = ""
    if previous_scores and len(previous_scores) > 0:
        last_score = previous_scores[-1]
        previous_context = f"""
        Note: The user's previous mental wellness score was {last_score}.
        Adjust the score based on today's message.
        """

    prompt = f"""
    You are Aira, a warm and compassionate mental health assistant. Your role is to reflect on the user's current mental wellness based on a single message and offer gentle, human-centered suggestions for their well-being.

    You will receive:
    - The user's message: {message}
    - Any additional context from previous days: {previous_context}

    Your task:
    1. Analyze the message for emotional sentiment, stress patterns, and mental state.
    2. Assign a score (`mental_score`) from 0–100:
       - 0–40 → indicates concern or emotional struggle
       - 41–70 → mixed state with ups and downs
       - 71–100 → indicates motivation, calm, or wellness
    3. Classify the emotional state (from this list: {emotional_states} or suggest a new one if appropriate).
    4. Write a **brief reflection** (1–2 sentences) summarizing how the user might be feeling, without quoting the message directly.
    5. Provide 1–3 supporting text snippets (short excerpts or the full message if short) explaining why you assigned this score or state.
    6. Offer 1–3 personalized, actionable suggestions (e.g., grounding exercises, journaling, connecting with a friend).

    Output must be in JSON format and include:
    - mental_score (float, 0–100)
    - emotional_state (from the list or a new one if appropriate)
    - reflection_text (1–2 sentences summarizing the user's state)
    - supporting_text (list of 1–2 short excerpts)
    - suggestions (list of 1–3 short helpful tips)

    Make sure your response is caring, insightful, and avoids clinical language. Use friendly emojis sparingly (like 😊, 🧠, or 🌱).

    Format:
    {{
        "mental_score": float,
        "emotional_state": "string",
        "reflection_text": "string",
        "supporting_text": ["string1", "string2", ...],
        "suggestions": ["tip1", "tip2", ...]
    }}
    """
    try:
        response = model.invoke(prompt)
        json_str = extract_json_from_text(response.content)
        if json_str:
            data = json.loads(json_str)
            # Validate mental_score
            if not isinstance(data.get("mental_score"), (int, float)) or not (0 <= data["mental_score"] <= 100):
                data["mental_score"] = max(0, min(100, 80 + sentiment_score))
            # Validate suggestions
            if not isinstance(data.get("suggestions"), list) or not data["suggestions"]:
                data["suggestions"] = ["Keep sharing your thoughts to help me support you better!"]
            # Validate reflection_text
            if not isinstance(data.get("reflection_text"), str) or not data["reflection_text"].strip():
                data["reflection_text"] = "Today seems steady. Keep nurturing your well-being! 🌱"
            # Validate supporting_text
            if not isinstance(data.get("supporting_text"), list) or not data["supporting_text"]:
                data["supporting_text"] = [message[:100] + "..." if len(message) > 100 else message]
            return data
        else:
            return {
                "mental_score": max(0, min(100, 80 + sentiment_score)),
                "emotional_state": "None",
                "reflection_text": "Today seems steady. Keep nurturing your well-being! 🌱",
                "supporting_text": [message[:100] + "..." if len(message) > 100 else message],
                "suggestions": ["Keep sharing your thoughts to help me support you better!"]
            }
    except Exception as e:
        print(f"Error analyzing message: {e}")
        return {
            "mental_score": max(0, min(100, 80 + sentiment_score)),
            "emotional_state": "None",
            "reflection_text": "Today seems steady. Keep nurturing your well-being! 🌱",
            "supporting_text": [message[:100] + "..." if len(message) > 100 else message],
            "suggestions": ["Keep sharing your thoughts to help me support you better!"]
        }

def already_analyzed(user_id, date):
    """Check if the given date was already analyzed for this user."""
    try:
        user_doc = sentiment_collection.find_one({"user_id": str(user_id)})
        if not user_doc:
            return False
        return any(s.get("date") == date for s in user_doc.get("sentiments", []))
    except Exception as e:
        print(f"Error checking if already analyzed: {e}")
        return True

def process_daily_messages(journals, user_id):
    """Process and analyze daily messages one at a time, aggregating scores."""
    day_data = defaultdict(list)
    user_id_str = str(user_id)

    # Aggregate messages by day from journals
    for journal in journals:
        if not journal or journal.get("title") == "Introduction Journal":
            continue
        for msg in journal.get("messages", []):
            if not msg or msg.get("role") != "User" or "created_at" not in msg:
                continue
            try:
                date = msg["created_at"][:10]
                content = msg.get("content", "").strip()
                if content:
                    day_data[date].append(content)
            except Exception as e:
                print(f"Error processing message: {e}")

    # Load model
    try:
        model = get_model()
    except Exception as e:
        print(f"Error getting model: {e}")
        return

    # Get previous scores for context
    previous_scores = []
    try:
        user_doc = sentiment_collection.find_one({"user_id": user_id_str})
        if user_doc and "sentiments" in user_doc:
            sentiments = sorted(user_doc["sentiments"], key=lambda x: x.get("date", ""))[-7:]
            previous_scores = [s.get("mental_score", 80) for s in sentiments]
    except Exception as e:
        print(f"Error getting previous scores: {e}")

    # Get today's date
    today = datetime.now().strftime("%Y-%m-%d")
    cutoff_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    # Ensure user document exists
    sentiment_collection.update_one(
        {"user_id": user_id_str},
        {"$setOnInsert": {"sentiments": []}},
        upsert=True
    )

    # Process each day's messages
    for day, messages in day_data.items():
        try:
            if day < today and already_analyzed(user_id_str, day):
                continue
            if not messages:
                continue

            # Analyze each message individually
            message_analyses = []
            for message in messages:
                analysis = analyze_single_message(message, model, previous_scores)
                message_analyses.append(analysis)

            # Aggregate scores
            if message_analyses:
                scores = [analysis["mental_score"] for analysis in message_analyses]
                avg_score = sum(scores) / len(scores) if scores else 80
                # Scale to ensure 0–100 range
                mental_score = max(0, min(100, avg_score))

                # Determine dominant emotional state
                emotional_states_count = defaultdict(int)
                for analysis in message_analyses:
                    state = analysis["emotional_state"]
                    emotional_states_count[state] += 1
                dominant_state = max(emotional_states_count.items(), key=lambda x: x[1])[0] if emotional_states_count else "None"

                # Combine reflections
                reflection_texts = [analysis["reflection_text"] for analysis in message_analyses]
                reflection_text = " ".join(reflection_texts[:2])  # Limit to 2 for brevity

                # Collect supporting texts (up to 3)
                supporting_texts = []
                for analysis in message_analyses:
                    supporting_texts.extend(analysis["supporting_text"])
                    if len(supporting_texts) >= 3:
                        break
                supporting_texts = supporting_texts[:3]
                encrypted_supporting_texts = [text for text in supporting_texts]

                # Collect suggestions (up to 3, prioritize unique ones)
                suggestions = []
                for analysis in message_analyses:
                    for suggestion in analysis["suggestions"]:
                        if suggestion not in suggestions and len(suggestions) < 3:
                            suggestions.append(suggestion)

                # Add slight variation to default scores
                if dominant_state == "None" and abs(mental_score - 80) < 0.1:
                    variation = random.uniform(-2, 2)
                    mental_score = 80 + variation

                sentiment_data = {
                    "date": day,
                    "mental_score": mental_score,
                    "emotional_state": dominant_state,
                    "reflection_text": reflection_text or "Today seems steady. Keep nurturing your well-being! 🌱",
                    "supporting_text": encrypted_supporting_texts,
                    "suggestions": suggestions or ["Keep sharing your thoughts to help me support you better!"],
                    "message_count": len(messages)
                }

                # Remove existing sentiment for this day and update
                sentiment_collection.update_one(
                    {"user_id": user_id_str},
                    {"$pull": {"sentiments": {"date": day}}}
                )
                sentiment_collection.update_one(
                    {"user_id": user_id_str},
                    {"$push": {"sentiments": sentiment_data}}
                )
        except Exception as e:
            print(f"Error processing day {day}: {e}")

    # Remove sentiments older than 30 days
    sentiment_collection.update_one(
        {"user_id": user_id_str},
        {"$pull": {"sentiments": {"date": {"$lt": cutoff_date}}}}
    )