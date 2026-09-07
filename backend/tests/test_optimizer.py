"""
Hard-constraint tests for the OR-Tools block optimizer.

These exercise `optimize_blocks` directly with lightweight stand-in task/window
objects (no database needed), asserting the guarantees the planner must never
violate:

  * a task requiring a block, with a fitting same-corridor window, is scheduled;
  * a task that does not require a traffic block is never placed;
  * a task is only ever placed in a window on its OWN corridor;
  * placed work always fits inside the granted window;
  * multiple departments on one corridor/window combine into a SINGLE block;
  * blocks on the same corridor and date never overlap in time.
"""

from types import SimpleNamespace

import pytest

from app.services.optimization import optimize_blocks


def mk_task(tid, corridor, dept, dur=90, score=0.85, block=True):
    return SimpleNamespace(
        id=tid,
        corridor_id=corridor,
        department=dept,
        estimated_duration_min=dur,
        priority_score=score,
        requires_traffic_block=block,
    )


def mk_window(wid, corridor, start="01:00", end="04:00", wtype="NIGHT_BLOCK", date="2026-09-07"):
    return SimpleNamespace(
        id=wid,
        corridor_id=corridor,
        window_start=start,
        window_end=end,
        window_type=wtype,
        date=date,
    )


def _solve(tasks, windows, traffic=None):
    traffic = traffic or {w.corridor_id: 50 for w in windows}
    res = optimize_blocks(tasks, windows, traffic, time_limit_s=5)
    assert res.status in ("OPTIMAL", "FEASIBLE"), res.status
    return res


def test_high_priority_task_is_scheduled():
    res = _solve([mk_task(1, "COR-A", "ENG", dur=90, score=0.95)], [mk_window(10, "COR-A")])
    assert 1 in res.scheduled_task_ids


def test_non_block_task_is_never_placed():
    res = _solve([mk_task(1, "COR-A", "ENG", block=False)], [mk_window(10, "COR-A")])
    assert 1 not in res.scheduled_task_ids


def test_task_only_placed_on_its_own_corridor():
    res = _solve([mk_task(1, "COR-A", "ENG")], [mk_window(10, "COR-B")])
    assert 1 not in res.scheduled_task_ids


def test_placed_work_fits_inside_window():
    res = _solve([mk_task(1, "COR-A", "ENG", dur=90, score=0.9)], [mk_window(10, "COR-A")])
    for b in res.blocks:
        assert b["planned_minutes"] <= b["window_minutes"]
        for p in b["tasks"]:
            assert 0 <= p["offset_start"] <= p["offset_end"] <= b["window_minutes"]


def test_multi_department_work_combines_into_one_block():
    tasks = [mk_task(1, "COR-A", "ENG", dur=60), mk_task(2, "COR-A", "SNT", dur=60)]
    res = _solve(tasks, [mk_window(10, "COR-A")])
    assert res.scheduled_task_ids == {1, 2}
    assert len(res.blocks) == 1
    assert res.blocks[0]["is_multi_dept"] is True


def test_blocks_on_same_corridor_and_date_do_not_overlap():
    # Two non-overlapping night windows on the same corridor/date, enough work
    # to use both. Resulting blocks must not overlap in time.
    tasks = [mk_task(i, "COR-A", "ENG", dur=90, score=0.9) for i in range(1, 5)]
    windows = [
        mk_window(10, "COR-A", "01:00", "03:00"),
        mk_window(11, "COR-A", "05:00", "07:00"),
    ]
    res = _solve(tasks, windows)

    def to_min(hhmm):
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)

    spans = {}
    for b in res.blocks:
        spans.setdefault((b["corridor_id"], str(b["date"])), []).append(
            (to_min(b["start_time"]), to_min(b["end_time"]))
        )
    for intervals in spans.values():
        intervals.sort()
        for (s1, e1), (s2, e2) in zip(intervals, intervals[1:]):
            assert e1 <= s2, f"blocks overlap: {(s1, e1)} vs {(s2, e2)}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
