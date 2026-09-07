"""
Report generation — weekly / monthly block plans as PDF and Excel.

Uses reportlab for PDF and openpyxl for Excel. Both return raw bytes so the API
can stream them as file downloads.
"""

from __future__ import annotations

import io
from collections import defaultdict
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy.orm import Session

from app.models import BlockTask, MaintenanceBlock, MaintenanceTask

PRIORITY_COLORS = {
    "Critical": colors.HexColor("#b91c1c"),
    "High": colors.HexColor("#c2410c"),
    "Medium": colors.HexColor("#a16207"),
    "Low": colors.HexColor("#15803d"),
}


def _collect_blocks(db: Session):
    blocks = db.query(MaintenanceBlock).order_by(
        MaintenanceBlock.date, MaintenanceBlock.corridor_id
    ).all()
    data = []
    for b in blocks:
        links = db.query(BlockTask).filter(BlockTask.block_id == b.id).all()
        tasks = []
        for l in links:
            t = db.get(MaintenanceTask, l.task_id)
            if t:
                tasks.append(t)
        data.append((b, tasks))
    return data


def build_pdf(db: Session, period: str = "weekly") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=1.2 * cm, rightMargin=1.2 * cm,
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "T", parent=styles["Title"], fontSize=18, textColor=colors.HexColor("#0f172a")
    )
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=colors.HexColor("#1e3a8a"))
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8)

    story = []
    story.append(Paragraph("Indian Railways — Automatic Block Plan", title_style))
    story.append(Paragraph(
        f"{period.capitalize()} Maintenance Block Plan &nbsp;|&nbsp; "
        f"Generated {datetime.now():%Y-%m-%d %H:%M}", styles["Normal"]))
    story.append(Spacer(1, 0.4 * cm))

    data = _collect_blocks(db)

    # Summary
    total_tasks = sum(len(t) for _, t in data)
    multidept = sum(1 for b, _ in data if b.is_multi_dept)
    avg_util = (sum(b.utilization for b, _ in data) / len(data)) if data else 0
    story.append(Paragraph(
        f"<b>{len(data)}</b> blocks planned &nbsp;|&nbsp; "
        f"<b>{total_tasks}</b> tasks scheduled &nbsp;|&nbsp; "
        f"<b>{multidept}</b> multi-department blocks &nbsp;|&nbsp; "
        f"average utilization <b>{avg_util:.0%}</b>", h2))
    story.append(Spacer(1, 0.3 * cm))

    # Group by date
    by_date = defaultdict(list)
    for b, tasks in data:
        by_date[b.date].append((b, tasks))

    for d in sorted(by_date):
        story.append(Paragraph(f"{d:%A, %d %b %Y}", h2))
        rows = [["Block", "Corridor", "Window", "Depts", "Tasks", "Util", "Disrupt."]]
        for b, tasks in by_date[d]:
            rows.append([
                b.block_ref,
                b.corridor_id.replace("COR-", ""),
                f"{b.start_time}-{b.end_time}",
                b.departments,
                str(b.task_count),
                f"{b.utilization:.0%}",
                f"{b.disruption_score:.0f}",
            ])
        tbl = Table(rows, repeatRows=1, colWidths=[3*cm, 3.5*cm, 3*cm, 2.6*cm, 1.6*cm, 1.6*cm, 2*cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 0.5 * cm))

    doc.build(story)
    buf.seek(0)
    return buf.read()


def build_excel(db: Session, period: str = "weekly") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Block Plan"

    header_fill = PatternFill("solid", fgColor="1E3A8A")
    header_font = Font(bold=True, color="FFFFFF")

    headers = [
        "Block Ref", "Date", "Corridor", "Start", "End", "Planned (min)",
        "Window (min)", "Utilization", "Departments", "Multi-Dept",
        "Task Count", "Disruption",
    ]
    ws.append(headers)
    for c in ws[1]:
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center")

    data = _collect_blocks(db)
    for b, _ in data:
        ws.append([
            b.block_ref, b.date.isoformat(), b.corridor_id, b.start_time, b.end_time,
            b.planned_minutes, b.window_minutes, round(b.utilization, 3),
            b.departments, "Yes" if b.is_multi_dept else "No",
            b.task_count, b.disruption_score,
        ])
    for col in ws.columns:
        width = max(len(str(c.value)) for c in col if c.value is not None) + 2
        ws.column_dimensions[col[0].column_letter].width = min(width, 30)

    # Second sheet: detailed task allocation
    ws2 = wb.create_sheet("Task Allocation")
    ws2.append([
        "Block Ref", "Source ID", "Department", "Defect", "Description",
        "Priority", "Corridor", "Station", "Duration (min)",
    ])
    for c in ws2[1]:
        c.fill = header_fill
        c.font = header_font
    for b, tasks in data:
        for t in tasks:
            ws2.append([
                b.block_ref, t.source_id, t.department, t.defect_code,
                t.description, t.priority_label, t.corridor_id, t.station_code,
                t.estimated_duration_min,
            ])
    for col in ws2.columns:
        width = max((len(str(c.value)) for c in col if c.value is not None), default=8) + 2
        ws2.column_dimensions[col[0].column_letter].width = min(width, 40)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
