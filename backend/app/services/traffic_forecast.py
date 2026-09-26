"""
Train + goods traffic forecasting.

Passenger trains are timetabled, goods (freight) trains are not — they run on
demand. To judge how disruptive a maintenance window will be, the planner
needs to know how many trains of each kind will want the line during it.

Model
-----
A small Poisson HistGradientBoostingRegressor learns hourly train counts per
corridor from the COA running history:

    features: corridor traffic (GMT), hour of day (+ sin/cos), Sunday flag,
              passenger/goods flag  (no weekday feature: one week of history
              would just memorise single days)
    target:   trains departing in that hour

Passenger counts on planning dates come from the timetable when it is known;
goods counts (and passenger counts beyond the timetable) come from the model.
The artifact is one compressed joblib (tens of KB). It retrains automatically
(~1 s) when the underlying running data changes.

Output feeds the optimizer: each window gets forecast passenger / goods trains
affected and a 0-1 disruption score that replaces the old static
"night = cheap, day = expensive" rule.
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.ml.train_model import read_meta, write_meta
from app.models import Corridor, MaintenanceWindow, Train

log = logging.getLogger(__name__)

MODEL_PATH = os.path.join(settings.MODEL_DIR, "traffic_forecast.joblib")
GOODS_TYPES = {"FRT"}
FEATURES = ["traffic_gmt", "hour", "hour_sin", "hour_cos", "is_sunday", "is_goods"]
GOODS_WEIGHT = 0.7      # a held goods train costs less than a held passenger train
DISRUPTION_REF = 12.0   # weighted trains at which a window counts as fully disruptive


def _hm(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _features(df: pd.DataFrame) -> pd.DataFrame:
    dts = pd.to_datetime(df["date"])
    return pd.DataFrame({
        "traffic_gmt": df["traffic_gmt"].astype(float),
        "hour": df["hour"].astype(int),
        "hour_sin": np.sin(2 * np.pi * df["hour"] / 24),
        "hour_cos": np.cos(2 * np.pi * df["hour"] / 24),
        "is_sunday": (dts.dt.weekday == 6).astype(int),
        "is_goods": df["is_goods"].astype(int),
    })[FEATURES]


def _plan_start(db: Session) -> date | None:
    return db.query(func.min(MaintenanceWindow.date)).scalar()


def _observations(db: Session) -> pd.DataFrame:
    """Hourly counts (zero-filled) for every corridor/date/category that has
    running data. Goods only exist for history dates, so goods rows are only
    produced for dates where at least one goods train ran on that corridor."""
    rows = db.query(Train.corridor_id, Train.service_date, Train.train_type, Train.scheduled_dep).all()
    if not rows:
        return pd.DataFrame()
    t = pd.DataFrame(rows, columns=["corridor_id", "date", "train_type", "dep"])
    t["hour"] = t["dep"].str.slice(0, 2).astype(int)
    t["is_goods"] = t["train_type"].isin(GOODS_TYPES).astype(int)
    counts = t.groupby(["corridor_id", "date", "is_goods", "hour"]).size().rename("count")
    present = counts.reset_index()[["corridor_id", "date", "is_goods"]].drop_duplicates()
    grid = present.merge(pd.DataFrame({"hour": range(24)}), how="cross")
    obs = grid.merge(counts.reset_index(), how="left", on=["corridor_id", "date", "is_goods", "hour"])
    obs["count"] = obs["count"].fillna(0).astype(int)
    gmt = dict(db.query(Corridor.corridor_id, Corridor.traffic_gmt).all())
    obs["traffic_gmt"] = obs["corridor_id"].map(gmt).fillna(0)
    return obs


def _fingerprint(db: Session) -> str:
    n, last = db.query(func.count(Train.id), func.max(Train.service_date)).one()
    return f"{n}:{last}"


def _new_model() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        loss="poisson", max_iter=80, max_leaf_nodes=8, min_samples_leaf=40,
        learning_rate=0.08, random_state=42
    )


def train(db: Session) -> dict:
    """Fit on actual running history (dates before the planning horizon)."""
    obs = _observations(db)
    if obs.empty:
        raise ValueError("No train running data loaded")
    start = _plan_start(db)
    hist = obs[obs["date"] < start] if start else obs
    if hist.empty or hist["is_goods"].sum() == 0:
        hist = obs  # fall back to everything available

    # Back-test: hold out the last 2 history days.
    days = sorted(hist["date"].unique())
    cut = days[-2] if len(days) > 3 else days[-1]
    tr, te = hist[hist["date"] < cut], hist[hist["date"] >= cut]
    metrics = {}
    if len(te) and len(tr):
        m = _new_model().fit(_features(tr), tr["count"])
        pred = m.predict(_features(te))
        # Baseline: average of the same corridor / category / hour.
        keys = ["corridor_id", "is_goods", "hour"]
        naive = tr.groupby(keys)["count"].mean()
        naive_pred = te.set_index(keys).index.map(naive).fillna(0)
        metrics = {
            "holdout_days": len(te["date"].unique()),
            "mae_trains_per_hour": round(float(mean_absolute_error(te["count"], pred)), 3),
            "baseline_mae_hourly_average": round(float(mean_absolute_error(te["count"], naive_pred)), 3),
            "daily_total_error_pct": round(float(
                abs(pred.sum() - te["count"].sum()) / max(te["count"].sum(), 1) * 100), 1),
        }

    model = _new_model().fit(_features(hist), hist["count"])
    os.makedirs(settings.MODEL_DIR, exist_ok=True)
    joblib.dump(model, MODEL_PATH, compress=3)
    info = {
        "algorithm": "sklearn_hist_gradient_boosting_poisson",
        "features": FEATURES,
        "trained_on_days": len(days),
        "rows": int(len(hist)),
        "fingerprint": _fingerprint(db),
        **metrics,
    }
    write_meta({"traffic_forecast": info})
    log.info("traffic forecast trained: %s", info)
    return info


class TrafficForecaster:
    def __init__(self, model, info: dict):
        self.model = model
        self.info = info

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return np.clip(self.model.predict(_features(frame)), 0, None)


_forecaster: TrafficForecaster | None = None


def get_forecaster(db: Session, retrain: bool = False) -> TrafficForecaster | None:
    """Load the model; (re)train when missing or when the data changed.
    Returns None when there is no running data at all."""
    global _forecaster
    fp = _fingerprint(db)
    if fp.startswith("0:"):
        return None
    if not retrain and _forecaster is not None and _forecaster.info.get("fingerprint") == fp:
        return _forecaster
    info = read_meta().get("traffic_forecast", {})
    model = None
    if not retrain and info.get("fingerprint") == fp and os.path.exists(MODEL_PATH):
        try:
            model = joblib.load(MODEL_PATH)
        except Exception:
            model = None
    if model is None:
        info = train(db)
        model = joblib.load(MODEL_PATH)
    _forecaster = TrafficForecaster(model, info)
    return _forecaster


# --------------------------------------------------------------------------- #
def hourly_forecast(db: Session, corridor_ids: list[str], dates: list[date]) -> pd.DataFrame:
    """Hourly passenger + goods trains per corridor/date for planning dates.
    Columns: corridor_id, date, hour, pax, goods, pax_source."""
    fc = get_forecaster(db)
    gmt = dict(db.query(Corridor.corridor_id, Corridor.traffic_gmt).all())
    grid = pd.DataFrame(
        [(c, d, h) for c in corridor_ids for d in dates for h in range(24)],
        columns=["corridor_id", "date", "hour"],
    )
    if grid.empty:
        return grid.assign(pax=[], goods=[], pax_source=[])
    grid["traffic_gmt"] = grid["corridor_id"].map(gmt).fillna(0)

    if fc is None:  # no running data: flat profile from corridor traffic
        per_hour = grid["traffic_gmt"] / 2 / 24
        grid["pax"], grid["goods"] = per_hour * 0.6, per_hour * 0.4
        grid["pax_source"] = "estimate"
    else:
        grid["pax"] = fc.predict(grid.assign(is_goods=0))
        grid["goods"] = fc.predict(grid.assign(is_goods=1))
        grid["pax_source"] = "forecast"

    # Timetabled passenger trains override the passenger forecast.
    tt = (
        db.query(Train.corridor_id, Train.service_date, Train.scheduled_dep)
        .filter(Train.corridor_id.in_(corridor_ids), Train.service_date.in_(dates))
        .filter(~Train.train_type.in_(GOODS_TYPES))
        .all()
    )
    if tt:
        t = pd.DataFrame(tt, columns=["corridor_id", "date", "dep"])
        t["hour"] = t["dep"].str.slice(0, 2).astype(int)
        known = t.groupby(["corridor_id", "date", "hour"]).size().rename("tt")
        keyed = set(zip(t["corridor_id"], t["date"]))
        grid = grid.merge(known.reset_index(), how="left", on=["corridor_id", "date", "hour"])
        mask = [(c, d) in keyed for c, d in zip(grid["corridor_id"], grid["date"])]
        grid.loc[mask, "pax"] = grid.loc[mask, "tt"].fillna(0)
        grid.loc[mask, "pax_source"] = "timetable"
        grid = grid.drop(columns=["tt"])
    return grid.drop(columns=["traffic_gmt"])


def _overlap_hours(start: str, end: str) -> list[tuple[int, int, float]]:
    """(day_offset, hour, fraction of that hour inside the window)."""
    s, e = _hm(start), _hm(end)
    if e <= s:
        e += 24 * 60
    out = []
    for m0 in range((s // 60) * 60, e, 60):
        frac = (min(e, m0 + 60) - max(s, m0)) / 60
        if frac > 0:
            out.append((m0 // (24 * 60), (m0 // 60) % 24, frac))
    return out


def disruption_from_trains(pax: float, goods: float) -> float:
    return round(min(1.0, (pax + GOODS_WEIGHT * goods) / DISRUPTION_REF), 3)


def window_traffic(db: Session, windows, growth_pct: float = 0.0) -> dict[int, dict]:
    """Forecast trains affected + disruption for each window object
    (needs id, corridor_id, date, window_start, window_end)."""
    if not windows:
        return {}
    corridors = sorted({w.corridor_id for w in windows})
    dates = sorted({d for w in windows for d in (w.date, w.date + timedelta(days=1))})
    hourly = hourly_forecast(db, corridors, dates)
    idx = hourly.set_index(["corridor_id", "date", "hour"])[["pax", "goods"]].to_dict("index")
    k = 1.0 + growth_pct / 100.0
    out = {}
    for w in windows:
        pax = goods = 0.0
        for off, hour, frac in _overlap_hours(w.window_start, w.window_end):
            r = idx.get((w.corridor_id, w.date + timedelta(days=off), hour))
            if r:
                pax += r["pax"] * frac
                goods += r["goods"] * frac
        pax, goods = pax * k, goods * k
        out[w.id] = {
            "pax": round(pax, 1),
            "goods": round(goods, 1),
            "disruption": disruption_from_trains(pax, goods),
        }
    return out


def corridor_outlook(db: Session, corridor_id: str | None = None, days: int = 7) -> dict:
    """API payload: daily + hourly outlook, window impact, quietest band."""
    start = _plan_start(db) or date.today()
    dates = [start + timedelta(days=i) for i in range(max(1, min(days, 28)))]
    q = db.query(Corridor)
    corridors = [c.corridor_id for c in (q.filter(Corridor.corridor_id == corridor_id) if corridor_id else q).all()]
    if not corridors:
        return {"corridors": [], "daily": [], "hourly_profile": [], "windows": [], "model": {}}
    h = hourly_forecast(db, corridors, dates)
    daily = (
        h.groupby("date")[["pax", "goods"]].sum().round(1).reset_index()
        .assign(date=lambda d: d["date"].astype(str)).to_dict(orient="records")
    )
    prof = h.groupby("hour")[["pax", "goods"]].sum() / len(dates)
    prof = prof.round(2)
    load = (prof["pax"] + GOODS_WEIGHT * prof["goods"]).to_numpy()
    band = np.convolve(np.r_[load, load[:2]], np.ones(3), "valid")[:24]
    qh = int(band.argmin())

    wins = (
        db.query(MaintenanceWindow)
        .filter(MaintenanceWindow.corridor_id.in_(corridors), MaintenanceWindow.date.in_(dates))
        .order_by(MaintenanceWindow.date, MaintenanceWindow.window_start).all()
    )
    wt = window_traffic(db, wins)
    return {
        "corridors": corridors,
        "start": str(start),
        "days": len(dates),
        "daily": daily,
        "hourly_profile": [{"hour": int(i), "pax": float(r.pax), "goods": float(r.goods)} for i, r in prof.iterrows()],
        "quietest_band": {"start": f"{qh:02d}:00", "end": f"{(qh + 3) % 24:02d}:00",
                          "weighted_trains": round(float(band[qh]), 1)},
        "pax_source": sorted(set(h["pax_source"])),
        "windows": [
            {"window_id": w.id, "corridor_id": w.corridor_id, "date": str(w.date),
             "start": w.window_start, "end": w.window_end, "type": w.window_type,
             "status": w.status or "GRANTED", **wt.get(w.id, {})}
            for w in wins
        ],
        "model": (get_forecaster(db).info if get_forecaster(db) else {}),
    }
