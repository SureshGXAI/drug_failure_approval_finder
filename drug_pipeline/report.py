"""
report.py
=========
Builds a single combined PDF report summarizing the output of all four
modules (failed, approved, ongoing, annotation) for one pipeline run.

The PDF is a *summary*, not a full CSV dump: each module's table shows a
curated set of the most useful columns so it stays readable on a landscape
page. The full column set is always available in the matching CSV file -
the PDF's job is a shareable, printable overview, not a data export format.

Used by:
  - drug_pipeline/cli.py       (--pdf-output flag)
  - streamlit_app.py           ("PDF report" tab)
"""

from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)

PAGE_SIZE = landscape(letter)
MARGIN = 0.5 * inch

# (title, subtitle, column spec) - column spec is (header, row_key, width_pts)
MODULE_SPECS = {
    "failed": {
        "title": "Module A - failed / stopped / discontinued drugs",
        "empty_message": "No failed, stopped, or discontinued drugs were found for this query.",
        "columns": [
            ("Drug name", "Drug Name", 110),
            ("Phase", "Phase", 60),
            ("Status", "Status", 75),
            ("Reason", "Reason", 330),
            ("Trial IDs", "Trial IDs (NCT)", 105),
        ],
    },
    "approved": {
        "title": "Module B - FDA-approved drugs",
        "empty_message": "No FDA-approved drugs were found for this query.",
        "columns": [
            ("Drug name", "Drug Name", 110),
            ("Phase", "Phase", 60),
            ("FDA status", "FDA Approval Status", 220),
            ("Sponsor(s)", "Sponsor(s)", 150),
            ("Approval date(s)", "Approval Date(s)", 140),
        ],
    },
    "ongoing": {
        "title": "Module C - ongoing clinical trials",
        "empty_message": "No ongoing clinical trials were found for this query.",
        "columns": [
            ("Drug name", "Drug Name", 100),
            ("Phase", "Phase", 55),
            ("Trial status", "Trial Status", 90),
            ("Sponsor", "Sponsor", 150),
            ("Est. completion", "Estimated Primary Completion Date", 105),
            ("Trial IDs", "Trial IDs (NCT)", 100),
        ],
    },
    "annotation": {
        "title": "Module D - target biological annotation",
        "empty_message": "No target annotation was generated for this query.",
        "columns": [
            ("Gene", "Gene Symbol", 60),
            ("Protein name", "Protein Name", 160),
            ("Reactome pathways", "Reactome Pathways", 260),
            ("DisGeNET associated diseases", "DisGeNET Associated Diseases", 200),
        ],
    },
}


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": base["Title"],
        "heading": base["Heading2"],
        "body": base["Normal"],
        "cell": ParagraphStyle("cell", parent=base["Normal"], fontSize=7.5, leading=9.5),
        "cell_header": ParagraphStyle("cell_header", parent=base["Normal"],
                                       fontSize=8, leading=10, textColor=colors.white,
                                       fontName="Helvetica-Bold"),
    }


def _module_table(rows: list, columns: list, styles: dict) -> Table:
    header = [Paragraph(h, styles["cell_header"]) for h, _key, _w in columns]
    data = [header]
    for row in rows:
        data.append([
            Paragraph(str(row.get(key, "") or ""), styles["cell"])
            for _label, key, _w in columns
        ])
    col_widths = [w for _label, _key, w in columns]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3C3489")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B4B2A9")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1EFE8")]),
    ]))
    return table


def build_pdf(entity: dict, module_rows: dict, output_path: str) -> str:
    """
    entity:      {'type', 'id', 'name'} from open_targets.resolve_input()
    module_rows: {'failed': [...], 'approved': [...], 'ongoing': [...], 'annotation': [...]}
                 any key may be omitted or empty if that module was skipped.
    output_path: where to write the PDF.
    """
    styles = _styles()
    doc = SimpleDocTemplate(
        output_path, pagesize=PAGE_SIZE,
        leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN,
    )
    story = []

    # --- Title / summary page ---------------------------------------------
    story.append(Paragraph("Drug pipeline report", styles["title"]))
    story.append(Spacer(1, 10))
    subtitle = f"{entity.get('type', '').title()}: {entity.get('name', '')} ({entity.get('id', '')})"
    story.append(Paragraph(subtitle, styles["heading"]))
    story.append(Paragraph(f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["body"]))
    story.append(Spacer(1, 16))

    summary_data = [["Module", "Description", "Rows"]]
    for key in ("failed", "approved", "ongoing", "annotation"):
        spec = MODULE_SPECS[key]
        count = len(module_rows.get(key) or [])
        summary_data.append([spec["title"].split(" - ")[0], spec["title"].split(" - ")[1], str(count)])
    summary_table = Table(summary_data, colWidths=[90, 420, 60])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#26215C")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B4B2A9")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1EFE8")]),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Each section below shows a curated subset of columns. The full column set "
        "(mechanism of action, PubChem chemical properties, PubMed references, source "
        "URLs, etc.) is available in the matching CSV export.",
        styles["body"],
    ))

    # --- One section per module ---------------------------------------------
    for key in ("failed", "approved", "ongoing", "annotation"):
        spec = MODULE_SPECS[key]
        rows = module_rows.get(key) or []
        story.append(PageBreak())
        story.append(Paragraph(spec["title"], styles["heading"]))
        story.append(Spacer(1, 8))
        if rows:
            story.append(_module_table(rows, spec["columns"], styles))
        else:
            story.append(Paragraph(spec["empty_message"], styles["body"]))

    doc.build(story)
    return output_path
