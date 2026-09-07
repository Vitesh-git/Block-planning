"""
End-to-end seed / bootstrap script.

Runs the full offline pipeline so the database is ready before the API starts:
  1. (optional) regenerate synthetic data
  2. create tables
  3. load + normalize the source feeds
  4. train the AI prioritization model and score every task
  5. run the OR-Tools optimizer and persist the block plan

Usage:
    python -m scripts.seed_db            # from backend/
    python scripts/seed_db.py --regen    # regenerate synthetic data first
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

# allow running as a plain script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal, init_db  # noqa: E402
from app.models import (  # noqa: E402
    BlockTask,
    Corridor,
    MaintenanceBlock,
    MaintenanceTask,
    MaintenanceWindow,
    Station,
    Train,
)
from app.services import data_integration as di  # noqa: E402
from app.services.ai_prioritization import get_prioritizer  # noqa: E402
from app.services.optimization import run_and_persist  # noqa: E402
from app.ml.train_model import train  # noqa: E402


def regen_data():
    gen = os.path.join(os.path.dirname(__file__), "..", "data", "generate_synthetic_data.py")
    subprocess.check_call([sys.executable, gen])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regen", action="store_true", help="regenerate synthetic data")
    ap.add_argument("--time-limit", type=int, default=None)
    args = ap.parse_args()

    if args.regen:
        print("[seed] regenerating synthetic data...")
        regen_data()

    print("[seed] creating tables...")
    init_db()

    db = SessionLocal()
    try:
        print("[seed] clearing existing rows...")
        for model in (BlockTask, MaintenanceBlock, MaintenanceTask,
                      MaintenanceWindow, Train, Station, Corridor):
            db.query(model).delete()
        db.commit()

        print("[seed] loading + normalizing source feeds...")
        merged = di.normalize_feeds()
        di.load_reference_data(db)
        di.load_tasks(db, merged)
        print("       ", di.integration_summary(merged))

        print("[seed] training AI prioritization model...")
        meta = train(verbose=True)

        print("[seed] scoring tasks with the model...")
        prio = get_prioritizer().apply_to_db(db)
        print("       priority distribution:", prio["distribution"])

        print("[seed] running OR-Tools block optimizer...")
        stats = run_and_persist(db, time_limit_s=args.time_limit)
        print("       ", stats)

        print("[seed] DONE.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
