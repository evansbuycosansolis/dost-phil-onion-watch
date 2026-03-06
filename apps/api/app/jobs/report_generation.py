from __future__ import annotations

from datetime import date

from app.core.database import SessionLocal
from app.services.report_service import generate_report


REPORT_CATEGORIES = [
    "provincial_exec_summary",
    "municipality_summary",
    "warehouse_utilization",
    "price_trend",
    "alert_digest",
]


def main() -> None:
    db = SessionLocal()
    try:
        month = date.today().replace(day=1)
        for category in REPORT_CATEGORIES:
            generate_report(db, category, month)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
