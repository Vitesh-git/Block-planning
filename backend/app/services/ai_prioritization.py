"""
AI maintenance-priority service.

Applies the trained model to maintenance tasks and writes back:

  * ``priority_label``   — Critical / High / Medium / Low
  * ``priority_score``   — 0-1 *expected* priority (probability-weighted), so the
                           optimizer can rank tasks inside the same class
  * ``priority_factors`` — JSON list of the drivers for THIS task, with signed
                           impact on the score (local, model-based attribution)
  * ``priority_explanation`` — the same drivers as a plain-English sentence

Local attribution is done by marginal occlusion: each factor group is swapped
for values taken from a small fixed background sample of real tasks, and the
drop in the model's expected score is that factor's impact on THIS task. It
uses the model itself, is deterministic, and needs no extra library (no SHAP /
LIME dependency).

A transparent safety rule sits on top of the model: a severity-5 defect on a
critical asset (criticality >= 4) is never ranked below High. When the rule
fires the explanation says so.

Controller overrides are respected: re-scoring updates the AI recommendation
(``ai_priority_label``) but never silently replaces a human decision.
"""

from __future__ import annotations

import json
import logging
import os

import joblib
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.ml.features import FEATURE_COLUMNS, build_features
from app.ml.train_model import ALGORITHM, MODEL_PATH, read_meta, train
from app.models import MaintenanceTask

log = logging.getLogger(__name__)

# Ordinal value of each class on the 0-1 score scale (shared with overrides).
ORDINAL = {"Low": 0.15, "Medium": 0.45, "High": 0.72, "Critical": 0.95}

# Factor groups used for explanations: engineered features move together with
# the raw feature they are derived from.
FACTOR_GROUPS = {
    "severity": ["severity"],
    "asset_criticality": ["asset_criticality"],
    "overdue": ["overdue_days", "sla_pressure"],
    "traffic": ["traffic_gmt", "traffic_impact"],
    "block": ["requires_traffic_block"],
    "duration": ["estimated_duration_min"],
    "gang": ["gang_size"],
    "department": ["dept_eng", "dept_snt", "dept_trd"],
}
FACTOR_TITLES = {
    "severity": "Defect severity",
    "asset_criticality": "Asset criticality",
    "overdue": "Overdue vs SLA",
    "traffic": "Corridor traffic",
    "block": "Needs traffic block",
    "duration": "Work duration",
    "gang": "Gang size",
    "department": "Department",
}
SAFETY_RULE = "Safety rule: a severity-5 defect on a critical asset is never ranked below High."


