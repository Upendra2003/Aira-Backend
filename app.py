from flask import Flask, request, jsonify
import time
import logging
from database.models import init_db
from scheduler import start_scheduler

app = Flask(__name__)

# Initialize MongoDB and collections - store the result
db_initialized = init_db(app)

# Only import blueprints after DB is initialized
if db_initialized:
    from routes.auth import auth_bp
    from routes.assessment import assessment_bp
    from routes.chat import chat_bp
    from routes.sentiment import sentiment_bp
    from routes.feedback import feedback_bp
    from routes.vision_board import visionboard_bp
    from routes.user import user_bp
    from routes.reminders import reminder_bp

    # Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(assessment_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(sentiment_bp)
    app.register_blueprint(feedback_bp)
    app.register_blueprint(visionboard_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(reminder_bp)


@app.route('/api/hello', methods=['GET'])
def hello():    
    name = request.args.get('name', 'World')
    return jsonify(message=f'Hello, {name}!')

if __name__ == "__main__":
    app.start_time = time.time()
    start_scheduler()
    logging.info("Starting AIRA Therapist application")
    app.run(  host='0.0.0.0', port=5000,debug=True) 