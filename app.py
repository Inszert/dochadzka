from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)

# Použitie DATABASE_URL z prostredia (Heroku/Koyeb)
database_url = os.environ.get("DATABASE_URL", "sqlite:///test.db")

# Pre psycopg3 je potrebné upraviť URL prefix
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# jednoduchý model
class User(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  name = db.Column(db.String(50), nullable=False)

@app.route("/")
def index():
  return "Hello World!"

if __name__ == "__main__":
    # Vytvorenie DB pri lokálnom teste
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=8000)
