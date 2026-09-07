"""
Synthetic dataset generator for the Automatic Block Planning System.

Produces four realistic, inter-consistent source datasets that mimic the
operational feeds that an Indian Railways zone would receive:

  * TMS  (Track Management System)          -> track / permanent-way defects
  * SMMS (Signal Maintenance Mgmt System)   -> signalling & telecom maintenance
  * TDMS (Traction Distribution Mgmt System) -> OHE / electrical maintenance
  * COA  (Control Office Application)        -> train timetable + maintenance windows

All four feeds share a common master of stations and corridors so that the
data-integration layer can merge them on `corridor_id` / `station_code`.

Run:
    python generate_synthetic_data.py --out ./raw --seed 42
"""

from __future__ import annotations

import argparse
import os
import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Master reference data — a compact but realistic slice of an IR zone.
# Corridors are real trunk routes; stations use real-ish station codes.
# --------------------------------------------------------------------------- #

CORRIDORS = [
    # corridor_id, name, section stations (code, name, km-post), traffic weight
    {
        "corridor_id": "COR-NDLS-CNB",
        "name": "New Delhi – Kanpur (Grand Trunk)",
        "electrified": True,
        "traffic_gmt": 95,  # gross million tonnes / annum (freight+pax intensity proxy)
        "stations": [
            ("NDLS", "New Delhi", 0),
            ("GZB", "Ghaziabad", 24),
            ("ALJN", "Aligarh Jn", 130),
            ("TDL", "Tundla Jn", 205),
            ("ETW", "Etawah", 310),
            ("CNB", "Kanpur Central", 440),
        ],
    },
    {
        "corridor_id": "COR-CNB-DDU",
        "name": "Kanpur – Pt. Deen Dayal Upadhyaya",
        "electrified": True,
        "traffic_gmt": 88,
        "stations": [
            ("CNB", "Kanpur Central", 440),
            ("FTP", "Fatehpur", 517),
            ("ALD", "Prayagraj Jn", 634),
            ("MZP", "Mirzapur", 720),
            ("DDU", "DDU Jn (Mughalsarai)", 800),
        ],
    },
    {
        "corridor_id": "COR-BRC-ST",
        "name": "Vadodara – Surat (Western Trunk)",
        "electrified": True,
        "traffic_gmt": 78,
        "stations": [
            ("BRC", "Vadodara Jn", 0),
            ("BH", "Bharuch Jn", 70),
            ("ANND", "Anand Jn", 35),
            ("ST", "Surat", 130),
        ],
    },
    {
        "corridor_id": "COR-HWH-ASN",
        "name": "Howrah – Asansol (Eastern Trunk)",
        "electrified": True,
        "traffic_gmt": 92,
        "stations": [
            ("HWH", "Howrah Jn", 0),
            ("BWN", "Barddhaman Jn", 107),
            ("DGR", "Durgapur", 158),
            ("ASN", "Asansol Jn", 200),
        ],
    },
    {
        "corridor_id": "COR-SBC-JTJ",
        "name": "Bengaluru – Jolarpettai (South Western)",
        "electrified": True,
        "traffic_gmt": 65,
        "stations": [
            ("SBC", "KSR Bengaluru", 0),
            ("BNC", "Bengaluru Cantt", 4),
            ("BWT", "Bangarapet", 65),
            ("KPN", "Kuppam", 110),
            ("JTJ", "Jolarpettai Jn", 148),
        ],
    },
    {
        "corridor_id": "COR-BSL-NGP",
        "name": "Bhusaval – Nagpur (Central Trunk)",
        "electrified": True,
        "traffic_gmt": 84,
        "stations": [
            ("BSL", "Bhusaval Jn", 0),
            ("AK", "Akola Jn", 130),
            ("BD", "Badnera Jn", 210),
            ("WR", "Wardha Jn", 290),
            ("NGP", "Nagpur Jn", 360),
        ],
    },
]

DEPARTMENTS = {
    "ENG": "Engineering (Permanent Way)",
    "SNT": "Signal & Telecom",
    "TRD": "Traction Distribution (OHE)",
}

# --------------------------------------------------------------------------- #
# Catalogues of realistic maintenance activity types per department.
# Each entry: code, description, base_duration_min, base_severity(1-5),
#             requires_traffic_block (bool), typical_gang_size
# --------------------------------------------------------------------------- #

