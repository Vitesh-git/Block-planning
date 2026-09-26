"""
End-to-end tests for the pipeline and the five planning capabilities, run
against a temporary SQLite database (see conftest.py).

Run:  pytest -q     (from backend/)
"""

from app.ml.features import build_features, label_from_index, priority_index
from app.services import data_integration as di

API = "/api/v1"


# ------------------------------------------------------------------ data / ML
def test_normalize_feeds_merges_three_sources():
    merged = di.normalize_feeds()
    assert set(merged["source_system"].unique()) == {"TMS", "SMMS", "TDMS"}
    assert set(merged["department"].unique()) == {"ENG", "SNT", "TRD"}
    assert merged["source_id"].notna().all()


def test_feature_matrix_shape():
    merged = di.normalize_feeds().head(50)
    X = build_features(merged)
    assert len(X) == 50
    assert not X.isna().any().any()


def test_priority_labels_are_ordered_classes():
    labels = label_from_index(priority_index(di.normalize_feeds()))
    assert set(labels.unique()).issubset({"Critical", "High", "Medium", "Low"})


def test_pipeline_creates_first_plan_version(client):
    kpis = client.get(f"{API}/dashboard/kpis").json()
    assert kpis["planned_blocks"] >= 1 and kpis["tasks_scheduled"] >= 1
    versions = client.get(f"{API}/plan/versions").json()
    assert versions[-1]["trigger_event"] == "FULL_PLAN"
    assert versions[0]["num_variables"] > 0 and versions[0]["solver_status"] in ("OPTIMAL", "FEASIBLE")


# ------------------------------------------------------- 1. AI maintenance priority
def test_tasks_have_factor_explanations(client):
    tasks = client.get(f"{API}/tasks", params={"limit": 50}).json()
    assert tasks
    for t in tasks:
        assert t["priority_label"] in {"Critical", "High", "Medium", "Low"}
        assert 0.0 <= t["priority_score"] <= 1.0
        for f in t["priority_factors"]:
            assert {"factor", "impact", "value"} <= set(f)
        assert t["priority_explanation"].startswith(("Classified", "Set to"))
    assert sum(1 for t in tasks if t["priority_factors"]) >= len(tasks) // 2


def test_safety_rule_never_ranks_severe_critical_asset_below_high():
    import pandas as pd

    from app.services.ai_prioritization import get_prioritizer

    row = pd.DataFrame([{
        "severity": 5, "asset_criticality": 5, "overdue_days": 0, "traffic_gmt": 10,
        "estimated_duration_min": 30, "requires_traffic_block": False, "gang_size": 2, "department": "SNT",
    }])
    out = get_prioritizer().predict_frame(row)
    assert out["priority_label"].iloc[0] in ("High", "Critical")


# ------------------------------------------------------- 2. traffic forecasting
def test_traffic_forecast_payload(client):
    r = client.get(f"{API}/forecast/traffic", params={"days": 7})
    assert r.status_code == 200
    body = r.json()
    assert len(body["hourly_profile"]) == 24
    assert body["daily"] and all(d["goods"] > 0 for d in body["daily"])
    assert body["windows"] and {"pax", "goods", "disruption"} <= set(body["windows"][0])
    assert "mae_trains_per_hour" in body["model"]


def test_blocks_are_explained_with_forecast_traffic(client):
    blocks = client.get(f"{API}/blocks").json()
    ex = blocks[0]["explanation"]
    assert ex["summary"] and len(ex["reasons"]) >= 2
    assert ex["traffic"]["source"] == "forecast"


# ------------------------------------------------------- 3. explainable AI + approval
def test_override_requires_reason_and_is_kept(client):
    t = client.get(f"{API}/tasks", params={"limit": 1, "priority": "High"}).json()[0]
    r = client.patch(f"{API}/tasks/{t['id']}", json={"priority_label": "Low"})
    assert r.status_code == 400

    r = client.patch(f"{API}/tasks/{t['id']}", json={
        "priority_label": "Low", "override_reason": "Asset renewed yesterday", "actor": "SSE/P.Way"})
    assert r.status_code == 200
    body = r.json()
    assert body["priority_label"] == "Low" and body["priority_source"] == "CONTROLLER"
    assert body["ai_priority_label"] == "High"

    client.post(f"{API}/pipeline/prioritize")  # re-scoring must not undo a human decision
    assert client.get(f"{API}/tasks/{t['id']}").json()["priority_label"] == "Low"

    audit = client.get(f"{API}/audit", params={"entity_type": "TASK", "entity_id": t["source_id"]}).json()
    assert audit[0]["action"] == "PRIORITY_OVERRIDE" and audit[0]["actor"] == "SSE/P.Way"

    r = client.patch(f"{API}/tasks/{t['id']}", json={"revert_to_ai": True})
    assert r.json()["priority_source"] == "AI" and r.json()["priority_label"] == "High"


def test_reject_needs_reason_and_approval_is_recorded(client):
    b = client.get(f"{API}/blocks").json()[0]
    assert client.patch(f"{API}/blocks/{b['id']}", json={"approval_status": "REJECTED"}).status_code == 400
    r = client.patch(f"{API}/blocks/{b['id']}", json={"approval_status": "APPROVED", "actor": "Sr.DOM"})
    assert r.status_code == 200 and r.json()["approved_by"] == "Sr.DOM" and r.json()["approved_at"]
    client.patch(f"{API}/blocks/{b['id']}", json={"approval_status": "PENDING"})


