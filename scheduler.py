from apscheduler.schedulers.background import BackgroundScheduler
from database.models import get_database
from datetime import datetime,timedelta,timezone
import requests
from config import SYSTEM_SECRET
from zoneinfo import ZoneInfo

def check_inactive_chats():
    try:
        db = get_database()
        chat_collection = db["chat"]

        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        threshold_time_format = now - timedelta(minutes=30)
        threshold_time = threshold_time_format.strftime('%Y-%m-%d %H:%M:%S')
        print("🔍 Checking for inactive chats...",threshold_time)

        active_chats = chat_collection.find({"journal_end_flag": 0})

        for chat in active_chats:
            user_id = chat.get("user_id")
            messages = chat.get("messages", [])

            if not messages:
                continue

            last_message = messages[-1]
            last_message_time= last_message.get("created_at")

            if not last_message_time:
                continue

            if last_message_time < threshold_time:
                print(f"⏰ Ending journal for inactive user {user_id}...")

                try:
                    response = requests.post(
                        'http://127.0.0.1:5000/api/chat/end_journal',
                        headers={"System-Secret": SYSTEM_SECRET, "User-ID": user_id}
                    )

                    if response.ok:
                        print(f"✅ Successfully ended journal for user {user_id}")
                        print(f"Journal end response: {response.json()}")
                    else:
                        print(f"❌ Failed to end journal for user {user_id}: {response.text}")

                except Exception as e:
                    print(f"❌ Error sending end_journal request for user {user_id}: {e}")

    except Exception as e:
        print(f"❌ Scheduler error: {e}")

def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_inactive_chats, 'interval', minutes=10)
    scheduler.start()
    print("✅ Background Scheduler started.")
