from __future__ import annotations

from app.core.database import SessionLocal
from app.services.document_ingestion_service import rebuild_document_index


def main() -> None:
    db = SessionLocal()
    try:
        rebuild_document_index(db)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
