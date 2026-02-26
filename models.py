from extensions import db
from datetime import datetime

class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    surname = db.Column(db.String(50), nullable=False)

    def __repr__(self):
        return f'<Employee {self.name} {self.surname}>'

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=True)
    work_location = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='active')
    
    employee = db.relationship("Employee", backref="attendances")

    def hours_worked(self):
        if self.end_time:
            start = datetime.combine(self.date, self.start_time)
            end = datetime.combine(self.date, self.end_time)
            delta = end - start
            return round(delta.total_seconds() / 3600, 2)
        return 0

    def __repr__(self):
        return f'<Attendance {self.employee_id} {self.date}>'
    



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

# ------------------------
# Funkcia na získanie sviatkov zo Nager.Date API
# ------------------------
def get_slovak_holidays(year):
    url = f"https://date.nager.at/api/v3/PublicHolidays/{year}/SK"
    resp = requests.get(url)
    if resp.status_code != 200:
        return set()
    data = resp.json()
    return {datetime.strptime(h['date'], "%Y-%m-%d").date() for h in data}

# ------------------------
# Route
# ------------------------



@app.route("/", methods=["GET", "POST"])
def report():
    emp = {"name": "Dániel", "surname": "Szabó"}

    # filtrovanie dátumov
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    if start_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    else:
        start_date = date.today().replace(day=1)  # prvý deň mesiaca

    if end_date:
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
    else:
        end_date = date.today()  # dnešný deň

    # Simulované záznamy (v reálnom projekte by si ich bral z DB)
    records = []
    current = start_date
    while current <= end_date:
        records.append(Record(current.isoformat(), "08:00", "16:00", "Office"))
        current += timedelta(days=1)

    # sviatky
    holidays = get_slovak_holidays(start_date.year)

    # počítanie hodín
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
