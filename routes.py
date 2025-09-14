from flask import Flask, render_template, request, redirect
from models import db, Attendance
from datetime import datetime

def init_routes(app):
    @app.route("/", methods=["GET", "POST"])
    def form():
        if request.method == "POST":
            first_name = request.form["first_name"]
            last_name = request.form["last_name"]
            workplace = request.form["workplace"]
            date_str = request.form["date"]
            start_time_str = request.form["start_time"]
            end_time_str = request.form["end_time"]

            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            start_time_obj = datetime.strptime(start_time_str, "%H:%M").time()
            end_time_obj = datetime.strptime(end_time_str, "%H:%M").time()

            new_entry = Attendance(
                first_name=first_name,
                last_name=last_name,
                workplace=workplace,
                date=date_obj,
                start_time=start_time_obj,
                end_time=end_time_obj
            )
            db.session.add(new_entry)
            db.session.commit()
            return redirect("/attendance")

        return render_template("form.html")

    @app.route("/attendance")
    def attendance():
        all_entries = Attendance.query.order_by(Attendance.date).all()
        total_hours = sum(entry.worked_hours() for entry in all_entries)
        return render_template("attendance.html", entries=all_entries, total_hours=total_hours)