TMS_DEFECTS = [
    ("RAIL_FRACTURE", "Rail fracture / weld failure", 240, 5, True, 8),
    ("GAUGE_WIDENING", "Gauge widening beyond limit", 180, 4, True, 10),
    ("BALLAST_DEFICIENCY", "Ballast deficiency / packing", 300, 3, True, 12),
    ("TRACK_CIRCUIT_FAIL", "Track buckling / misalignment", 210, 4, True, 8),
    ("USFD_FLAW", "USFD detected internal flaw", 150, 5, True, 6),
    ("POINTS_CROSSING_WEAR", "Points & crossing wear", 240, 3, True, 6),
    ("LWR_DESTRESSING", "LWR de-stressing", 360, 3, True, 14),
    ("BRIDGE_APPROACH", "Bridge approach track attention", 200, 4, True, 10),
]

SMMS_TASKS = [
    ("SIGNAL_LAMP_FAIL", "Colour-light signal lamp failure", 60, 4, False, 2),
    ("POINT_MACHINE", "Electric point machine overhaul", 180, 4, True, 3),
    ("AXLE_COUNTER", "Axle counter reset / replacement", 90, 3, False, 2),
    ("TRACK_CIRCUIT", "Track circuit tuning / repair", 120, 3, True, 3),
    ("INTERLOCKING_TEST", "Interlocking periodic testing", 240, 3, True, 4),
    ("CABLE_FAULT", "Signalling cable fault rectification", 150, 4, True, 3),
    ("BLOCK_INSTRUMENT", "Block instrument / telecom repair", 90, 2, False, 2),
    ("LC_GATE_SIGNAL", "Level-crossing gate signal attention", 120, 3, False, 2),
]

TDMS_TASKS = [
    ("OHE_WIRE_WEAR", "OHE contact wire wear replacement", 240, 5, True, 6),
    ("INSULATOR_FLASH", "Insulator flashover / replacement", 120, 4, True, 4),
    ("TENSIONING", "Auto-tensioning device attention", 150, 3, True, 4),
    ("PANTO_ENTANGLE", "Pantograph entanglement damage", 300, 5, True, 8),
    ("SP_MAINT", "Sectioning post / SP maintenance", 180, 3, True, 4),
    ("EARTHING", "OHE earthing / bonding check", 90, 2, False, 3),
    ("NEUTRAL_SECTION", "Neutral section attention", 120, 3, True, 4),
    ("TSS_TRANSFORMER", "Traction sub-station transformer", 360, 4, True, 6),
]


def _rng(seed: int):
    random.seed(seed)
    np.random.seed(seed)


def _all_stations():
    rows = []
    for c in CORRIDORS:
        for code, name, km in c["stations"]:
            rows.append(
                {
                    "corridor_id": c["corridor_id"],
                    "corridor_name": c["name"],
                    "station_code": code,
                    "station_name": name,
                    "km_post": km,
                    "electrified": c["electrified"],
                    "traffic_gmt": c["traffic_gmt"],
                }
            )
    return pd.DataFrame(rows)


def _pick_asset_criticality(traffic_gmt: int) -> int:
    """Higher-traffic corridors host more critical assets (1-5)."""
    base = 3 if traffic_gmt >= 85 else (2 if traffic_gmt >= 70 else 1)
    return int(np.clip(base + np.random.randint(0, 3), 1, 5))


def generate_defect_feed(catalogue, dept_code, prefix, n, stations, start_day, horizon_days):
    rows = []
    today = start_day
    for i in range(n):
        st = stations.sample(1).iloc[0]
        code, desc, dur, sev, needs_block, gang = random.choice(catalogue)

        # reported date within the last `horizon_days`
        reported = today - timedelta(days=int(np.random.exponential(scale=horizon_days / 3)))
        reported = max(reported, today - timedelta(days=horizon_days))

        # SLA depends on severity: severe defects have short SLA
        sla_days = {5: 3, 4: 7, 3: 15, 2: 30, 1: 45}[sev]
        due = reported + timedelta(days=sla_days)
        overdue_days = max(0, (today - due).days)

        # jitter duration / severity a little for realism
        duration = int(max(30, np.random.normal(dur, dur * 0.15)))
        severity = int(np.clip(round(np.random.normal(sev, 0.4)), 1, 5))

        asset_crit = _pick_asset_criticality(st["traffic_gmt"])

        rows.append(
            {
                f"{prefix}_id": f"{prefix}-{i+1:05d}",
                "department": dept_code,
                "corridor_id": st["corridor_id"],
                "station_code": st["station_code"],
                "km_post": float(st["km_post"]) + round(np.random.uniform(-2, 2), 2),
                "defect_code": code,
                "description": desc,
                "severity": severity,
                "asset_criticality": asset_crit,
                "reported_date": reported.date().isoformat(),
                "due_date": due.date().isoformat(),
                "overdue_days": overdue_days,
                "estimated_duration_min": duration,
                "requires_traffic_block": bool(needs_block),
                "gang_size": gang,
                "traffic_gmt": int(st["traffic_gmt"]),
                "status": np.random.choice(
                    ["PENDING", "PENDING", "PENDING", "IN_PROGRESS", "COMPLETED"],
                    p=[0.55, 0.15, 0.1, 0.1, 0.1],
                ),
            }
        )
    return pd.DataFrame(rows)