# ------------------------------------------------------- 4. what-if simulation
def _db_counts():
    from app.core.database import SessionLocal
    from app.models import MaintenanceBlock, MaintenanceTask, PlanVersion, Scenario

    db = SessionLocal()
    try:
        return tuple(db.query(m).count() for m in (MaintenanceBlock, MaintenanceTask, PlanVersion, Scenario))
    finally:
        db.close()


def test_simulation_runs_in_memory(client):
    before = _db_counts()
    r = client.post(f"{API}/simulate", json={"window_extension_min": 60, "time_limit_s": 4})
    assert r.status_code == 200
    body = r.json()
    assert {"baseline", "scenario", "delta"} <= set(body)
    assert body["saved_id"] is None
    assert _db_counts() == before  # nothing persisted


def test_simulation_cancelling_every_window_schedules_nothing(client):
    wins = [w["id"] for w in client.get(f"{API}/windows").json()]
    body = client.post(f"{API}/simulate", json={
        "cancel_window_ids": wins, "respect_approved": False, "time_limit_s": 2}).json()
    assert body["scenario"]["tasks_scheduled"] == 0
    assert body["delta"]["tasks_scheduled"] == -body["baseline"]["tasks_scheduled"]


def test_saving_a_scenario_stores_only_params_and_metrics(client):
    body = client.post(f"{API}/simulate", json={
        "parallel_gangs": 2, "time_limit_s": 3, "save": True, "name": "Two gangs"}).json()
    assert body["saved_id"]
    saved = client.get(f"{API}/scenarios").json()[0]
    assert saved["name"] == "Two gangs" and saved["params"]["parallel_gangs"] == 2
    assert "scenario" in saved["metrics"]
    assert client.delete(f"{API}/scenarios/{saved['id']}").status_code == 200


# ------------------------------------------------------- 5. dynamic rescheduling
def test_reschedule_keeps_approved_blocks(client):
    b = client.get(f"{API}/blocks").json()[0]
    client.patch(f"{API}/blocks/{b['id']}", json={"approval_status": "APPROVED", "actor": "Sr.DOM"})
    v_before = client.get(f"{API}/plan/versions").json()[0]["version"]

    r = client.post(f"{API}/reschedule", json={"type": "EMERGENCY_DEFECT", "actor": "Control", "time_limit_s": 5})
    assert r.status_code == 200, r.text
    opt = r.json()["optimization"]
    assert opt["version"] == v_before + 1 and opt["kept_approved_blocks"] >= 1

    kept = client.get(f"{API}/blocks/{b['id']}").json()
    assert kept["approval_status"] == "APPROVED"
    assert {t["task_id"] for t in kept["tasks"]} == {t["task_id"] for t in b["tasks"]}
    latest = client.get(f"{API}/plan/versions").json()[0]
    assert latest["trigger_event"] == "EMERGENCY_DEFECT" and latest["changed_by"] == "Control"


def test_window_cancellation_voids_approval_and_replans(client):
    b = next(x for x in client.get(f"{API}/blocks").json() if x["approval_status"] == "APPROVED")
    win = next(w for w in client.get(f"{API}/windows").json()
               if w["corridor_id"] == b["corridor_id"] and w["date"] == b["date"] and w["start"] == b["start_time"])
    r = client.post(f"{API}/reschedule", json={"type": "WINDOW_CANCELLED", "window_id": win["id"], "time_limit_s": 5})
    assert r.status_code == 200, r.text
    assert client.get(f"{API}/blocks/{b['id']}").status_code == 404
    assert all(x["start_time"] != b["start_time"] or x["date"] != b["date"] or x["corridor_id"] != b["corridor_id"]
               for x in client.get(f"{API}/blocks").json())
    actions = {e["action"] for e in client.get(f"{API}/audit").json()}
    assert {"APPROVAL_VOIDED", "WINDOW_CANCELLED"} <= actions
    # the same window cannot be cancelled twice
    assert client.post(f"{API}/reschedule", json={"type": "WINDOW_CANCELLED", "window_id": win["id"]}).status_code == 400


def test_reschedule_validates_input(client):
    assert client.post(f"{API}/reschedule", json={"type": "NOT_A_TYPE"}).status_code == 422
    assert client.post(f"{API}/reschedule", json={"type": "WINDOW_REDUCED", "window_id": 999999, "new_minutes": 60}).status_code == 404


def test_same_scenario_twice_gives_identical_results(client):
    body = {"parallel_gangs": 3, "time_limit_s": 2}
    a = client.post(f"{API}/simulate", json=body).json()["scenario"]
    b = client.post(f"{API}/simulate", json=body).json()["scenario"]
    for k in ("tasks_scheduled", "blocks", "disruption_score", "critical_scheduled"):
        assert a[k] == b[k], k


def test_unchanged_scenario_has_zero_delta(client):
    body = client.post(f"{API}/simulate", json={"time_limit_s": 2}).json()
    assert all(v == 0 for v in body["delta"].values())


def test_replan_is_stable(client):
    r = client.post(f"{API}/reschedule", json={"type": "REPLAN", "time_limit_s": 5}).json()
    d = r["optimization"]["diff"]
    assert d["moved"] + d["dropped"] <= max(3, r["optimization"]["tasks_scheduled"] // 20)
