"""
Train the AI prioritization model.

Trains an XGBoost multi-class classifier (falls back to sklearn
GradientBoosting if XGBoost is unavailable) to predict the maintenance priority
class. Persists the model + label encoder + feature list to MODEL_DIR.

Run directly:
    python -m app.ml.train_model
"""

from __future__ import annotations

import json
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

from app.core.config import settings
from app.ml.features import (
    FEATURE_COLUMNS,
    PRIORITY_CLASSES,
    build_features,
    label_from_index,
    priority_index,
)
from app.services.data_integration import normalize_feeds

MODEL_PATH = os.path.join(settings.MODEL_DIR, "priority_model.joblib")
ENCODER_PATH = os.path.join(settings.MODEL_DIR, "label_encoder.joblib")
META_PATH = os.path.join(settings.MODEL_DIR, "model_meta.json")


def _get_estimator():
    """Prefer XGBoost; gracefully fall back to sklearn if not installed."""
    try:
        from xgboost import XGBClassifier

        return (
            "xgboost",
            XGBClassifier(
                n_estimators=300,
                max_depth=4,
                learning_rate=0.08,
                subsample=0.9,
                colsample_bytree=0.9,
                objective="multi:softprob",
                num_class=len(PRIORITY_CLASSES),
                eval_metric="mlogloss",
                tree_method="hist",
                random_state=42,
            ),
        )
    except Exception:  # pragma: no cover
        from sklearn.ensemble import GradientBoostingClassifier

        return "sklearn_gbdt", GradientBoostingClassifier(random_state=42)


def train(verbose: bool = True) -> dict:
    os.makedirs(settings.MODEL_DIR, exist_ok=True)

    merged = normalize_feeds()
    X = build_features(merged)
    y_labels = label_from_index(priority_index(merged))

    encoder = LabelEncoder().fit(PRIORITY_CLASSES)
    y = encoder.transform(y_labels)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    algo, model = _get_estimator()
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    acc = accuracy_score(y_test, preds)
    report = classification_report(
        y_test, preds, target_names=encoder.classes_, output_dict=True, zero_division=0
    )

    # Feature importances (if available)
    importances = {}
    if hasattr(model, "feature_importances_"):
        importances = dict(
            zip(FEATURE_COLUMNS, [float(v) for v in model.feature_importances_])
        )

    joblib.dump(model, MODEL_PATH)
    joblib.dump(encoder, ENCODER_PATH)

    meta = {
        "algorithm": algo,
        "accuracy": float(acc),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "features": FEATURE_COLUMNS,
        "classes": list(encoder.classes_),
        "feature_importances": importances,
        "classification_report": report,
    }
    with open(META_PATH, "w") as fh:
        json.dump(meta, fh, indent=2)

    if verbose:
        print(f"[train] algorithm      = {algo}")
        print(f"[train] test accuracy  = {acc:.3f}")
        print(f"[train] model saved to = {MODEL_PATH}")
        top = sorted(importances.items(), key=lambda kv: kv[1], reverse=True)[:5]
        print("[train] top features   =", ", ".join(f"{k}({v:.2f})" for k, v in top))

    return meta


if __name__ == "__main__":
    train()
