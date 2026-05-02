"""
Task Management API - Main application entry point.
"""

from flask import Flask
from database import db
from routes.tasks import tasks_bp
from routes.users import users_bp
from routes.auth import auth_bp

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///tasks.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "dev-secret-key-change-in-production"

db.init_app(app)

app.register_blueprint(tasks_bp, url_prefix="/api/tasks")
app.register_blueprint(users_bp, url_prefix="/api/users")
app.register_blueprint(auth_bp, url_prefix="/api/auth")

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)
