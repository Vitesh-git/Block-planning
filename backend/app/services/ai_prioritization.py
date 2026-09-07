"""
AI prioritization service.

Loads the trained model and applies it to maintenance tasks, writing back a
priority label, a 0-1 score, and a human-readable explanation of *why* each task
received its priority. The explanation is generated from the model's global
feature importances combined with each task's own feature values, so it reflects
the actual drivers for that specific record (a lightweight, deterministic
contribution attribution suitable for operational transparency).
"""

from __future__ import annotations

import json
import os

import joblib
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.ml.features import (
    FEATURE_COLUMNS,
    FEATURE_LABELS,
    build_features,
    label_from_index,
    priority_index,
)
from app.ml.train_model import ENCODER_PATH, META_PATH, MODEL_PATH, train
from app.models import MaintenanceTask


class Prioritizer:
    def __init__(self):
        self.model = None
        self.encoder = None
        self.meta = {}
        self._load_or_train()

    def _load_or_train(self):
        if not (os.path.exists(MODEL_PATH) and os.path.exists(ENCODER_PATH)):
            train(verbose=False)
        self.model = joblib.load(MODEL_PATH)
        self.encoder = joblib.load(ENCODER_PATH)
        if os.path.exists(META_PATH):
            with open(META_PATH) as fh:
                self.meta = json.load(fh)

    # ------------------------------------------------------------------ #
    def predict_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return df augmented with priority_label, priority_score, explanation."""
        X = build_features(df)
        proba = self.model.predict_proba(X)
        pred_idx = proba.argmax(axis=1)
        labels = self.encoder.inverse_transform(pred_idx)

        # priority_score: confidence-weighted ordinal score in [0,1].
        class_order = {c: i for i, c in enumerate(self.encoder.classes_)}
        # map class to ordinal weight Low=0..Critical=1
        ordinal = {"Low": 0.15, "Medium": 0.45, "High": 0.72, "Critical": 0.95}
        scores = np.array([ordinal.get(lbl, 0.5) for lbl in labels])

        out = df.copy()
        out["priority_label"] = labels
        out["priority_score"] = scores.round(3)
        out["priority_explanation"] = [
            self._explain(df.iloc[i], X.iloc[i], labels[i]) for i in range(len(df))
        ]
        return out

    # ------------------------------------------------------------------ #
    def _explain(self, raw_row: pd.Series, feat_row: pd.Series, label: str) -> str:
        """Build a short natural-language explanation of the drivers."""
        importances = self.meta.get("feature_importances", {})
        if not importances:
            importances = {c: 1.0 for c in FEATURE_COLUMNS}

        # Contribution ~ global importance * normalized feature value.
        contributions = {}
        for col in FEATURE_COLUMNS:
            val = float(feat_row[col])
            # normalize each feature to roughly 0-1 for comparability
            norm = _normalize(col, val)
            contributions[col] = importances.get(col, 0.0) * norm

        top = sorted(contributions.items(), key=lambda kv: kv[1], reverse=True)[:3]
        drivers = []
        for col, _ in top:
            drivers.append(_phrase(col, raw_row))

        drivers = [d for d in drivers if d]
        driver_text = "; ".join(drivers) if drivers else "combined operational factors"
        return (
            f"Classified {label} primarily due to {driver_text}. "
            f"(Severity {int(raw_row['severity'])}/5, asset criticality "
            f"{int(raw_row['asset_criticality'])}/5, {int(raw_row['overdue_days'])} days overdue, "
            f"corridor traffic {int(raw_row['traffic_gmt'])} GMT.)"
        )

    # ------------------------------------------------------------------ #
    def apply_to_db(self, db: Session) -> dict:
        """Score every task in the DB and persist priorities."""
        tasks = db.query(MaintenanceTask).all()
        if not tasks:
            return {"updated": 0}

        df = pd.DataFrame(
            [
                {
                    "id": t.id,
                    "severity": t.severity,
                    "asset_criticality": t.asset_criticality,
                    "overdue_days": t.overdue_days,
                    "traffic_gmt": t.traffic_gmt,
                    "estimated_duration_min": t.estimated_duration_min,
                    "requires_traffic_block": t.requires_traffic_block,
                    "gang_size": t.gang_size,
                    "department": t.department,
                }
                for t in tasks
            ]
        )
        scored = self.predict_frame(df)
        by_id = {row["id"]: row for _, row in scored.iterrows()}
        for t in tasks:
            r = by_id[t.id]
            t.priority_label = r["priority_label"]
            t.priority_score = float(r["priority_score"])
            t.priority_explanation = r["priority_explanation"]
        db.commit()

        counts = scored["priority_label"].value_counts().to_dict()
        return {"updated": len(tasks), "distribution": counts}


def _normalize(col: str, val: float) -> float:
    ranges = {
        "severity": 5,
        "asset_criticality": 5,
        "overdue_days": 30,
        "traffic_gmt": 100,
        "estimated_duration_min": 360,
        "requires_traffic_block": 1,
        "gang_size": 14,
        "sla_pressure": 8,
        "traffic_impact": 2,
        "dept_eng": 1,
        "dept_snt": 1,
        "dept_trd": 1,
    }
    denom = ranges.get(col, 1) or 1
    return float(np.clip(val / denom, 0, 1))


def _phrase(col: str, raw: pd.Series) -> str:
    """Turn a driving feature into a readable clause given the record."""
    if col == "severity" and raw["severity"] >= 4:
        return f"high defect severity ({int(raw['severity'])}/5)"
    if col == "asset_criticality" and raw["asset_criticality"] >= 4:
        return f"critical asset ({int(raw['asset_criticality'])}/5)"
    if col in ("overdue_days", "sla_pressure") and raw["overdue_days"] > 0:
        return f"{int(raw['overdue_days'])} days overdue against SLA"
    if col in ("traffic_gmt", "traffic_impact") and raw["traffic_gmt"] >= 80:
        return f"heavily-trafficked corridor ({int(raw['traffic_gmt'])} GMT)"
    if col == "requires_traffic_block" and raw["requires_traffic_block"]:
        return "need for a line-blocking traffic block"
    if col.startswith("dept_"):
        return ""  # department alone isn't an interesting explanation
    return FEATURE_LABELS.get(col, col)


# module-level singleton (lazy)
_prioritizer: Prioritizer | None = None


def get_prioritizer() -> Prioritizer:
    global _prioritizer
    if _prioritizer is None:
        _prioritizer = Prioritizer()
    return _prioritizer
