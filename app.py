import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)

# Databáza
database_url = os.environ.get("DATABASE_URL")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "fallback_secret")

db = SQLAlchemy(app)

# Modely
class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    surname = db.Column(db.String(50), nullable=False)
    workplace = db.Column(db.String(100), nullable=False)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey("employee.id"), nullable=False)
    employee = db.relationship("Employee", backref=db.backref("attendances", lazy=True))

    def hours_worked(self):
        delta = datetime.combine(self.date, self.end_time) - datetime.combine(self.date, self.start_time)
        return round(delta.total_seconds() / 3600, 2)

# ROUTES
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/employees", methods=["GET", "POST"])
def employees():
    if request.method == "POST":
        name = request.form["name"]
        surname = request.form["surname"]
        workplace = request.form["workplace"]
        new_emp = Employee(name=name, surname=surname, workplace=workplace)
        db.session.add(new_emp)
        db.session.commit()
        return redirect(url_for("employees"))
    employees = Employee.query.all()
    return render_template("employees.html", employees=employees)

@app.route("/attendance", methods=["GET", "POST"])
def attendance():
    employees = Employee.query.all()
    if request.method == "POST":
        emp_id = request.form["employee_id"]
        date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
        start = datetime.strptime(request.form["start_time"], "%H:%M").time()
        end = datetime.strptime(request.form["end_time"], "%H:%M").time()
        record = Attendance(date=date, start_time=start, end_time=end, employee_id=emp_id)
        db.session.add(record)
        db.session.commit()
        return redirect(url_for("attendance"))
    records = Attendance.query.all()
    return render_template("attendance.html", employees=employees, records=records)

@app.route("/report")
def report():
    records = Attendance.query.all()
    total_hours = sum(r.hours_worked() for r in records)
    return render_template("report.html", records=records, total_hours=total_hours)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=8000)
