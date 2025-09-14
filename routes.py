from flask import Flask, request, jsonify
from models import db, Attendance
from datetime import datetime

def init_routes(app):
    # Pridanie dochádzky
    @app.route("/api/attendance", methods=["POST"])
    def add_attendance():
        data = request.json
        try:
            date_obj = datetime.strptime(data["date"], "%Y-%m-%d").date()
            start_time_obj = datetime.strptime(data["start_time"], "%H:%M").time()
            end_time_obj = datetime.strptime(data["end_time"], "%H:%M").time()

            new_entry = Attendance(
                first_name=data["first_name"],
                last_name=data["last_name"],
                workplace=data["workplace"],
                date=date_obj,
                start_time=start_time_obj,
                end_time=end_time_obj
            )
            db.session.add(new_entry)
            db.session.commit()
            return jsonify({"message": "Attendance added"}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    # Získanie mesačnej tabuľky (filter podľa mesiaca)
    @app.route("/api/attendance", methods=["GET"])
    def get_attendance():
        month = request.args.get("month")  # "2025-09"
        if not month:
            return jsonify({"error": "Month parameter required (YYYY-MM)"}), 400

        try:
            year, mon = map(int, month.split("-"))
        except:
            return jsonify({"error": "Invalid month format"}), 400

        entries = Attendance.query.filter(
            db.extract("year", Attendance.date) == year,
            db.extract("month", Attendance.date) == mon
        ).order_by(Attendance.date).all()

        table = []
        total_hours = 0
        for e in entries:
            hours = e.worked_hours()
            total_hours += hours
            table.append({
                "first_name": e.first_name,
                "last_name": e.last_name,
                "workplace": e.workplace,
                "date": e.date.strftime("%Y-%m-%d"),
                "start_time": e.start_time.strftime("%H:%M"),
                "end_time": e.end_time.strftime("%H:%M"),
                "hours": round(hours, 2)
            })

        return jsonify({
            "month": month,
            "total_hours": round(total_hours, 2),
            "entries": table
        })