class Prioritizer:
    def __init__(self):
        self.model = None
        self.meta: dict = {}
        self._load_or_train()

    def _load_or_train(self):
        meta = read_meta()
        stale = (
            not os.path.exists(MODEL_PATH)
            or meta.get("algorithm") != ALGORITHM
            or meta.get("features") != FEATURE_COLUMNS
        )
        if not stale:
            try:
                self.model = joblib.load(MODEL_PATH)
                # guard against an older artifact (e.g. XGBoost with integer classes)
                if not {str(c) for c in getattr(self.model, "classes_", [])} <= set(ORDINAL):
                    raise ValueError("unexpected model classes")
            except Exception:  # old / foreign artifact: retrain rather than mis-score
                log.warning("priority model artifact is stale or unreadable; retraining")
                stale = True
        if stale:
            train(verbose=False)
            self.model = joblib.load(MODEL_PATH)
        self.meta = read_meta()

    # ------------------------------------------------------------------ #
    def _expected(self, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        proba = self.model.predict_proba(X)
        weights = np.array([ORDINAL.get(str(c), 0.5) for c in self.model.classes_])
        return proba, proba @ weights

    def predict_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return df augmented with label, score, factors and explanation."""
        X = build_features(df)
        proba, score = self._expected(X)
        classes = np.array([str(c) for c in self.model.classes_])
        labels = classes[proba.argmax(axis=1)]
        confidence = proba.max(axis=1)

        # Marginal occlusion per factor group, vectorised over all rows:
        # impact = score - mean_b score(x with group := background_b).
        bg = pd.DataFrame(self.meta.get("explain_background") or X.sample(n=min(24, len(X)), random_state=7))
        n, k = len(X), len(bg)
        tiled = pd.DataFrame(np.repeat(X.to_numpy(), k, axis=0), columns=X.columns)
        bg_tiled = pd.DataFrame(np.tile(bg[X.columns].to_numpy(), (n, 1)), columns=X.columns)
        impacts = {}
        for group, cols in FACTOR_GROUPS.items():
            Xo = tiled.copy()
            Xo[cols] = bg_tiled[cols].to_numpy()
            impacts[group] = score - self._expected(Xo)[1].reshape(n, k).mean(axis=1)

        out = df.copy()
        final_labels, final_scores, factors, texts = [], [], [], []
        for i in range(len(df)):
            raw = df.iloc[i]
            label, s = str(labels[i]), float(score[i])
            safety = False
            if int(raw["severity"]) >= 5 and int(raw["asset_criticality"]) >= 4 and label in ("Low", "Medium"):
                label, s, safety = "High", max(s, ORDINAL["High"]), True
            # keep the 4 strongest drivers that actually move the score
            fl = sorted(
                (
                    {"factor": FACTOR_TITLES[g], "value": _value_text(g, raw),
                     "impact": round(float(impacts[g][i]), 3)}
                    for g in FACTOR_GROUPS
                    if abs(float(impacts[g][i])) >= 0.005
                ),
                key=lambda f: -abs(f["impact"]),
            )[:4]
            final_labels.append(label)
            final_scores.append(round(float(np.clip(s, 0, 1)), 3))
            factors.append(fl)
            texts.append(_explain(raw, label, final_scores[-1], float(confidence[i]), fl, safety))

        out["priority_label"] = final_labels
        out["priority_score"] = final_scores
        out["priority_factors"] = factors
        out["priority_explanation"] = texts
        return out

    # ------------------------------------------------------------------ #
    def apply_to_db(self, db: Session, tasks: list[MaintenanceTask] | None = None) -> dict:
        """Score tasks (default: every task in the DB) and persist priorities."""
        if tasks is None:
            tasks = db.query(MaintenanceTask).all()
        if not tasks:
            return {"updated": 0, "distribution": {}}

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
        kept = 0
        for t in tasks:
            r = by_id[t.id]
            t.ai_priority_label = r["priority_label"]
            t.priority_factors = json.dumps(r["priority_factors"], separators=(",", ":"))
            if (t.priority_source or "AI") == "CONTROLLER":
                kept += 1  # human decision stands; AI view is still recorded
                continue
            t.priority_label = r["priority_label"]
            t.priority_score = float(r["priority_score"])
            t.priority_explanation = r["priority_explanation"]
            t.priority_source = "AI"
        db.commit()

        counts = pd.Series([t.priority_label for t in tasks]).value_counts().to_dict()
        return {"updated": len(tasks), "controller_overrides_kept": kept, "distribution": counts}


def _value_text(group: str, raw: pd.Series) -> str:
    if group == "severity":
        return f"{int(raw['severity'])}/5"
    if group == "asset_criticality":
        return f"{int(raw['asset_criticality'])}/5"
    if group == "overdue":
        return f"{int(raw['overdue_days'])} days overdue" if raw["overdue_days"] > 0 else "within SLA"
    if group == "traffic":
        return f"{int(raw['traffic_gmt'])} GMT"
    if group == "block":
        return "yes" if bool(raw["requires_traffic_block"]) else "no"
    if group == "duration":
        return f"{int(raw['estimated_duration_min'])} min"
    if group == "gang":
        return f"{int(raw['gang_size'])} staff"
    return str(raw.get("department", ""))


def _explain(raw, label, score, confidence, factors, safety) -> str:
    up = [f for f in factors if f["impact"] >= 0.01]
    down = [f for f in factors if f["impact"] <= -0.01]
    parts = [f"Classified {label} (score {score:.2f}, model confidence {confidence:.0%})."]
    if up:
        parts.append("Compared with a typical task, raised by " + "; ".join(
            f"{f['factor']} {f['value']} (+{f['impact']:.2f})" for f in up[:3]) + ".")
    if down:
        parts.append(("Lowered" if up else "Compared with a typical task, lowered") + " by " + "; ".join(
            f"{f['factor']} {f['value']} ({f['impact']:.2f})" for f in down[:2]) + ".")
    if not up and not down:
        parts.append("No single factor dominates; the combination of inputs sets the level.")
    if safety:
        parts.append(SAFETY_RULE)
    return " ".join(parts)


# module-level singleton (lazy)
_prioritizer: Prioritizer | None = None


def get_prioritizer(reload: bool = False) -> Prioritizer:
    global _prioritizer
    if _prioritizer is None or reload:
        _prioritizer = Prioritizer()
    return _prioritizer
