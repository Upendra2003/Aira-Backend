from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from datetime import datetime, timedelta
from database.models import users_collection, get_current_time, sessions_collection
from functions.auth_functions import (
    generate_token, 
    decode_token, 
    verify_jwt_token,
    send_welcome_email,
)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# Routes
@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.json
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")
    if not all([username, email, password]):
        return jsonify({"error": "All fields are required"}), 400
    if users_collection.find_one({"email": email}):
        return jsonify({"error": "User already exists"}), 409
    hashed_password = generate_password_hash(password)
    current_time=get_current_time()
    user_data = {
        "username": username,
        "email": email,
        "password": hashed_password,
        "created_at": current_time
    }
    result = users_collection.insert_one(user_data)
    send_welcome_email(email, username)  # Send email after registration
    return jsonify({"username": username,"email": email, "message": "User registered successfully"}), 201

#Login Route
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    # Validate input
    if not all([email, password]):
        return jsonify({"error": "Email and password are required"}), 400

    # Find user in users_collection
    user = users_collection.find_one({"email": email})
    if not user or not check_password_hash(user["password"], password):
        return jsonify({"error": "Invalid credentials"}), 401

    # Create new session
    session_id = str(uuid.uuid4())
    session_expires_at = datetime.utcnow() + timedelta(days=7)
    session_data = {
        "user_id": str(user["_id"]),
        "session_id": session_id,
        "login_time": datetime.utcnow(),
        "expires_at": session_expires_at,
        "active": True
    }
    sessions_collection.insert_one(session_data)

    # Generate access token
    access_token = generate_token(user["_id"], session_id, timedelta(minutes=15))
    
    response_data = {
        "message": "Login successful",
        "access_token": access_token,
        "refresh_token": session_id,
        "user_id": str(user["_id"]),
        "user": {"username": user["username"], "email": user["email"]},
        "assessment_flag": user.get("assessment_flag", 0)
    }

    return jsonify(response_data), 200

# Reset Password Route
@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.json
    email = data.get("email")
    new_password = data.get("new_password")

    if not all([email, new_password]):
        return jsonify({"error": "Email and new password are required"}), 400

    user = users_collection.find_one({"email": email})
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Update password
    hashed_password = generate_password_hash(new_password)
    users_collection.update_one(
        {"email": email},
        {"$set": {"password": hashed_password}}
    )

    # Invalidate all existing sessions for security
    sessions_collection.update_many(
        {"user_id": str(user["_id"]), "active": True},
        {"$set": {"active": False}}
    )

    return jsonify({"message": "Password reset successfully"}), 200

#Refresh Token Route
@auth_bp.route("/refresh", methods=["POST"])
def refresh():
    data = request.json
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        return jsonify({"error": "Refresh token is required"}), 400
    session = sessions_collection.find_one({"session_id": refresh_token, "active": True})
    if not session or session["expires_at"] < datetime.utcnow():
        return jsonify({"error": "Invalid or expired refresh token"}), 401
    access_token = generate_token(session["user_id"], session["session_id"], timedelta(minutes=15))
    return jsonify({"access_token": access_token}), 200

#Logout Route
@auth_bp.route("/logout", methods=["POST"])
def logout():
    auth_header = request.headers.get("Authorization")
    if not auth_header or "Bearer" not in auth_header:
        return jsonify({"error": "Authorization header is missing or invalid"}), 400
    token = auth_header.split("Bearer ")[1]
    decoded_token = decode_token(token, verify_exp=False)
    if not decoded_token:
        return jsonify({"error": "Invalid token"}), 401
    session_id = decoded_token.get("session_id")
    sessions_collection.delete_one({"session_id": session_id})
    return jsonify({"message": "Logout successful"}), 200