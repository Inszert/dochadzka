from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)

# Koyeb poskytne DATABASE_URL ako env var, alebo vlož priamo
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://koyeb-adm:npg_wzo2Xd3SAZYF@ep-cold-cloud-a2abkwup.eu-central-1.pg.koyeb.app/koyebdb")
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

class Test(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)

@app.route("/")
def home():
    return "✅ Flask on Koyeb + Postgres connected!"

@app.route("/add/<name>")
def add_name(name):
    row = Test(name=name)
    db.session.add(row)
    db.session.commit()
    return f"Inserted {name}"

@app.route("/list")
def list_names():
    rows = Test.query.all()
    return jsonify([r.name for r in rows])

if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # vytvorí tabuľku pri prvom deployi
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
