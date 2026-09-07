"""
Feature engineering for the AI prioritization model.

The model predicts a maintenance-priority class (Critical / High / Medium / Low)
from operational features. We derive an interpretable "priority index" as the
supervised target (a domain-weighted score binned into 4 classes) and then train
a gradient-boosted classifier to learn it. This mirrors real deployments where a
first policy is codified, then a model generalizes and is retrained on outcomes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Features used by the model (order matters for the trained artifact).
FEATURE_COLUMNS = [
    "severity",
    "asset_criticality",
    "overdue_days",
    "traffic_gmt",
    "estimated_duration_min",
    "requires_traffic_block",
    "gang_size",
    "sla_pressure",          # engineered
    "traffic_impact",        # engineered
    "dept_eng",              # one-hot department
    "dept_snt",
    "dept_trd",
]

PRIORITY_CLASSES = ["Low", "Medium", "High", "Critical"]

# Human-readable driver labels for explanations.
FEATURE_LABELS = {
    "severity": "defect severity",
    "asset_criticality": "asset criticality",
    "overdue_days": "days overdue against SLA",
    "traffic_gmt": "corridor train-traffic intensity",
    "estimated_duration_min": "estimated work duration",
    "requires_traffic_block": "requirement for a traffic block",
    "gang_size": "maintenance gang size",
    "sla_pressure": "SLA time pressure",
    "traffic_impact": "traffic-impact exposure",
    "dept_eng": "Engineering department",
    "dept_snt": "S&T department",
    "dept_trd": "Traction department",
}


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return a feature matrix (same index as df) from raw task columns."""
    f = pd.DataFrame(index=df.index)
    f["severity"] = df["severity"].astype(float)
    f["asset_criticality"] = df["asset_criticality"].astype(float)
    f["overdue_days"] = df["overdue_days"].astype(float)
    f["traffic_gmt"] = df["traffic_gmt"].astype(float)
    f["estimated_duration_min"] = df["estimated_duration_min"].astype(float)
    f["requires_traffic_block"] = df["requires_traffic_block"].astype(int)
    f["gang_size"] = df["gang_size"].astype(float)

    # Engineered: SLA pressure grows non-linearly once overdue.
    f["sla_pressure"] = np.log1p(df["overdue_days"].clip(lower=0)) * df["severity"]

    # Engineered: traffic impact combines corridor intensity and whether a block
    # (which stops trains) is required.
    f["traffic_impact"] = (df["traffic_gmt"] / 100.0) * (
        1.0 + df["requires_traffic_block"].astype(int)
    )

    dept = df["department"].astype(str)
    f["dept_eng"] = (dept == "ENG").astype(int)
    f["dept_snt"] = (dept == "SNT").astype(int)
    f["dept_trd"] = (dept == "TRD").astype(int)

    return f[FEATURE_COLUMNS]


def priority_index(df: pd.DataFrame) -> pd.Series:
    """Domain-weighted priority score in [0, 1] used to derive training labels."""
    sev = df["severity"] / 5.0
    crit = df["asset_criticality"] / 5.0
    overdue = np.clip(df["overdue_days"] / 30.0, 0, 1)
    traffic = df["traffic_gmt"] / 100.0
    block = df["requires_traffic_block"].astype(int)

    score = (
        0.32 * sev
        + 0.24 * crit
        + 0.20 * overdue
        + 0.16 * traffic
        + 0.08 * block
    )
    return score.clip(0, 1)


def label_from_index(score: pd.Series) -> pd.Series:
    """Bin the priority index into 4 ordered classes using fixed thresholds."""
    bins = [-0.001, 0.35, 0.55, 0.72, 1.001]
    return pd.cut(score, bins=bins, labels=PRIORITY_CLASSES).astype(str)
