import os
from flask import Flask
from extensions import db

app = Flask(__name__)

# Database configuration
database_url = os.environ.get("DATABASE_URL")
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "fallback_secret")

# Initialize the database with the app
db.init_app(app)

# Import models AFTER initializing db but BEFORE create_all()
from models import Employee, Attendance

# Import routes after models
from routes import *

if __name__ == "__main__":
    with app.app_context():
        try:
            db.create_all()
            print("Database tables created successfully!")
        except Exception as e:
            print("Database initialization error:", e)

    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
