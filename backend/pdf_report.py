"""
PDF report generator for PlanMeasure AI.
"""
from __future__ import annotations

import io
from typing import Dict, Any, List

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image as RLImage, PageBreak
)


BRAND_BLUE = colors.HexColor("#2563EB")
DARK = colors.HexColor("#0A0A0A")
MUTED = colors.HexColor("#52525B")
BORDER = colors.HexColor("#E5E7EB")


def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle("H1Brand", parent=s["Heading1"], textColor=DARK,
                         fontSize=22, spaceAfter=6, leading=26))
    s.add(ParagraphStyle("H2Brand", parent=s["Heading2"], textColor=DARK,
                         fontSize=14, spaceAfter=6, leading=18))
    s.add(ParagraphStyle("MutedSmall", parent=s["BodyText"], textColor=MUTED,
                         fontSize=9, leading=12))
    s.add(ParagraphStyle("BodyBrand", parent=s["BodyText"], textColor=DARK,
                         fontSize=10, leading=14))
    return s


def _stat_table(rows: List[List[str]]):
    tbl = Table(rows, colWidths=[65 * mm, 65 * mm, 40 * mm])
    tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F9FAFB")),
        ("TEXTCOLOR", (0, 0), (-1, 0), DARK),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 1), (-1, -1), DARK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return tbl


def build_report_pdf(bd: Dict[str, Any], preview_png: bytes | None,
                     filename: str = "plan",
                     pages: list | None = None) -> bytes:
    """Return PDF bytes for a completed BuildingData analysis dict.

    If `pages` is given, it is a list of (page_index, page_data_dict, preview_png|None)
    tuples. In that case the aggregate summary is rendered first, followed by one
    section per page. If omitted, the report renders the single top-level `bd`.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"PlanMeasure AI Report — {filename}",
    )
    s = _styles()
    story = []

    # Header
    story.append(Paragraph("PlanMeasure AI", s["H1Brand"]))
    story.append(Paragraph("Automated Floor Plan Analysis Report", s["MutedSmall"]))
    story.append(Spacer(1, 6 * mm))

    # Project meta
    total_pages = len(pages) if pages and len(pages) > 1 else 1
    story.append(Paragraph(f"<b>Source:</b> {filename} · {total_pages} page(s)",
                           s["BodyBrand"]))
    conf = bd.get("confidence", 0)
    approx = "Approximate" if bd.get("approximate") else "Measured"
    scale_note = bd.get("scale_note") or (
        "Scale detected" if bd.get("scale_detected")
        else "No scale detected — measurements approximate"
    )
    story.append(Paragraph(
        f"<b>Confidence:</b> {int(conf)}%  &nbsp;&nbsp; "
        f"<b>Mode:</b> {approx}  &nbsp;&nbsp; "
        f"<b>Notes:</b> {scale_note}", s["MutedSmall"]
    ))
    story.append(Spacer(1, 6 * mm))

    # Aggregate preview (or single-page preview)
    if preview_png:
        try:
            img = RLImage(io.BytesIO(preview_png))
            max_w = 170 * mm
            iw, ih = img.wrap(0, 0)
            if iw > max_w:
                ratio = max_w / iw
                img._restrictSize(max_w, ih * ratio)
            story.append(img)
            story.append(Spacer(1, 6 * mm))
        except Exception:
            pass

    # Aggregate summary
    title = "Aggregate Building Summary" if (pages and len(pages) > 1) else "Building Summary"
    story.append(Paragraph(title, s["H2Brand"]))
    story.append(_stat_table([
        ["Metric", "Value", "Unit"],
        ["Total Wall Length", f"{bd.get('wall_length', 0):.1f}", "ft"],
        ["Total Wall Length", f"{bd.get('wall_length_m', 0):.2f}", "m"],
        ["External Wall Length", f"{bd.get('external_wall', 0):.1f}", "ft"],
        ["Internal Wall Length", f"{bd.get('internal_wall', 0):.1f}", "ft"],
        ["Total Rooms", str(bd.get("rooms", 0)), "count"],
        ["Bathrooms", str(bd.get("bathrooms", 0)), "count"],
        ["Doors", str(bd.get("doors", 0)), "count"],
        ["Windows", str(bd.get("windows", 0)), "count"],
        ["Built-up Area", (f"{bd.get('built_up_area_sqft'):.0f}"
                           if bd.get("built_up_area_sqft") else "—"), "sq ft"],
        ["AI Confidence Score", f"{int(bd.get('confidence', 0))}", "%"],
    ]))
    story.append(Spacer(1, 6 * mm))

    # Room list
    room_list = bd.get("room_list") or []
    if room_list:
        story.append(Paragraph("Detected Rooms", s["H2Brand"]))
        rows = [["#", "Room", "Type", "Page", "Area (sq ft)"]]
        for i, r in enumerate(room_list, 1):
            rows.append([
                str(i),
                str(r.get("name", "-")),
                "Bathroom" if r.get("is_bathroom") else "Room",
                str(r.get("page") or "1"),
                (f"{r.get('area_sqft'):.0f}" if r.get("area_sqft") else "—"),
            ])
        t = Table(rows, colWidths=[10 * mm, 75 * mm, 30 * mm, 20 * mm, 35 * mm])
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F9FAFB")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(t)
        story.append(Spacer(1, 6 * mm))

    # Per-page breakdown
    if pages and len(pages) > 1:
        story.append(PageBreak())
        story.append(Paragraph("Per-Page Breakdown", s["H1Brand"]))
        story.append(Spacer(1, 4 * mm))
        for (idx, pdata, ppng) in pages:
            story.append(Paragraph(f"Page {idx + 1}", s["H2Brand"]))
            if ppng:
                try:
                    pimg = RLImage(io.BytesIO(ppng))
                    max_w = 170 * mm
                    iw, ih = pimg.wrap(0, 0)
                    if iw > max_w:
                        ratio = max_w / iw
                        pimg._restrictSize(max_w, ih * ratio)
                    story.append(pimg)
                    story.append(Spacer(1, 4 * mm))
                except Exception:
                    pass
            story.append(_stat_table([
                ["Metric", "Value", "Unit"],
                ["Wall Length", f"{pdata.get('wall_length', 0):.1f}", "ft"],
                ["External", f"{pdata.get('external_wall', 0):.1f}", "ft"],
                ["Internal", f"{pdata.get('internal_wall', 0):.1f}", "ft"],
                ["Rooms", str(pdata.get("rooms", 0)), "count"],
                ["Bathrooms", str(pdata.get("bathrooms", 0)), "count"],
                ["Doors", str(pdata.get("doors", 0)), "count"],
                ["Windows", str(pdata.get("windows", 0)), "count"],
                ["Confidence", f"{int(pdata.get('confidence', 0))}", "%"],
            ]))
            story.append(Spacer(1, 8 * mm))

    # Footer
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(
        "This report was generated automatically by PlanMeasure AI. "
        "Values marked approximate should be verified on site before construction decisions.",
        s["MutedSmall"]
    ))

    doc.build(story)
    return buf.getvalue()
