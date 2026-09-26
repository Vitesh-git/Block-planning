"""
Train the AI maintenance-priority model.

A scikit-learn HistGradientBoostingClassifier predicts the priority class
(Critical / High / Medium / Low). It replaces the earlier XGBoost model: same
accuracy class on this tabular problem, but scikit-learn is already a
dependency, so the project no longer ships XGBoost (~170 MB locally and a
~500 MB GPU build in Linux/Docker images).

Only the final model is persisted (compressed joblib) plus a small JSON
metadata file; no checkpoints or intermediate files are written.

Run directly:
    python -m app.ml.train_model
"""

from __future__ import annotations

import json
import os

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split

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
META_PATH = os.path.join(settings.MODEL_DIR, "model_meta.json")
ALGORITHM = "sklearn_hist_gradient_boosting"


# ------------------------------------------------------------------ #
# Shared metadata file (priority model at top level for backward
# compatibility; other models store their own section, e.g.
# "traffic_forecast").
# ------------------------------------------------------------------ #
def read_meta() -> dict:
    try:
        with open(META_PATH) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def write_meta(updates: dict) -> dict:
    os.makedirs(settings.MODEL_DIR, exist_ok=True)
    meta = read_meta()
    meta.update(updates)
    tmp = META_PATH + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(meta, fh, indent=2)
    os.replace(tmp, META_PATH)  # atomic; no stray temp file is left behind
    return meta


def _make_model() -> HistGradientBoostingClassifier:
    # Small trees + few iterations keep the artifact to a few hundred KB.
    return HistGradientBoostingClassifier(
        max_iter=120,
        max_leaf_nodes=15,
        learning_rate=0.1,
        l2_regularization=0.1,
        class_weight="balanced",  # "Low" is rare; don't let it be ignored
        random_state=42,
    )


def train(verbose: bool = True) -> dict:
    os.makedirs(settings.MODEL_DIR, exist_ok=True)

    merged = normalize_feeds()
    X = build_features(merged)
    y = label_from_index(priority_index(merged)).to_numpy()

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    model = _make_model().fit(X_train, y_train)
    preds = model.predict(X_test)

    acc = accuracy_score(y_test, preds)
    macro_f1 = f1_score(y_test, preds, average="macro")
    report = classification_report(y_test, preds, output_dict=True, zero_division=0)
    labels = [c for c in PRIORITY_CLASSES[::-1] if c in set(y)]  # Critical..Low
    cm = confusion_matrix(y_test, preds, labels=labels).tolist()

    # 4-fold cross-validated accuracy is a steadier number on ~560 rows.
    cv = StratifiedKFold(n_splits=4, shuffle=True, random_state=0)
    cv_acc = cross_val_score(_make_model(), X, y, cv=cv).mean()

    # Model-agnostic global importance (HGB has no feature_importances_).
    perm = permutation_importance(model, X_test, y_test, n_repeats=5, random_state=42)
    raw = np.clip(perm.importances_mean, 0, None)
    total = float(raw.sum()) or 1.0
    importances = {c: round(float(v) / total, 4) for c, v in zip(FEATURE_COLUMNS, raw)}

    # Refit on all data for inference (evaluation above used the hold-out).
    model = _make_model().fit(X, y)
    joblib.dump(model, MODEL_PATH, compress=3)

    meta = write_meta({
        "algorithm": ALGORITHM,
        "accuracy": round(float(acc), 4),
        "macro_f1": round(float(macro_f1), 4),
        "cv_accuracy": round(float(cv_acc), 4),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "features": FEATURE_COLUMNS,
        "classes": [str(c) for c in model.classes_],
        "confusion_matrix": {"labels": labels, "matrix": cm},
        "feature_importances": importances,
        # Small background sample for per-task explanations: a factor's
        # impact = score - average score when that factor takes typical values.
        "explain_background": X.sample(n=min(24, len(X)), random_state=7).round(4).to_dict(orient="list"),
        "classification_report": report,
    })

    if verbose:
        print(f"[train] algorithm      = {ALGORITHM}")
        print(f"[train] hold-out acc   = {acc:.3f}  macro-F1 = {macro_f1:.3f}  4-fold CV acc = {cv_acc:.3f}")
        print(f"[train] model saved to = {MODEL_PATH} ({os.path.getsize(MODEL_PATH) // 1024} KB)")
        top = sorted(importances.items(), key=lambda kv: kv[1], reverse=True)[:5]
        print("[train] top features   =", ", ".join(f"{k}({v:.2f})" for k, v in top))

    return meta


if __name__ == "__main__":
    train()
