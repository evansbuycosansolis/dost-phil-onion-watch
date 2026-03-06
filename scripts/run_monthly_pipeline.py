"""Run monthly pipeline job locally."""

from pathlib import Path
import sys

API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.core.database import SessionLocal
from app.jobs.monthly_pipeline import run_monthly_pipeline


if __name__ == "__main__":
    db = SessionLocal()
    try:
        job = run_monthly_pipeline(db)
        db.commit()
        print({"job_id": job.id, "status": job.status})
    finally:
        db.close()
