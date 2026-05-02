"""
User management routes.
"""

from flask import Blueprint, request, jsonify, session
from database import db
from models.user import User

users_bp = Blueprint("users", __name__)


@users_bp.route("/<int:user_id>", methods=["GET"])
def get_user(user_id):
    # ISSUE 8: No authentication check. Anyone can fetch any user's profile.
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user.to_dict()), 200


@users_bp.route("/<int:user_id>", methods=["PUT"])
def update_user(user_id):
    current_user_id = session.get("user_id")
    if not current_user_id:
        return jsonify({"error": "Not authenticated"}), 401

    if current_user_id != user_id:
        return jsonify({"error": "Forbidden"}), 403

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    if "username" in data:
        username = data["username"].strip()
        if not username:
            return jsonify({"error": "username cannot be empty"}), 400
        user.username = username

    if "email" in data:
        email = data["email"].strip().lower()
        existing = User.query.filter_by(email=email).first()
        if existing and existing.id != user_id:
            return jsonify({"error": "Email already in use"}), 409
        user.email = email

    db.session.commit()
    return jsonify(user.to_dict()), 200


@users_bp.route("/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    current_user_id = session.get("user_id")
    if not current_user_id:
        return jsonify({"error": "Not authenticated"}), 401

    if current_user_id != user_id:
        return jsonify({"error": "Forbidden"}), 403

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "User deleted"}), 200


@users_bp.route("/<int:user_id>/tasks", methods=["GET"])
def get_user_tasks(user_id):
    current_user_id = session.get("user_id")
    if not current_user_id:
        return jsonify({"error": "Not authenticated"}), 401

    if current_user_id != user_id:
        return jsonify({"error": "Forbidden"}), 403

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Same pagination issue as tasks list — no limit/offset
    tasks = user.tasks
    return jsonify([t.to_dict() for t in tasks]), 200
