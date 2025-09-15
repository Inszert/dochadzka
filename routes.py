from flask import render_template, request, redirect, url_for
from app import app
from models import db, Employee, Attendance
from datetime import datetime

@app.route("/")
def home():
    return render_template("index.html")

# zvyšné route definície
@app.route("/employees")
def employees():
    employees = Employee.query.all()
    return render_template("employees.html", employees=employees)

@app.route("/attendance")
def attendance():
    records = Attendance.query.all()
    return render_template("attendance.html", records=records)
