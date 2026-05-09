from extensions import db
from datetime import datetime

class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    surname = db.Column(db.String(50), nullable=False)

    def __repr__(self):
        return f'<Employee {self.name} {self.surname}>'
    

class ShiftDedupLog(db.Model):
    __tablename__ = "shift_dedup_log"

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(50), nullable=False)
    name_key = db.Column(db.String(150), nullable=False, index=True)
    event_time = db.Column(db.DateTime(timezone=True), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False)    

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