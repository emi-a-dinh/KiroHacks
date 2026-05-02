"""
Tests for authentication routes.
"""

import pytest
import json
from app import app, db
from models.user import User
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


def test_register_success(client):
    response = client.post(
        "/api/auth/register",
        data=json.dumps({
            "username": "alice",
            "email": "alice@example.com",
            "password": "securepass",
        }),
        content_type="application/json",
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["user"]["email"] == "alice@example.com"


def test_register_duplicate_email(client):
    payload = json.dumps({
        "username": "alice",
        "email": "alice@example.com",
        "password": "securepass",
    })
    client.post("/api/auth/register", data=payload, content_type="application/json")
    response = client.post("/api/auth/register", data=payload, content_type="application/json")
    assert response.status_code == 409


def test_register_short_password(client):
    response = client.post(
        "/api/auth/register",
        data=json.dumps({
            "username": "bob",
            "email": "bob@example.com",
            "password": "short",
        }),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_login_success(client):
    with app.app_context():
        user = User(
            username="alice",
            email="alice@example.com",
            password_hash=hash_password("securepass"),
        )
        db.session.add(user)
        db.session.commit()

    response = client.post(
        "/api/auth/login",
        data=json.dumps({"email": "alice@example.com", "password": "securepass"}),
        content_type="application/json",
    )
    assert response.status_code == 200


def test_login_wrong_password(client):
    with app.app_context():
        user = User(
            username="alice",
            email="alice@example.com",
            password_hash=hash_password("securepass"),
        )
        db.session.add(user)
        db.session.commit()

    response = client.post(
        "/api/auth/login",
        data=json.dumps({"email": "alice@example.com", "password": "wrongpass"}),
        content_type="application/json",
    )
    assert response.status_code == 401


def test_me_unauthenticated(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
