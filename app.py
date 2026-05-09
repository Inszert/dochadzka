import os
from flask import Flask
from extensions import db

app = Flask(__name__)

# -----------------------------
# Načítanie DB credentialov z ENV (Koyeb)
# -----------------------------
DB_HOST = os.environ.get("DATABASE_HOST")
DB_USER = os.environ.get("DATABASE_USER")
DB_PASSWORD = os.environ.get("DATABASE_PASSWORD")
DB_NAME = os.environ.get("DATABASE_NAME")

# Zostavenie SQLAlchemy URI so SSL pre Koyeb
if DB_HOST and DB_USER and DB_PASSWORD and DB_NAME:
    database_url = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}?sslmode=require"
else:
    database_url = "sqlite:///attendance.db"

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_size": 5,
    "max_overflow": 10
}

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "fallback_secret")

# Initialize database
db.init_app(app)

# Import models BEFORE create_all()
from models import Employee, Attendance, ShiftDedupLog

# Import routes AFTER models
from routes import *

# Toto sa spustí aj pri Gunicorn/Koyeb štarte
with app.app_context():
    try:
        db.create_all()
        print("Database tables checked/created successfully!")
    except Exception as e:
        print("Database initialization error:", e)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)