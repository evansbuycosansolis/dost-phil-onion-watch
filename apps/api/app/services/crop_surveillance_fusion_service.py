from __future__ import annotations

from sqlalchemy.orm import Session


def run_fusion_refresh(db: Session, *, correlation_id: str | None = None) -> dict:
    """Phase B stub.

    Phase D will fuse optical + radar + historical context into AOI-level signals.
    """

    _ = correlation_id
    _ = db
    return {"status": "not_implemented"}
