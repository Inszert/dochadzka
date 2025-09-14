from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)

# Tvoj Koyeb connection string (prepíš postgres:// na postgresql://)
DATABASE_URL = "postgresql://koyeb-adm:npg_wzo2Xd3SAZYF@ep-cold-cloud-a2abkwup.eu-central-1.pg.koyeb.app/koyebdb"

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", DATABASE_URL)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# jednoduchá tabuľka na test
class Person(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)

@app.route("/")
def home():
    return "✅ Flask + Koyeb Postgres works!"

@app.route("/add/<name>")
def add_name(name):
    person = Person(name=name)
    db.session.add(person)
    db.session.commit()
    return f"Added {name} to DB!"

@app.route("/list")
def list_names():
    people = Person.query.all()
    return jsonify([p.name for p in people])

if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # vytvorí tabuľku, ak ešte neexistuje
    app.run(host="0.0.0.0", port=5000)
