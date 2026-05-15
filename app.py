import os
import time
from flask import Flask, jsonify, request
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool
from extensions import db

app = Flask(__name__)

DB_HOST = os.environ.get("DATABASE_HOST")
DB_USER = os.environ.get("DATABASE_USER")
DB_PASSWORD = os.environ.get("DATABASE_PASSWORD")
DB_NAME = os.environ.get("DATABASE_NAME")

if DB_HOST and DB_USER and DB_PASSWORD and DB_NAME:
    database_url = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}?sslmode=require"
else:
    database_url = "sqlite:///attendance.db"

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "poolclass": NullPool,
}
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "fallback_secret")

db.init_app(app)

from models import Employee, Attendance, ShiftDedupLog, EmailLog
from routes import *

_IS_POSTGRES = database_url.startswith("postgresql")


@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()


@app.before_request
def ensure_db_connection():
    if not _IS_POSTGRES or request.endpoint == "static":
        return
    for attempt in range(4):
        try:
            db.session.execute(text("SELECT 1"))
            return
        except OperationalError:
            db.session.remove()
            if attempt == 3:
                return jsonify({"error": "Database unavailable, please retry"}), 503
            time.sleep(2 ** attempt)  # 1, 2, 4s before attempts 2, 3, 4


def _create_tables_with_retry():
    for attempt in range(4):
        try:
            db.create_all()
            print("Database tables checked/created successfully!")
            return
        except OperationalError as e:
            if attempt == 3:
                print("Database initialization error after retries:", e)
                return
            wait = 2 ** attempt
            print(f"DB not ready, retrying in {wait}s... (attempt {attempt + 1}/4)")
            time.sleep(wait)


with app.app_context():
    _create_tables_with_retry()

from scheduler import start_scheduler
start_scheduler(app)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)