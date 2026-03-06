import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_ROOT = Path(__file__).resolve().parent
TMP_DIR = TEST_ROOT / "tmp"
TMP_DIR.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("DATABASE_URL", f"sqlite+pysqlite:///{TMP_DIR / 'test.db'}")
os.environ.setdefault("FAISS_INDEX_PATH", str(TMP_DIR / "knowledge.index"))
os.environ.setdefault("FAISS_METADATA_PATH", str(TMP_DIR / "knowledge_meta.json"))
os.environ.setdefault("REPORTS_PATH", str(TMP_DIR / "reports"))
os.environ.setdefault("SECRET_KEY", "test-secret")

from app.core.database import Base, SessionLocal, engine
from app.main import app
from app.models import User
from app.services.alert_service import generate_alerts_from_signals
from app.services.anomaly_service import run_anomaly_detection
from app.services.document_ingestion_service import rebuild_document_index
from app.services.forecasting_service import run_forecasting
from app.services.seed_service import seed_documents, seed_operational_data, seed_reference_data


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_reference_data(db)
        seed_operational_data(db)
        seed_documents(db)
        from datetime import date

        month = date.today().replace(day=1)
        run_forecasting(db, month)
        run_anomaly_detection(db, month)
        generate_alerts_from_signals(db, month)
        rebuild_document_index(db)
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def client(setup_database):
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_headers(client: TestClient):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "super_admin@onionwatch.ph", "password": "ChangeMe123!"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def municipal_headers(client: TestClient):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "municipal_encoder@onionwatch.ph", "password": "ChangeMe123!"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
