"""Seed helper for local bootstrap."""

from datetime import date
from pathlib import Path
import sys

API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.core.database import Base, SessionLocal, engine
from app.services.alert_service import generate_alerts_from_signals
from app.services.anomaly_service import run_anomaly_detection
from app.services.document_ingestion_service import rebuild_document_index
from app.services.forecasting_service import run_forecasting
from app.services.seed_service import seed_operational_data, seed_reference_data
from app.services.seed_service import seed_documents


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        print("Seeding reference data...")
        print(seed_reference_data(db))
        print("Seeding operational data...")
        print(seed_operational_data(db))
        print(seed_documents(db))

        month = date.today().replace(day=1)
        run_forecasting(db, month)
        run_anomaly_detection(db, month)
        generate_alerts_from_signals(db, month)
        rebuild_document_index(db)
        db.commit()
        print("Seed complete")
    finally:
        db.close()
