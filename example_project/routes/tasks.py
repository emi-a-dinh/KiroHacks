"""
Task CRUD routes.
"""

from flask import Blueprint, request, jsonify, session
from database import db
from models.task import Task, Tag, VALID_STATUSES, VALID_PRIORITIES
from datetime import datetime

tasks_bp = Blueprint("tasks", __name__)


def get_current_user_id():
    return session.get("user_id")


def require_auth():
    """Returns user_id or None. Caller must handle None."""
    return session.get("user_id")


@tasks_bp.route("/", methods=["GET"])
def list_tasks():
    user_id = require_auth()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    # ISSUE 4: No pagination. Returns ALL tasks for the user.
    # On large datasets this will be slow and return too much data.
    tasks = Task.query.filter_by(user_id=user_id).all()
    return jsonify([t.to_dict() for t in tasks]), 200


@tasks_bp.route("/", methods=["POST"])
def create_task():
    user_id = require_auth()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    title = data.get("title", "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400

    status = data.get("status", "todo")
    if status not in VALID_STATUSES:
        return jsonify({"error": f"status must be one of {VALID_STATUSES}"}), 400

    priority = data.get("priority", "medium")
    if priority not in VALID_PRIORITIES:
        return jsonify({"error": f"priority must be one of {VALID_PRIORITIES}"}), 400

    due_date = None
    if data.get("due_date"):
        try:
            due_date = datetime.fromisoformat(data["due_date"])
        except ValueError:
            return jsonify({"error": "due_date must be a valid ISO 8601 datetime"}), 400

    task = Task(
        title=title,
        description=data.get("description"),
        status=status,
        priority=priority,
        due_date=due_date,
        user_id=user_id,
    )

    # Handle tags
    tag_names = data.get("tags", [])
    for tag_name in tag_names:
        tag_name = tag_name.strip().lower()
        if not tag_name:
            continue
        tag = Tag.query.filter_by(name=tag_name).first()
        if not tag:
            tag = Tag(name=tag_name)
            db.session.add(tag)
        task.tags.append(tag)

    db.session.add(task)
    db.session.commit()

    return jsonify(task.to_dict()), 201


@tasks_bp.route("/<int:task_id>", methods=["GET"])
def get_task(task_id):
    user_id = require_auth()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    task = Task.query.get(task_id)

    # ISSUE 5: Authorization check is missing. Any logged-in user can read any task.
    # Should check: if task.user_id != user_id: return 403
    if not task:
        return jsonify({"error": "Task not found"}), 404

    return jsonify(task.to_dict()), 200


@tasks_bp.route("/<int:task_id>", methods=["PUT"])
def update_task(task_id):
    user_id = require_auth()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    task = Task.query.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    if task.user_id != user_id:
        return jsonify({"error": "Forbidden"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    if "title" in data:
        title = data["title"].strip()
        if not title:
            return jsonify({"error": "title cannot be empty"}), 400
        task.title = title

    if "description" in data:
        task.description = data["description"]

    if "status" in data:
        if data["status"] not in VALID_STATUSES:
            return jsonify({"error": f"status must be one of {VALID_STATUSES}"}), 400
        task.status = data["status"]

    if "priority" in data:
        if data["priority"] not in VALID_PRIORITIES:
            return jsonify({"error": f"priority must be one of {VALID_PRIORITIES}"}), 400
        task.priority = data["priority"]

    if "due_date" in data:
        if data["due_date"] is None:
            task.due_date = None
        else:
            try:
                task.due_date = datetime.fromisoformat(data["due_date"])
            except ValueError:
                return jsonify({"error": "due_date must be a valid ISO 8601 datetime"}), 400

    if "tags" in data:
        task.tags = []
        for tag_name in data["tags"]:
            tag_name = tag_name.strip().lower()
            if not tag_name:
                continue
            tag = Tag.query.filter_by(name=tag_name).first()
            if not tag:
                tag = Tag(name=tag_name)
                db.session.add(tag)
            task.tags.append(tag)

    # updated_at is NOT set here — see Issue 2 in models/task.py
    db.session.commit()
    return jsonify(task.to_dict()), 200


@tasks_bp.route("/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    user_id = require_auth()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    task = Task.query.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    if task.user_id != user_id:
        return jsonify({"error": "Forbidden"}), 403

    db.session.delete(task)
    db.session.commit()
    return jsonify({"message": "Task deleted"}), 200


@tasks_bp.route("/search", methods=["GET"])
def search_tasks():
    # ISSUE 6: Search is not implemented — returns 501 stub.
    return jsonify({"error": "Search not yet implemented"}), 501


@tasks_bp.route("/stats", methods=["GET"])
def task_stats():
    user_id = require_auth()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    # ISSUE 7: N+1 query problem. Loads all tasks into Python then counts in memory.
    # Should use db.session.query(Task.status, db.func.count()).group_by(Task.status)
    tasks = Task.query.filter_by(user_id=user_id).all()

    stats = {
        "total": len(tasks),
        "by_status": {},
        "by_priority": {},
        "overdue": 0,
    }

    now = datetime.utcnow()
    for task in tasks:
        stats["by_status"][task.status] = stats["by_status"].get(task.status, 0) + 1
        stats["by_priority"][task.priority] = stats["by_priority"].get(task.priority, 0) + 1
        if task.due_date and task.due_date < now and task.status != "done":
            stats["overdue"] += 1

    return jsonify(stats), 200
