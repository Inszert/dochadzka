import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# DATABASE_URL z prostredia (Heroku/Koyeb)
database_url = os.environ.get("DATABASE_URL", "sqlite:///test.db")

# psycopg3 prefix pre SQLAlchemy
if database_url.startswith("postgres://"):
  database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# Jednoduchý model pre test
class User(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  name = db.Column(db.String(50), nullable=False)

@app.route("/")
def index():
  return "Hello, world!"

if __name__ == "__main__":
  app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
