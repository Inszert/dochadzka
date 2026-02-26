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
    # fallback na lokálnu SQLite
    database_url = "sqlite:///attendance.db"

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Connection pool a ping pre stabilitu spojenia
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,   # automaticky re-connectne ak DB uzavrie spojenie
    "pool_size": 5,
    "max_overflow": 10
}

# SECRET_KEY z env alebo fallback
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "fallback_secret")

# Initialize the database with the app
db.init_app(app)

# Import models AFTER initializing db but BEFORE create_all()
from models import Employee, Attendance

# Import routes after models
from routes import routes
app.register_blueprint(routes)
if __name__ == "__main__":
    with app.app_context():
        try:
            db.create_all()
            print("Database tables created successfully!")
        except Exception as e:
            print("Database initialization error:", e)

    # Použitie portu z ENV, fallback na 8000
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
