from apscheduler.schedulers.background import BackgroundScheduler
from datetime import date, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Bratislava")


def _try_claim_job(job_type: str, ref_date: date) -> bool:
    """Insert a row into EmailLog. Returns True if this worker won the race."""
    from models import db, EmailLog
    from sqlalchemy.exc import IntegrityError

    try:
        db.session.add(EmailLog(
            job_type=job_type,
            reference_date=ref_date,
            sent_at=datetime.now(TZ),
        ))
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        return False


def _check_open_shifts(app):
    with app.app_context():
        today = datetime.now(TZ).date()
        if not _try_claim_job("open_shifts_alert", today):
            return

        from models import Attendance
        from mailer import send_open_shifts_alert

        open_records = (
            Attendance.query
            .filter_by(status="active")
            .join(Attendance.employee)
            .all()
        )
        if open_records:
            send_open_shifts_alert(open_records)
            print(f"[scheduler] Open-shifts alert sent – {len(open_records)} record(s)")
        else:
            print("[scheduler] No open shifts at 23:00, skipping alert")


def _send_monthly_report(app):
    with app.app_context():
        today = datetime.now(TZ).date()
        year = today.year if today.month > 1 else today.year - 1
        month = today.month - 1 if today.month > 1 else 12
        ref = date(year, month, 1)

        if not _try_claim_job("monthly_report", ref):
            return

        from mailer import send_monthly_report
        send_monthly_report(year, month)
        print(f"[scheduler] Monthly report sent for {year}-{month:02d}")


def start_scheduler(app):
    scheduler = BackgroundScheduler(timezone="Europe/Bratislava")

    scheduler.add_job(
        _check_open_shifts,
        trigger="cron",
        hour=23,
        minute=0,
        args=[app],
        id="open_shifts_alert",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _send_monthly_report,
        trigger="cron",
        day=2,
        hour=8,
        minute=0,
        args=[app],
        id="monthly_report",
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    print("[scheduler] Started – open-shifts alert at 23:00, monthly report on 2nd at 08:00")
    return scheduler