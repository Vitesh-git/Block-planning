"""
Smoke tests for the end-to-end pipeline against an in-memory SQLite DB.

Run:  pytest -q     (from backend/)
"""

import pandas as pd

from app.ml.features import build_features, label_from_index, priority_index
from app.services import data_integration as di


def test_normalize_feeds_merges_three_sources():
    merged = di.normalize_feeds()
    assert set(merged["source_system"].unique()) == {"TMS", "SMMS", "TDMS"}
    assert set(merged["department"].unique()) == {"ENG", "SNT", "TRD"}
    assert merged["source_id"].notna().all()


def test_feature_matrix_shape():
    merged = di.normalize_feeds().head(50)
    X = build_features(merged)
    assert len(X) == 50
    # all engineered/one-hot columns present, no NaNs
    assert not X.isna().any().any()


def test_priority_labels_are_ordered_classes():
    merged = di.normalize_feeds()
    labels = label_from_index(priority_index(merged))
    assert set(labels.unique()).issubset({"Critical", "High", "Medium", "Low"})


def test_optimizer_produces_blocks():
    """Full pipeline on the configured DB should yield a feasible plan."""
    from app.core.database import SessionLocal, init_db
    from app.models import (
        BlockTask, Corridor, MaintenanceBlock, MaintenanceTask,
        MaintenanceWindow, Station, Train,
    )
    from app.services.ai_prioritization import Prioritizer
    from app.services.optimization import run_and_persist

    init_db()
    db = SessionLocal()
    try:
        # clean slate
        for model in (BlockTask, MaintenanceBlock, MaintenanceTask,
                      MaintenanceWindow, Train, Station, Corridor):
            db.query(model).delete()
        db.commit()

        merged = di.normalize_feeds()
        di.load_reference_data(db)
        di.load_tasks(db, merged)
        Prioritizer().apply_to_db(db)
        stats = run_and_persist(db, time_limit_s=5)
        assert stats["blocks_opened"] >= 1
        assert stats["tasks_scheduled"] >= 1
    finally:
        db.close()
