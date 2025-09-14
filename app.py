import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# Získame URL databázy z environment premennej
database_url = os.environ.get("DATABASE_URL")

# SQLAlchemy 2.x vyžaduje prefix 'postgresql://', nie 'postgres://'
if database_url.startswith("postgres://"):
  database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "fallback_secret")

# Inicializácia SQLAlchemy
db = SQLAlchemy(app)

# Test route
@app.route("/")
def index():
  return "App is running!"

if __name__ == "__main__":
  app.run(host="0.0.0.0", port=8000)
