from __future__ import annotations

from datetime import date

from app.core.database import SessionLocal
from app.services.alert_service import generate_alerts_from_signals


def main() -> None:
    db = SessionLocal()
    try:
        month = date.today().replace(day=1)
        generate_alerts_from_signals(db, month)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