def generate_coa_timetable(stations, start_day, days=7):
    """
    COA feed: for each corridor produce (a) a train timetable of passing trains
    and (b) the daily maintenance windows (traffic blocks the control office
    is willing to grant), typically low-traffic night/afternoon periods.
    """
    train_rows = []
    window_rows = []

    corridors = stations[["corridor_id", "corridor_name", "traffic_gmt"]].drop_duplicates()

    train_types = [
        ("RAJ", "Rajdhani Express", 1),
        ("SF", "Superfast Express", 2),
        ("EXP", "Mail/Express", 3),
        ("PASS", "Passenger", 4),
        ("FRT", "Freight", 5),
        ("MEMU", "MEMU/EMU", 4),
    ]

    tid = 1
    for _, cor in corridors.iterrows():
        # number of daily trains scales with traffic
        n_trains = int(cor["traffic_gmt"] / 2)
        for d in range(days):
            day = start_day + timedelta(days=d)
            for _ in range(n_trains):
                ttype, tname, prio = random.choice(train_types)
                dep_minute = np.random.randint(0, 24 * 60)
                dep = day + timedelta(minutes=int(dep_minute))
                train_rows.append(
                    {
                        "train_no": f"{np.random.randint(10000, 99999)}",
                        "train_type": ttype,
                        "train_name": tname,
                        "priority": prio,  # 1 highest (Rajdhani) .. 5 freight
                        "corridor_id": cor["corridor_id"],
                        "service_date": day.date().isoformat(),
                        "scheduled_dep": dep.strftime("%H:%M"),
                    }
                )
                tid += 1

            # Maintenance windows: control office grants blocks in low-density bands.
            # Typically 2 windows/day: a night mega-block and an afternoon lean-period.
            windows = [
                ("00:30", "04:30", "NIGHT_BLOCK"),
                ("13:00", "16:00", "LEAN_PERIOD"),
            ]
            # High-traffic corridors get shorter/fewer windows
            if cor["traffic_gmt"] >= 90:
                windows = [("01:00", "04:00", "NIGHT_BLOCK")]
            for w_start, w_end, wtype in windows:
                window_rows.append(
                    {
                        "corridor_id": cor["corridor_id"],
                        "date": day.date().isoformat(),
                        "window_start": w_start,
                        "window_end": w_end,
                        "window_type": wtype,
                        "max_block_minutes": int(
                            (datetime.strptime(w_end, "%H:%M") - datetime.strptime(w_start, "%H:%M")).seconds / 60
                        ),
                    }
                )

    return pd.DataFrame(train_rows), pd.DataFrame(window_rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "raw"))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--horizon", type=int, default=45, help="days of defect history")
    ap.add_argument("--plan-days", type=int, default=7, help="timetable/window horizon")
    args = ap.parse_args()

    _rng(args.seed)
    os.makedirs(args.out, exist_ok=True)

    stations = _all_stations()
    stations.to_csv(os.path.join(args.out, "master_stations.csv"), index=False)

    today = datetime(2026, 9, 5)  # aligned with project "today"

    tms = generate_defect_feed(TMS_DEFECTS, "ENG", "TMS", 220, stations, today, args.horizon)
    smms = generate_defect_feed(SMMS_TASKS, "SNT", "SMMS", 180, stations, today, args.horizon)
    tdms = generate_defect_feed(TDMS_TASKS, "TRD", "TDMS", 160, stations, today, args.horizon)

    tms.to_csv(os.path.join(args.out, "tms_track_defects.csv"), index=False)
    smms.to_csv(os.path.join(args.out, "smms_signal_maintenance.csv"), index=False)
    tdms.to_csv(os.path.join(args.out, "tdms_electrical_maintenance.csv"), index=False)

    trains, windows = generate_coa_timetable(stations, today + timedelta(days=1), days=args.plan_days)
    trains.to_csv(os.path.join(args.out, "coa_timetable.csv"), index=False)
    windows.to_csv(os.path.join(args.out, "coa_maintenance_windows.csv"), index=False)

    print("Synthetic data written to", args.out)
    for name, df in [
        ("master_stations", stations),
        ("tms_track_defects", tms),
        ("smms_signal_maintenance", smms),
        ("tdms_electrical_maintenance", tdms),
        ("coa_timetable", trains),
        ("coa_maintenance_windows", windows),
    ]:
        print(f"  {name:32s} {len(df):5d} rows")


if __name__ == "__main__":
    main()
