"""
Tests for task routes.

ISSUE 9: Test coverage is incomplete.
- create_task, update_task, delete_task have no tests.
- The authorization bypass in get_task (Issue 5) has no test catching it.
- Stats endpoint N+1 query has no performance test.
"""

import pytest
import json
from app import app, db
from models.user import User
from models.task import Task
from routes.auth import hash_password


@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SECRET_KEY"] = "test-secret"

    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.drop_all()


@pytest.fixture
def auth_client(client):
    """A client with a logged-in user."""
    with app.app_context():
        user = User(
            username="testuser",
            email="test@example.com",
            password_hash=hash_password("password123"),
        )
        db.session.add(user)
        db.session.commit()

    client.post(
        "/api/auth/login",
        data=json.dumps({"email": "test@example.com", "password": "password123"}),
        content_type="application/json",
    )
    return client


def test_list_tasks_unauthenticated(client):
    response = client.get("/api/tasks/")
    assert response.status_code == 401


def test_list_tasks_empty(auth_client):
    response = auth_client.get("/api/tasks/")
    assert response.status_code == 200
    data = response.get_json()
    assert data["items"] == []
    assert "pagination" in data
    assert data["pagination"]["total"] == 0


def test_get_task_not_found(auth_client):
    response = auth_client.get("/api/tasks/9999")
    assert response.status_code == 404


# MISSING: test_create_task
# MISSING: test_create_task_invalid_status
# MISSING: test_update_task
# MISSING: test_delete_task
# MISSING: test_get_task_wrong_user  <-- would catch Issue 5
# MISSING: test_search_tasks
# MISSING: test_task_stats
