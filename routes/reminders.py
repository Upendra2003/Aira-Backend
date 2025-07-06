from flask import Blueprint, request, jsonify
from database.models import reminder_collection
from bson import ObjectId
from datetime import datetime, timedelta
import logging
import pytz

reminder_bp = Blueprint("reminder", __name__, url_prefix="/api/reminder")
logger = logging.getLogger(__name__)

# Timezones
utc_tz = pytz.UTC
ist_tz = pytz.timezone('Asia/Kolkata')

def to_ist(dt):
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except ValueError:
            try:
                dt = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                logger.error(f"Invalid datetime string: {dt}")
                return None
    if dt.tzinfo is None:
        dt = utc_tz.localize(dt)
    return dt.astimezone(ist_tz)

def to_utc(dt):
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except ValueError:
            try:
                dt = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                logger.error(f"Invalid datetime string: {dt}")
                return None
    if dt.tzinfo is None:
        dt = ist_tz.localize(dt)
    return dt.astimezone(utc_tz)

def format_ist_string(dt):
    if isinstance(dt, datetime):
        dt = dt.astimezone(ist_tz)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return dt

@reminder_bp.route("/add_reminder", methods=["POST"])
def add_reminder():
    try:
        data = request.json
        user_id = data.get("user_id")
        title = data.get("title")
        scheduled_time = data.get("scheduled_time")

        if not all([user_id, title, scheduled_time]):
            return jsonify({"error": "Missing required fields"}), 400

        ist_dt = to_ist(scheduled_time)
        if not ist_dt:
            return jsonify({"error": "Invalid scheduled_time format. Use YYYY-MM-DD HH:MM:SS"}), 400
        # print(f"IST DateTime: {ist_dt}")
        # print(f"Scheduled Time: {scheduled_time}")
        now_ist = datetime.now(ist_tz)
        new_reminder = {
            "_id": ObjectId(),
            "generated_reminder": title,
            "scheduled_time": scheduled_time,
            "status": "pending",
            "created_at": format_ist_string(now_ist)
        }

        result = reminder_collection.update_one(
            {"user_id": user_id},
            {"$push": {"reminders": new_reminder}},
            upsert=True
        )

        if result.modified_count > 0 or result.upserted_id:
            return jsonify({"message": "Reminder added", "reminder": new_reminder}), 201
        else:
            return jsonify({"error": "Failed to add reminder"}), 500

    except Exception as e:
        logger.exception("Error adding reminder")
        return jsonify({"error": "Internal server error"}), 500

@reminder_bp.route("/get_all_reminders", methods=["GET"])
def get_all_reminders():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    now = datetime.now(ist_tz)
    user = reminder_collection.find_one({"user_id": user_id})

    if not user:
        return jsonify({"reminders": []}), 200

    reminders = []
    for reminder in user.get("reminders", []):
        try:
            scheduled_str = reminder.get("scheduled_time")
            scheduled_dt = datetime.strptime(scheduled_str, "%Y-%m-%d %H:%M:%S")
            is_due = scheduled_dt <= now and reminder.get("status") == "pending"
        except Exception as e:
            logger.warning(f"Could not parse scheduled_time: {scheduled_str}")
            is_due = False

        reminder_copy = reminder.copy()
        reminder_copy["_id"] = str(reminder_copy["_id"])
        reminder_copy["is_due"] = is_due
        reminders.append(reminder_copy)

    reminders.sort(key=lambda x: x.get("scheduled_time", ""))
    return jsonify({"reminders": reminders}), 200

@reminder_bp.route("/update_reminder", methods=["POST"])
def update_reminder():
    try:
        data = request.json
        user_id = data.get("user_id")
        reminder_id = data.get("reminder_id")
        new_title = data.get("title")
        new_time = data.get("scheduled_time")
        status = data.get("status")

        if not user_id or not reminder_id:
            return jsonify({"error": "Missing user_id or reminder_id"}), 400

        reminder_oid = ObjectId(reminder_id)

        # Fetch user document
        user_doc = reminder_collection.find_one({"user_id": user_id})
        if not user_doc:
            return jsonify({"error": "User not found"}), 404

        # Find the reminder index
        reminders = user_doc.get("reminders", [])
        index = next((i for i, r in enumerate(reminders) if r["_id"] == reminder_oid), -1)

        if index == -1:
            return jsonify({"error": "Reminder not found"}), 404

        # DELETE reminder
        if status == "done":
            result = reminder_collection.update_one(
                {"user_id": user_id},
                {"$pull": {"reminders": {"_id": reminder_oid}}}
            )
            if result.modified_count:
                return jsonify({"message": "Reminder deleted"}), 200
            return jsonify({"error": "Reminder not deleted"}), 404

        # RESCHEDULE reminder
        if status == "not_done":
            if not new_time:
                return jsonify({"error": "Missing scheduled_time"}), 400
            try:
                dt = datetime.strptime(new_time, "%Y-%m-%d %H:%M:%S") + timedelta(hours=1)
                new_time = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                return jsonify({"error": "Invalid time format"}), 400

            update_path = f"reminders.{index}"
            update_fields = {
                f"{update_path}.scheduled_time": new_time,
                f"{update_path}.status": "pending"
            }
            if new_title:
                update_fields[f"{update_path}.generated_reminder"] = new_title

            result = reminder_collection.update_one({"user_id": user_id}, {"$set": update_fields})
            if result.modified_count:
                return jsonify({"message": "Reminder rescheduled", "new_time": new_time}), 200
            return jsonify({"error": "Reminder not updated"}), 404

        # GENERIC UPDATE
        update_fields = {}
        update_path = f"reminders.{index}"
        if new_title:
            update_fields[f"{update_path}.generated_reminder"] = new_title
        if new_time:
            try:
                datetime.strptime(new_time, "%Y-%m-%d %H:%M:%S")
                update_fields[f"{update_path}.scheduled_time"] = new_time
            except Exception:
                return jsonify({"error": "Invalid time format"}), 400

        if not update_fields:
            return jsonify({"error": "Nothing to update"}), 400

        result = reminder_collection.update_one({"user_id": user_id}, {"$set": update_fields})
        if result.modified_count:
            return jsonify({"message": "Reminder updated"}), 200
        return jsonify({"error": "Reminder not updated"}), 404

    except Exception as e:
        logger.exception("Error updating reminder")
        return jsonify({"error": "Internal server error"}), 500


@reminder_bp.route("/delete_reminder", methods=["DELETE"])
def delete_reminder():
    """
    Delete a specific reminder
    Expects JSON body with: user_id, reminder_id
    """
    try:
        data = request.json
        user_id = data.get("user_id")
        reminder_id = data.get("reminder_id")

        if not user_id or not reminder_id:
            return jsonify({"error": "Missing required fields (user_id, reminder_id)"}), 400

        # Delete the reminder from the array
        result = reminder_collection.update_one(
            {"user_id": user_id},
            {"$pull": {"reminders": {"_id": ObjectId(reminder_id)}}}
        )

        if result.modified_count > 0:
            return jsonify({"message": "Reminder deleted successfully"}), 200
        else:
            return jsonify({"error": "Reminder not found"}), 404

    except Exception as e:
        logger.error(f"Error deleting reminder: {str(e)}")
        return jsonify({"error": "An error occurred while deleting the reminder"}), 500