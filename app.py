from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

app = Flask(__name__)

DATABASE_URL = "postgresql://koyeb-adm:npg_wzo2Xd3SAZYF@ep-cold-cloud-a2abkwup.eu-central-1.pg.koyeb.app/koyebdb"
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", DATABASE_URL)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    position = db.Column(db.String(64), nullable=True)
    attendance = db.relationship("Attendance", backref="employee", lazy=True)

class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    attendance = db.relationship("Attendance", backref="location", lazy=True)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey("location.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    check_in = db.Column(db.Time, nullable=False)
    check_out = db.Column(db.Time, nullable=True)
    hours_worked = db.Column(db.Float, nullable=True)

# Routes
@app.route("/")
def home():
    return "✅ Attendance system with locations working!"

# Add employee
@app.route("/employee/add", methods=["POST"])
def add_employee():
    data = request.json
    emp = Employee(name=data["name"], position=data.get("position"))
    db.session.add(emp)
    db.session.commit()
    return jsonify({"id": emp.id, "name": emp.name})

# Add location
@app.route("/location/add", methods=["POST"])
def add_location():
    data = request.json
    loc = Location(name=data["name"])
    db.session.add(loc)
    db.session.commit()
    return jsonify({"id": loc.id, "name": loc.name})

# Add attendance
@app.route("/attendance/add", methods=["POST"])
def add_attendance():
    data = request.json
    check_in = datetime.strptime(data["check_in"], "%H:%M").time()
    check_out = datetime.strptime(data["check_out"], "%H:%M").time()
    hours = (datetime.combine(datetime.min, check_out) - datetime.combine(datetime.min, check_in)).seconds / 3600
    att = Attendance(
        employee_id=data["employee_id"],
        location_id=data["location_id"],
        date=datetime.strptime(data["date"], "%Y-%m-%d").date(),
        check_in=check_in,
        check_out=check_out,
        hours_worked=hours
    )
    db.session.add(att)
    db.session.commit()
    return jsonify({"id": att.id, "hours_worked": att.hours_worked})

# List all attendance (for reporting)
@app.route("/attendance/list")
def list_attendance():
    all_att = Attendance.query.all()
    result = []
    for a in all_att:
        result.append({
            "employee": a.employee.name,
            "position": a.employee.position,
            "location": a.location.name,
            "date": a.date.isoformat(),
            "check_in": a.check_in.strftime("%H:%M"),
            "check_out": a.check_out.strftime("%H:%M"),
            "hours_worked": a.hours_worked
        })
    return jsonify(result)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000)
