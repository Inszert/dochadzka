import os
from flask import Flask, render_template, request
from extensions import db
from datetime import datetime, date, timedelta
import requests

app = Flask(__name__)

# -----------------------------
# Načítanie DB credentialov z ENV (Koyeb)
# -----------------------------
DB_HOST = os.environ.get("DATABASE_HOST")
DB_USER = os.environ.get("DATABASE_USER")
DB_PASSWORD = os.environ.get("DATABASE_PASSWORD")
DB_NAME = os.environ.get("DATABASE_NAME")

if DB_HOST and DB_USER and DB_PASSWORD and DB_NAME:
    database_url = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}?sslmode=require"
else:
    database_url = "sqlite:///attendance.db"

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 10}
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "fallback_secret")

db.init_app(app)

from models import Employee, Attendance
from routes import *

# -----------------------------
# Simulovaný model pre report (ak chceš rýchlo testovať)
# -----------------------------
class Record:
    def __init__(self, date_str, start_time_str, end_time_str, work_location):
        self.date = datetime.strptime(date_str, "%Y-%m-%d").date()
        self.start_time = datetime.strptime(start_time_str, "%H:%M")
        self.end_time = datetime.strptime(end_time_str, "%H:%M") if end_time_str else None
        self.work_location = work_location

    def hours_worked(self):
        if self.end_time:
            delta = self.end_time - self.start_time
            return round(delta.total_seconds() / 3600, 2)
        return 0

# -----------------------------
# Funkcia na sviatky zo Slovenska cez Nager.Date API
# -----------------------------
def get_slovak_holidays(year):
    try:
        url = f"https://date.nager.at/api/v3/PublicHolidays/{year}/SK"
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
        return {datetime.strptime(h['date'], "%Y-%m-%d").date() for h in data}
    except Exception as e:
        print("Chyba pri načítaní sviatkov:", e)
        return set()

# -----------------------------
# Nová route /report
# -----------------------------
@app.route("/report", methods=["GET", "POST"])
def report():
    emp = {"name": "Dániel", "surname": "Szabó"}

    # filtrovanie dátumov
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    if start_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    else:
        start_date = date.today().replace(day=1)

    if end_date:
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
    else:
        end_date = date.today()

    # simulované záznamy (v reálnom projekte berieš z DB)
    records = []
    current = start_date
    while current <= end_date:
        records.append(Record(current.isoformat(), "08:00", "16:00", "Office"))
        current += timedelta(days=1)

    holidays = get_slovak_holidays(start_date.year)

    normal_hours = 0
    weekend_hours = 0
    holiday_hours = 0
    total_hours = 0

    for rec in records:
        hours = rec.hours_worked()
        total_hours += hours
        if rec.date in holidays:
            holiday_hours += hours
        elif rec.date.weekday() >= 5:
            weekend_hours += hours
        else:
            normal_hours += hours

    return render_template(
        "report.html",
        emp=emp,
        records=records,
        holidays=holidays,
        normal_hours=normal_hours,
        weekend_hours=weekend_hours,
        holiday_hours=holiday_hours,
        total_hours=total_hours
    )

# -----------------------------
# Spustenie aplikácie
# -----------------------------
if __name__ == "__main__":
    with app.app_context():
        try:
            db.create_all()
            print("Database tables created successfully!")
        except Exception as e:
            print("Database initialization error:", e)

    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)