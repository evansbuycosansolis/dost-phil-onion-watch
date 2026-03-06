"""Run APScheduler background worker."""

from pathlib import Path
import sys

API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.jobs.worker import main


if __name__ == "__main__":
    main()
