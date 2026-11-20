"""report_export.py — PDF and Excel/CSV export for all report types."""

import csv
import os

# ── reportlab ─────────────────────────────────────────────────────────────────
from reportlab.lib.pagesizes import A4, landscape as _rl_land
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

# ── openpyxl ──────────────────────────────────────────────────────────────────
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

# ── Colour palette ────────────────────────────────────────────────────────────
C_DARK  = colors.HexColor("#0f3460")
C_MID   = colors.HexColor("#16213e")
C_GREEN = colors.HexColor("#27ae60")
C_RED   = colors.HexColor("#c0392b")
C_BLUE  = colors.HexColor("#2980b9")
C_AMBER = colors.HexColor("#e67e22")
C_ROW1  = colors.HexColor("#eaf4fb")
C_ROW2  = colors.white
C_WHITE = colors.white
C_GREY  = colors.HexColor("#95a5a6")

# ── Helpers ───────────────────────────────────────────────────────────────────

_FORMULA_CHARS = frozenset("=+-@\t\r")


def _safe_cell(val):
    """Prevent Excel formula injection: prefix dangerous leading chars with a space."""
    if isinstance(val, str) and val and val[0] in _FORMULA_CHARS:
        return " " + val
    return val


def _safe_row(row):
    """Apply _safe_cell to every value in a list before ws.append()."""
    return [_safe_cell(v) for v in row]


def _para(text, size=10, bold=False, color=None, align=TA_CENTER):
    from xml.sax.saxutils import escape
    safe = escape(str(text)) if text else ""
    style = ParagraphStyle(
        "p",
        fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=size,
        textColor=color or colors.HexColor("#1a1a2e"),
        alignment=align,
        spaceAfter=3,
    )
    return Paragraph(safe, style)

def _money(v):
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        if v < 0:
            return f"({abs(v):,.2f})"
        return f"{v:,.2f}"
    return str(v)

def _doc(filepath, land=False):
    ps = _rl_land(A4) if land else A4
    return SimpleDocTemplate(
        filepath, pagesize=ps,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=1.8*cm, bottomMargin=1.5*cm,
    )

def _report_header(title, subtitle, firm):
    elems = []
    if firm:
        elems.append(_para(firm, 13, bold=True, color=C_BLUE))
    elems.append(_para(title, 16, bold=True, color=C_DARK))
    elems.append(_para(subtitle, 9, color=C_GREY))
    elems.append(Spacer(1, 0.4*cm))
    return elems

# ── Generic two-column PDF table (P&L, Balance Sheet, Cash Flow) ──────────────
# row = {"cells": [label, value], "style": "data|section|total|highlight|subtotal|opening|empty"}

def _two_col_pdf(col_headers, rows, col_widths=None):
    if col_widths is None:
        col_widths = [12*cm, 5*cm]
    table_data = [col_headers]
    ts = [
        # Header row
        ("BACKGROUND",    (0, 0), (-1, 0), C_DARK),
        ("TEXTCOLOR",     (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 9),
        ("ALIGN",         (0, 0), (-1, 0), "CENTER"),
        # Base
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), 8.5),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
        ("ALIGN",         (1, 0), (1, -1), "RIGHT"),
    ]
    for i, row in enumerate(rows):
        ri = i + 1  # 0 = header
        label = row["cells"][0]
        val   = _money(row["cells"][1]) if len(row["cells"]) > 1 else ""
        table_data.append([label, val])
        s = row.get("style", "data")
        if s == "section":
            ts += [("BACKGROUND", (0, ri), (-1, ri), C_MID),
                   ("TEXTCOLOR",  (0, ri), (-1, ri), C_BLUE),
                   ("FONTNAME",   (0, ri), (-1, ri), "Helvetica-Bold")]
        elif s == "total":
            ts += [("BACKGROUND",   (0, ri), (-1, ri), C_ROW1),
                   ("FONTNAME",     (0, ri), (-1, ri), "Helvetica-Bold"),
                   ("LINEABOVE",    (0, ri), (-1, ri), 0.5, C_DARK)]
        elif s == "subtotal":
            ts += [("FONTNAME",  (0, ri), (-1, ri), "Helvetica-Bold"),
                   ("LINEABOVE", (0, ri), (-1, ri), 0.3, C_GREY)]
        elif s == "highlight":
            v = row["cells"][1] if len(row["cells"]) > 1 else 0
            bg = C_GREEN if (isinstance(v, (int, float)) and v >= 0) else C_RED
            ts += [("BACKGROUND", (0, ri), (-1, ri), bg),
                   ("TEXTCOLOR",  (0, ri), (-1, ri), C_WHITE),
                   ("FONTNAME",   (0, ri), (-1, ri), "Helvetica-Bold"),
                   ("FONTSIZE",   (0, ri), (-1, ri), 10)]
        elif s == "opening" or s == "closing":
            ts += [("BACKGROUND", (0, ri), (-1, ri), C_DARK),
                   ("TEXTCOLOR",  (0, ri), (-1, ri), C_WHITE),
                   ("FONTNAME",   (0, ri), (-1, ri), "Helvetica-Bold")]
        elif s == "empty":
            ts += [("BACKGROUND", (0, ri), (-1, ri), C_ROW2),
                   ("LINEBELOW",  (0, ri), (-1, ri), 0, C_ROW2)]
        else:
            bg = C_ROW1 if ri % 2 == 0 else C_ROW2
            ts += [("BACKGROUND", (0, ri), (-1, ri), bg)]

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle(ts))
    return tbl

# ── Generic multi-column PDF table (Trial Balance, Aging) ─────────────────────

def _multi_col_pdf(col_headers, rows, col_widths):
    table_data = [col_headers]
    ts = [
        ("BACKGROUND",    (0, 0), (-1, 0), C_DARK),
        ("TEXTCOLOR",     (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 8),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
    ]
    for i, row in enumerate(rows):
        ri = i + 1
        cells = [str(c) if c is not None else "" for c in row["cells"]]
        table_data.append(cells)
        s = row.get("style", "data")
        if s == "total":
            ts += [("BACKGROUND", (0, ri), (-1, ri), C_MID),
                   ("TEXTCOLOR",  (0, ri), (-1, ri), C_WHITE),
                   ("FONTNAME",   (0, ri), (-1, ri), "Helvetica-Bold"),
                   ("LINEABOVE",  (0, ri), (-1, ri), 0.5, C_DARK)]
        elif s == "highlight":
            ts += [("BACKGROUND", (0, ri), (-1, ri), C_GREEN),
                   ("TEXTCOLOR",  (0, ri), (-1, ri), C_WHITE),
                   ("FONTNAME",   (0, ri), (-1, ri), "Helvetica-Bold")]
        else:
            bg = C_ROW1 if ri % 2 == 0 else C_ROW2
            ts += [("BACKGROUND", (0, ri), (-1, ri), bg)]
        # Align numeric columns right
        for ci, h in enumerate(col_headers):
            if any(x in h for x in ("₹", "Days", "Amount", "Debit", "Credit", "Total")):
                ts += [("ALIGN", (ci, ri), (ci, ri), "RIGHT")]

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle(ts))
    return tbl

# ══════════════════════════════════════════════════════════════════════════════
# P & L
# ══════════════════════════════════════════════════════════════════════════════

def _pl_rows(data):
    rows = []
    rows.append({"cells": ["INCOME", ""], "style": "section"})
    for name, amt in data["income"]:
        if amt:
            rows.append({"cells": [f"  {name}", amt], "style": "data"})
    rows.append({"cells": ["Total Income", data["total_income"]], "style": "total"})
    rows.append({"cells": ["", ""], "style": "empty"})
    rows.append({"cells": ["EXPENSES", ""], "style": "section"})
    for name, amt in data["expenses"]:
        if amt:
            rows.append({"cells": [f"  {name}", amt], "style": "data"})
    rows.append({"cells": ["Total Expenses", data["total_expenses"]], "style": "total"})
    rows.append({"cells": ["", ""], "style": "empty"})
    p = data["net_profit"]
    rows.append({"cells": ["NET PROFIT" if p >= 0 else "NET LOSS", abs(p)], "style": "highlight"})
    return rows

def export_pl_pdf(data, from_date, to_date, firm, filepath):
    doc = _doc(filepath)
    elems = _report_header("PROFIT & LOSS STATEMENT",
                            f"Period: {from_date}  to  {to_date}", firm)
    elems.append(_two_col_pdf(["Account", "Amount (₹)"], _pl_rows(data)))
    doc.build(elems)

def export_pl_excel(data, from_date, to_date, firm, filepath):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "P&L"
    _xl_header(ws, "PROFIT & LOSS STATEMENT", f"Period: {from_date} to {to_date}", firm)
    _xl_two_col(ws, ["Account", "Amount (₹)"], _pl_rows(data))
    _xl_col_widths(ws, [40, 18])
    wb.save(filepath)

def export_pl_csv(data, from_date, to_date, filepath):
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Period", f"{from_date} to {to_date}"])
        w.writerow([])
        w.writerow(["INCOME"])
        for name, amt in data["income"]:
            if amt:
                w.writerow([name, amt])
        w.writerow(["Total Income", data["total_income"]])
        w.writerow([])
        w.writerow(["EXPENSES"])
        for name, amt in data["expenses"]:
            if amt:
                w.writerow([name, amt])
        w.writerow(["Total Expenses", data["total_expenses"]])
        w.writerow([])
        p = data["net_profit"]
        w.writerow(["NET PROFIT" if p >= 0 else "NET LOSS", abs(p)])

# ══════════════════════════════════════════════════════════════════════════════
# Balance Sheet
# ══════════════════════════════════════════════════════════════════════════════

def _bs_rows(data):
    rows = []
    rows.append({"cells": ["ASSETS", ""], "style": "section"})
    for a in data["assets"]:
        rows.append({"cells": [f"  {a['name']}", a["balance"]], "style": "data"})
    rows.append({"cells": ["Total Assets", data["total_assets"]], "style": "total"})
    rows.append({"cells": ["", ""], "style": "empty"})
    rows.append({"cells": ["LIABILITIES", ""], "style": "section"})
    for a in data["liabilities"]:
        rows.append({"cells": [f"  {a['name']}", a["balance"]], "style": "data"})
    rows.append({"cells": ["Total Liabilities", data["total_liab"]], "style": "total"})
    rows.append({"cells": ["", ""], "style": "empty"})
    rows.append({"cells": ["EQUITY", ""], "style": "section"})
    for a in data["equity"]:
        rows.append({"cells": [f"  {a['name']}", a["balance"]], "style": "data"})
    ni = data["net_income"]
    rows.append({"cells": [f"  Net {'Profit' if ni >= 0 else 'Loss'} (Current Period)", ni], "style": "data"})
    rows.append({"cells": ["Total Equity", data["total_equity"]], "style": "total"})
    rows.append({"cells": ["", ""], "style": "empty"})
    bal = data["total_assets"] - (data["total_liab"] + data["total_equity"])
    rows.append({"cells": ["Balanced" if abs(bal) < 0.01 else f"Difference: {bal:,.2f}",
                            data["total_liab"] + data["total_equity"]], "style": "highlight"})
    return rows

def export_bs_pdf(data, as_of, firm, filepath):
    doc = _doc(filepath)
    elems = _report_header("BALANCE SHEET", f"As at  {as_of}", firm)
    elems.append(_two_col_pdf(["Account", "Amount (₹)"], _bs_rows(data)))
    doc.build(elems)

def export_bs_excel(data, as_of, firm, filepath):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Balance Sheet"
    _xl_header(ws, "BALANCE SHEET", f"As at {as_of}", firm)
    _xl_two_col(ws, ["Account", "Amount (₹)"], _bs_rows(data))
    _xl_col_widths(ws, [40, 18])
    wb.save(filepath)

def export_bs_csv(data, as_of, filepath):
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["As at", as_of])
        w.writerow([])
        w.writerow(["ASSETS"])
        for a in data["assets"]:
            w.writerow([a["name"], a["balance"]])
        w.writerow(["Total Assets", data["total_assets"]])
        w.writerow([])
        w.writerow(["LIABILITIES"])
        for a in data["liabilities"]:
            w.writerow([a["name"], a["balance"]])
        w.writerow(["Total Liabilities", data["total_liab"]])
        w.writerow([])
        w.writerow(["EQUITY"])
        for a in data["equity"]:
            w.writerow([a["name"], a["balance"]])
        w.writerow(["Net Income (Current Period)", data["net_income"]])
        w.writerow(["Total Equity", data["total_equity"]])

# ══════════════════════════════════════════════════════════════════════════════
# Trial Balance
# ══════════════════════════════════════════════════════════════════════════════

def _tb_rows(data):
    rows = []
    for r in data["rows"]:
        dr = f"{r['debit']:,.2f}" if r["debit"] else "—"
        cr = f"{r['credit']:,.2f}" if r["credit"] else "—"
        rows.append({"cells": [r["code"], r["name"], r["account_type"], dr, cr], "style": "data"})
    rows.append({"cells": ["", "TOTALS", "",
                             f"{data['total_dr']:,.2f}",
                             f"{data['total_cr']:,.2f}"], "style": "total"})
    return rows

def export_tb_pdf(data, as_of, firm, filepath):
    doc = _doc(filepath)
    elems = _report_header("TRIAL BALANCE", f"As at  {as_of}", firm)
    col_w = [1.5*cm, 7*cm, 3*cm, 3.5*cm, 3.5*cm]
    elems.append(_multi_col_pdf(
        ["Code", "Account Name", "Type", "Debit (₹)", "Credit (₹)"],
        _tb_rows(data), col_w))
    doc.build(elems)

def export_tb_excel(data, as_of, firm, filepath):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Trial Balance"
    _xl_header(ws, "TRIAL BALANCE", f"As at {as_of}", firm)
    headers = ["Code", "Account Name", "Type", "Debit (₹)", "Credit (₹)"]
    _xl_multi_col(ws, headers, _tb_rows(data), right_cols={3, 4})
    _xl_col_widths(ws, [8, 32, 14, 16, 16])
    wb.save(filepath)

def export_tb_csv(data, as_of, filepath):
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["As at", as_of])
        w.writerow([])
        w.writerow(["Code", "Account Name", "Type", "Debit", "Credit"])
        for r in data["rows"]:
            w.writerow([r["code"], r["name"], r["account_type"],
                        r["debit"] or "", r["credit"] or ""])
        w.writerow(["", "TOTALS", "", data["total_dr"], data["total_cr"]])

# ══════════════════════════════════════════════════════════════════════════════
# Cash Flow
# ══════════════════════════════════════════════════════════════════════════════

def _cf_rows(data):
    rows = []
    rows.append({"cells": ["Opening Cash & Bank Balance", data["opening"]], "style": "opening"})
    rows.append({"cells": ["A.  OPERATING ACTIVITIES", ""], "style": "section"})
    for item in data["operating"]:
        rows.append({"cells": [f"  {item['narration']}", item["amount"]], "style": "data"})
    if not data["operating"]:
        rows.append({"cells": ["  No operating transactions", ""], "style": "data"})
    rows.append({"cells": ["Net Cash from Operating Activities", data["op_total"]], "style": "subtotal"})
    rows.append({"cells": ["", ""], "style": "empty"})
    rows.append({"cells": ["B.  INVESTING ACTIVITIES", ""], "style": "section"})
    for item in data["investing"]:
        rows.append({"cells": [f"  {item['narration']}", item["amount"]], "style": "data"})
    if not data["investing"]:
        rows.append({"cells": ["  No investing transactions", ""], "style": "data"})
    rows.append({"cells": ["Net Cash from Investing Activities", data["inv_total"]], "style": "subtotal"})
    rows.append({"cells": ["", ""], "style": "empty"})
    rows.append({"cells": ["C.  FINANCING ACTIVITIES", ""], "style": "section"})
    for item in data["financing"]:
        rows.append({"cells": [f"  {item['narration']}", item["amount"]], "style": "data"})
    if not data["financing"]:
        rows.append({"cells": ["  No financing transactions", ""], "style": "data"})
    rows.append({"cells": ["Net Cash from Financing Activities", data["fin_total"]], "style": "subtotal"})
    rows.append({"cells": ["", ""], "style": "empty"})
    net = data["net"]
    rows.append({"cells": ["NET INCREASE IN CASH" if net >= 0 else "NET DECREASE IN CASH", net],
                 "style": "highlight"})
    rows.append({"cells": ["Closing Cash & Bank Balance", data["closing"]], "style": "closing"})
    return rows

def export_cf_pdf(data, from_date, to_date, firm, filepath):
    doc = _doc(filepath)
    elems = _report_header("CASH FLOW STATEMENT",
                            f"Period: {from_date}  to  {to_date}", firm)
    elems.append(_two_col_pdf(["Description", "Amount (₹)"], _cf_rows(data)))
    doc.build(elems)

def export_cf_excel(data, from_date, to_date, firm, filepath):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cash Flow"
    _xl_header(ws, "CASH FLOW STATEMENT", f"Period: {from_date} to {to_date}", firm)
    _xl_two_col(ws, ["Description", "Amount (₹)"], _cf_rows(data))
    _xl_col_widths(ws, [50, 18])
    wb.save(filepath)

def export_cf_csv(data, from_date, to_date, filepath):
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Period", f"{from_date} to {to_date}"])
        w.writerow([])
        w.writerow(["Opening Balance", data["opening"]])
        w.writerow([])
        w.writerow(["OPERATING ACTIVITIES"])
        for item in data["operating"]:
            w.writerow([item["narration"], item["amount"]])
        w.writerow(["Net Operating", data["op_total"]])
        w.writerow([])
        w.writerow(["INVESTING ACTIVITIES"])
        for item in data["investing"]:
            w.writerow([item["narration"], item["amount"]])
        w.writerow(["Net Investing", data["inv_total"]])
        w.writerow([])
        w.writerow(["FINANCING ACTIVITIES"])
        for item in data["financing"]:
            w.writerow([item["narration"], item["amount"]])
        w.writerow(["Net Financing", data["fin_total"]])
        w.writerow([])
        w.writerow(["Net Change", data["net"]])
        w.writerow(["Closing Balance", data["closing"]])

# ══════════════════════════════════════════════════════════════════════════════
# Debtors Aging
# ══════════════════════════════════════════════════════════════════════════════

def export_aging_pdf(data, as_of, firm, filepath):
    doc = _doc(filepath, land=True)
    elems = _report_header("DEBTORS AGING REPORT", f"As at  {as_of}", firm)
    labels = data["labels"]
    col_headers = ["Client"] + labels + ["Total"]
    rows = []
    for c in data["clients"]:
        cells = [c["name"]] + [f"{v:,.2f}" if v else "—" for v in c["buckets"]] + [f"{c['total']:,.2f}"]
        rows.append({"cells": cells, "style": "data"})
    grand = (["TOTAL"] +
             [f"{v:,.2f}" if v else "—" for v in data["grand_buckets"]] +
             [f"{data['grand_total']:,.2f}"])
    rows.append({"cells": grand, "style": "total"})
    # column widths in landscape: 5 bucket cols + name + total
    n_cols = len(col_headers)
    name_w = 5*cm
    num_w  = 2.5*cm
    col_w  = [name_w] + [num_w] * (n_cols - 1)
    elems.append(_multi_col_pdf(col_headers, rows, col_w))

    # Invoice detail table
    elems.append(Spacer(1, 0.5*cm))
    elems.append(_para("Invoice Detail", 11, bold=True, color=C_DARK, align=TA_LEFT))
    elems.append(Spacer(1, 0.2*cm))
    inv_hdr = ["Invoice #", "Client", "Invoice Date", "Due Date", "Days", "Amount (₹)", "Status"]
    inv_rows = []
    all_inv = []
    for c in data["clients"]:
        for inv in c["invoices"]:
            inv["client_name"] = c["name"]
            all_inv.append(inv)
    all_inv.sort(key=lambda x: x["days_overdue"], reverse=True)
    for inv in all_inv:
        days = inv["days_overdue"]
        days_str = f"{days}" if days >= 0 else f"({abs(days)})"
        inv_rows.append({"cells": [inv["invoice_number"], inv["client_name"],
                                    inv["invoice_date"], inv["due_date"],
                                    days_str, f"{inv['amount']:,.2f}", inv["status"]],
                          "style": "data"})
    inv_col_w = [2.5*cm, 4*cm, 2.5*cm, 2.5*cm, 1.5*cm, 2.5*cm, 1.8*cm]
    elems.append(_multi_col_pdf(inv_hdr, inv_rows, inv_col_w))
    doc.build(elems)

def export_aging_excel(data, as_of, firm, filepath):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Aging Summary"
    _xl_header(ws, "DEBTORS AGING REPORT", f"As at {as_of}", firm)
    labels  = data["labels"]
    headers = ["Client"] + labels + ["Total"]
    right_cols = set(range(1, len(headers)))
    rows = []
    for c in data["clients"]:
        cells = [c["name"]] + list(c["buckets"]) + [c["total"]]
        rows.append({"cells": cells, "style": "data"})
    grand = (["TOTAL"] + list(data["grand_buckets"]) + [data["grand_total"]])
    rows.append({"cells": grand, "style": "total"})
    _xl_multi_col(ws, headers, rows, right_cols=right_cols,
                  num_fmt='#,##0.00', num_cols=right_cols)

    # Invoice detail sheet
    ws2 = wb.create_sheet("Invoice Detail")
    inv_hdr = ["Invoice #", "Client", "Invoice Date", "Due Date", "Days Overdue", "Amount (₹)", "Status"]
    all_inv = []
    for c in data["clients"]:
        for inv in c["invoices"]:
            inv["client_name"] = c["name"]
            all_inv.append(inv)
    all_inv.sort(key=lambda x: x["days_overdue"], reverse=True)
    inv_rows = []
    for inv in all_inv:
        inv_rows.append({"cells": [inv["invoice_number"], inv["client_name"],
                                    inv["invoice_date"], inv["due_date"],
                                    inv["days_overdue"], inv["amount"], inv["status"]],
                          "style": "data"})
    _xl_header(ws2, "Invoice Detail", f"As at {as_of}", firm)
    _xl_multi_col(ws2, inv_hdr, inv_rows, right_cols={4, 5}, num_cols={4, 5})
    _xl_col_widths(ws2, [14, 25, 12, 12, 13, 15, 10])
    _xl_col_widths(ws, [25] + [14] * len(labels) + [14])
    wb.save(filepath)

def export_aging_csv(data, as_of, filepath):
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["As at", as_of])
        w.writerow([])
        labels = data["labels"]
        w.writerow(["Client"] + labels + ["Total"])
        for c in data["clients"]:
            w.writerow([c["name"]] + c["buckets"] + [c["total"]])
        w.writerow(["TOTAL"] + data["grand_buckets"] + [data["grand_total"]])
        w.writerow([])
        w.writerow(["Invoice #", "Client", "Invoice Date", "Due Date",
                    "Days Overdue", "Amount", "Status"])
        for c in data["clients"]:
            for inv in c["invoices"]:
                w.writerow([inv["invoice_number"], c["name"], inv["invoice_date"],
                            inv["due_date"], inv["days_overdue"], inv["amount"], inv["status"]])

# ══════════════════════════════════════════════════════════════════════════════
# Excel helpers
# ══════════════════════════════════════════════════════════════════════════════

_XL_DARK  = "0F3460"
_XL_MID   = "16213E"
_XL_GREEN = "27AE60"
_XL_RED   = "C0392B"
_XL_BLUE  = "2980B9"
_XL_LTROW = "EAF4FB"

def _xfill(hex_color):
    return PatternFill("solid", fgColor=hex_color)

def _xl_header(ws, title, subtitle, firm):
    ws.append([firm or ""])
    ws["A1"].font = Font(bold=True, size=12, color=_XL_BLUE)
    ws.append([title])
    ws["A2"].font = Font(bold=True, size=14, color=_XL_DARK)
    ws.append([subtitle])
    ws["A3"].font = Font(size=9, color="888888")
    ws.append([])

def _xl_two_col(ws, col_headers, rows):
    # Write column headers
    ws.append(col_headers)
    hdr_row = ws.max_row
    for col in range(1, 3):
        c = ws.cell(hdr_row, col)
        c.font  = Font(bold=True, color="FFFFFF", size=10)
        c.fill  = _xfill(_XL_DARK)
        c.alignment = Alignment(horizontal="center")

    for row in rows:
        label = row["cells"][0]
        val   = row["cells"][1] if len(row["cells"]) > 1 else ""
        ws.append([label, val])
        ri = ws.max_row
        s  = row.get("style", "data")
        c1, c2 = ws.cell(ri, 1), ws.cell(ri, 2)
        c2.alignment = Alignment(horizontal="right")
        if isinstance(val, (int, float)):
            c2.number_format = '#,##0.00'
        if s == "section":
            for c in (c1, c2):
                c.font = Font(bold=True, color=_XL_BLUE, size=10)
                c.fill = _xfill(_XL_MID)
        elif s == "total":
            for c in (c1, c2):
                c.font = Font(bold=True, size=10)
                c.fill = _xfill(_XL_LTROW)
        elif s == "subtotal":
            for c in (c1, c2):
                c.font = Font(bold=True)
        elif s == "highlight":
            v = row["cells"][1] if len(row["cells"]) > 1 else 0
            fg = _XL_GREEN if (isinstance(v, (int, float)) and v >= 0) else _XL_RED
            for c in (c1, c2):
                c.font = Font(bold=True, color="FFFFFF", size=11)
                c.fill = _xfill(fg)
        elif s in ("opening", "closing"):
            for c in (c1, c2):
                c.font = Font(bold=True, color="FFFFFF")
                c.fill = _xfill(_XL_DARK)

def _xl_multi_col(ws, col_headers, rows, right_cols=None, num_fmt='#,##0.00', num_cols=None):
    right_cols = right_cols or set()
    num_cols   = num_cols or set()
    ws.append(col_headers)
    hdr_row = ws.max_row
    for col_idx in range(1, len(col_headers) + 1):
        c = ws.cell(hdr_row, col_idx)
        c.font  = Font(bold=True, color="FFFFFF", size=9)
        c.fill  = _xfill(_XL_DARK)
        c.alignment = Alignment(horizontal="center")

    for i, row in enumerate(rows):
        ws.append(row["cells"])
        ri = ws.max_row
        s  = row.get("style", "data")
        for ci in range(1, len(row["cells"]) + 1):
            c = ws.cell(ri, ci)
            if (ci - 1) in right_cols:
                c.alignment = Alignment(horizontal="right")
            if (ci - 1) in num_cols and isinstance(c.value, (int, float)):
                c.number_format = num_fmt
            if s == "total":
                c.font = Font(bold=True, color="FFFFFF")
                c.fill = _xfill(_XL_MID)
            elif i % 2 == 0:
                c.fill = _xfill(_XL_LTROW)

def _xl_col_widths(ws, widths):
    cols = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for i, w in enumerate(widths):
        ws.column_dimensions[cols[i]].width = w
    ws.freeze_panes = "A6"


# ══════════════════════════════════════════════════════════════════════════════
# GSTR-1
# ══════════════════════════════════════════════════════════════════════════════

def _gstr1_b2b_rows(data):
    rows = []
    for r in data["b2b"]:
        rows.append({"cells": [
            r["invoice_number"], r["invoice_date"], r["client_name"],
            r["client_gstin"], r["supply_type"].upper(),
            _money(r["subtotal"]), _money(r["cgst_total"]),
            _money(r["sgst_total"]), _money(r["igst_total"]),
            _money(r["grand_total"]),
        ], "style": "data"})
    t = data["b2b_total"]
    rows.append({"cells": [
        "Total B2B", "", "", "", "",
        _money(t["taxable"]), _money(t["cgst"]),
        _money(t["sgst"]), _money(t["igst"]), _money(t["grand"]),
    ], "style": "total"})
    return rows

def _gstr1_b2c_rows(data):
    rows = []
    for r in data["b2c"]:
        rows.append({"cells": [
            r["invoice_number"], r["invoice_date"], r["client_name"],
            r["supply_type"].upper(),
            _money(r["subtotal"]), _money(r["cgst_total"]),
            _money(r["sgst_total"]), _money(r["igst_total"]),
            _money(r["grand_total"]),
        ], "style": "data"})
    t = data["b2c_total"]
    rows.append({"cells": [
        "Total B2C", "", "", "",
        _money(t["taxable"]), _money(t["cgst"]),
        _money(t["sgst"]), _money(t["igst"]), _money(t["grand"]),
    ], "style": "total"})
    return rows

def _gstr1_hsn_rows(data):
    rows = []
    for r in data["hsn"]:
        rows.append({"cells": [
            r["hsn_code"] or "—", r["description"][:30] if r["description"] else "",
            r["unit"] or "", f"{r['total_qty']:.2f}",
            _money(r["taxable_value"]), _money(r["cgst"]),
            _money(r["sgst"]), _money(r["igst"]), _money(r["total_tax"]),
        ], "style": "data"})
    return rows

_B2B_HDR = ["Invoice #", "Date", "Client", "GSTIN", "Type",
            "Taxable ₹", "CGST ₹", "SGST ₹", "IGST ₹", "Total ₹"]
_B2C_HDR = ["Invoice #", "Date", "Client", "Type",
            "Taxable ₹", "CGST ₹", "SGST ₹", "IGST ₹", "Total ₹"]
_HSN_HDR = ["HSN Code", "Description", "UQC", "Qty",
            "Taxable ₹", "CGST ₹", "SGST ₹", "IGST ₹", "Total Tax ₹"]

def export_gstr1_pdf(data, from_date, to_date, firm, filepath):
    doc = _doc(filepath, land=True)
    elems = _report_header("GSTR-1  Outward Supply Details",
                           f"Period: {from_date}  to  {to_date}", firm)
    elems.append(_para("B2B Supplies (Registered Buyers)", 10, bold=True,
                       color=C_DARK, align=TA_LEFT))
    elems.append(Spacer(1, 0.2*cm))
    b2b_w = [2.4, 2, 3.4, 3.6, 1.4, 2.2, 2, 2, 2, 2.2]
    if data["b2b"]:
        elems.append(_multi_col_pdf(_B2B_HDR, _gstr1_b2b_rows(data),
                                    [w*cm for w in b2b_w]))
    else:
        elems.append(_para("No B2B invoices in this period.", 9, color=C_GREY))
    elems.append(Spacer(1, 0.4*cm))
    elems.append(_para("B2C Supplies (Unregistered Buyers)", 10, bold=True,
                       color=C_DARK, align=TA_LEFT))
    elems.append(Spacer(1, 0.2*cm))
    b2c_w = [2.4, 2, 4, 1.4, 2.4, 2.2, 2.2, 2.2, 2.4]
    if data["b2c"]:
        elems.append(_multi_col_pdf(_B2C_HDR, _gstr1_b2c_rows(data),
                                    [w*cm for w in b2c_w]))
    else:
        elems.append(_para("No B2C invoices in this period.", 9, color=C_GREY))
    elems.append(Spacer(1, 0.4*cm))
    elems.append(_para("HSN / SAC Summary", 10, bold=True,
                       color=C_DARK, align=TA_LEFT))
    elems.append(Spacer(1, 0.2*cm))
    if data["hsn"]:
        hsn_w = [2.4, 4, 1.6, 1.6, 2.6, 2.2, 2.2, 2.2, 2.4]
        elems.append(_multi_col_pdf(_HSN_HDR, _gstr1_hsn_rows(data),
                                    [w*cm for w in hsn_w]))
    else:
        elems.append(_para("No HSN data in this period.", 9, color=C_GREY))
    g = data["grand"]
    grand_rows = [{"cells": [
        "GRAND TOTAL", "", "", "", "",
        _money(g["taxable"]), _money(g["cgst"]),
        _money(g["sgst"]), _money(g["igst"]), _money(g["grand"]),
    ], "style": "total"}]
    elems.append(Spacer(1, 0.3*cm))
    elems.append(_multi_col_pdf(_B2B_HDR, grand_rows, [w*cm for w in b2b_w]))
    doc.build(elems)

def export_gstr1_excel(data, from_date, to_date, firm, filepath):
    wb = openpyxl.Workbook()
    for sheet_name, hdr, rows, widths in [
        ("B2B", _B2B_HDR, _gstr1_b2b_rows(data), [14,12,22,20,8,14,12,12,12,14]),
        ("B2C", _B2C_HDR, _gstr1_b2c_rows(data), [14,12,24,8,14,12,12,12,14]),
        ("HSN", _HSN_HDR, _gstr1_hsn_rows(data), [12,24,8,10,14,12,12,12,14]),
    ]:
        ws = wb.create_sheet(sheet_name)
        _xl_header(ws, f"GSTR-1 — {sheet_name}", f"Period: {from_date} to {to_date}", firm)
        _xl_multi_col(ws, hdr, rows,
                      right_cols={i for i, h in enumerate(hdr) if "₹" in h},
                      num_cols={i for i, h in enumerate(hdr) if "₹" in h})
        _xl_col_widths(ws, widths)
    del wb["Sheet"]
    wb.save(filepath)

def export_gstr1_csv(data, from_date, to_date, filepath):
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Period", f"{from_date} to {to_date}"])
        w.writerow([])
        w.writerow(["B2B Supplies"])
        w.writerow(_B2B_HDR)
        for r in data["b2b"]:
            w.writerow([r["invoice_number"], r["invoice_date"], r["client_name"],
                        r["client_gstin"], r["supply_type"].upper(),
                        r["subtotal"], r["cgst_total"], r["sgst_total"],
                        r["igst_total"], r["grand_total"]])
        w.writerow([])
        w.writerow(["B2C Supplies"])
        w.writerow(_B2C_HDR)
        for r in data["b2c"]:
            w.writerow([r["invoice_number"], r["invoice_date"], r["client_name"],
                        r["supply_type"].upper(),
                        r["subtotal"], r["cgst_total"], r["sgst_total"],
                        r["igst_total"], r["grand_total"]])
        w.writerow([])
        w.writerow(["HSN / SAC Summary"])
        w.writerow(_HSN_HDR)
        for r in data["hsn"]:
            w.writerow([r["hsn_code"], r["description"], r["unit"],
                        r["total_qty"], r["taxable_value"],
                        r["cgst"], r["sgst"], r["igst"], r["total_tax"]])
        g = data["grand"]
        w.writerow([])
        w.writerow(["GRAND TOTAL", "", "", "", "",
                    g["taxable"], g["cgst"], g["sgst"], g["igst"], g["grand"]])


# ══════════════════════════════════════════════════════════════════════════════
# GSTR-3B
# ══════════════════════════════════════════════════════════════════════════════

def export_gstr3b_pdf(data, from_date, to_date, firm, filepath):
    doc = _doc(filepath)
    elems = _report_header("GSTR-3B  Summary Return",
                           f"Period: {from_date}  to  {to_date}", firm)
    rows = [
        {"cells": ["3.1  Details of Outward Supplies", ""], "style": "section"},
        {"cells": ["(a) Outward taxable supplies (other than zero / nil / exempt)",
                   data["taxable_value"]], "style": "data"},
        {"cells": ["    CGST", data["cgst_out"]], "style": "data"},
        {"cells": ["    SGST / UTGST", data["sgst_out"]], "style": "data"},
        {"cells": ["    IGST", data["igst_out"]], "style": "data"},
        {"cells": ["Total Output Tax", data["total_out"]], "style": "total"},
        {"cells": ["", ""], "style": "empty"},
        {"cells": ["4.  Eligible ITC", ""], "style": "section"},
        {"cells": ["    CGST ITC", data["cgst_itc"]], "style": "data"},
        {"cells": ["    SGST / UTGST ITC", data["sgst_itc"]], "style": "data"},
        {"cells": ["    IGST ITC", data["igst_itc"]], "style": "data"},
        {"cells": ["Total ITC (purchase invoices not tracked)", data["total_itc"]],
         "style": "subtotal"},
        {"cells": ["", ""], "style": "empty"},
        {"cells": ["5.  Values of Exempt, Nil and Non-GST Inward Supplies",
                   ""], "style": "section"},
        {"cells": ["    Not applicable (no purchase tracking)", "—"], "style": "data"},
        {"cells": ["", ""], "style": "empty"},
        {"cells": ["NET GST PAYABLE", data["net_total"]], "style": "highlight"},
    ]
    elems.append(_two_col_pdf(["Description", "Amount (₹)"], rows))
    doc.build(elems)

def export_gstr3b_excel(data, from_date, to_date, firm, filepath):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "GSTR-3B"
    _xl_header(ws, "GSTR-3B Summary Return", f"Period: {from_date} to {to_date}", firm)
    rows = [
        {"cells": ["3.1  Outward Supplies", ""], "style": "section"},
        {"cells": ["Taxable Value", data["taxable_value"]], "style": "data"},
        {"cells": ["CGST", data["cgst_out"]], "style": "data"},
        {"cells": ["SGST / UTGST", data["sgst_out"]], "style": "data"},
        {"cells": ["IGST", data["igst_out"]], "style": "data"},
        {"cells": ["Total Output Tax", data["total_out"]], "style": "total"},
        {"cells": ["", ""], "style": "empty"},
        {"cells": ["4.  Eligible ITC", ""], "style": "section"},
        {"cells": ["CGST ITC", data["cgst_itc"]], "style": "data"},
        {"cells": ["SGST ITC", data["sgst_itc"]], "style": "data"},
        {"cells": ["IGST ITC", data["igst_itc"]], "style": "data"},
        {"cells": ["Total ITC (purchase invoices not tracked)", data["total_itc"]],
         "style": "subtotal"},
        {"cells": ["", ""], "style": "empty"},
        {"cells": ["NET GST PAYABLE", data["net_total"]], "style": "highlight"},
    ]
    _xl_two_col(ws, ["Description", "Amount (₹)"], rows)
    _xl_col_widths(ws, [42, 18])
    wb.save(filepath)

def export_gstr3b_csv(data, from_date, to_date, filepath):
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Period", f"{from_date} to {to_date}"])
        w.writerow([])
        w.writerow(["3.1 Outward Supplies"])
        w.writerow(["Taxable Value", data["taxable_value"]])
        w.writerow(["CGST", data["cgst_out"]])
        w.writerow(["SGST / UTGST", data["sgst_out"]])
        w.writerow(["IGST", data["igst_out"]])
        w.writerow(["Total Output Tax", data["total_out"]])
        w.writerow([])
        w.writerow(["4. Eligible ITC"])
        w.writerow(["CGST ITC", data["cgst_itc"]])
        w.writerow(["SGST ITC", data["sgst_itc"]])
        w.writerow(["IGST ITC", data["igst_itc"]])
        w.writerow(["Total ITC", data["total_itc"]])
        w.writerow([])
        w.writerow(["NET GST PAYABLE", data["net_total"]])


# ── Bank Reconciliation exports ───────────────────────────────────────────────

_BANK_HDR = ["Date", "Description", "Debit", "Credit", "Matched"]
_JE_HDR   = ["Date", "Narration", "Reference", "Net Dr/Cr", "Matched"]


def _bank_rows_list(data):
    return [[r["txn_date"], r["description"], _money(r["debit"]) if r["debit"] else "",
             _money(r["credit"]) if r["credit"] else "",
             "Yes" if r["is_matched"] else "No"] for r in data["bank"]]


def _je_rows_list(data):
    return [[r["entry_date"], r["narration"], r.get("reference", ""),
             _money(r["net_dr"]) if r["net_dr"] else "",
             "Yes" if r["is_matched"] else "No"] for r in data["je"]]


def export_recon_pdf(data, account_name, from_date, to_date, firm, filepath):
    doc = _doc(filepath)
    elems = _report_header("Bank Reconciliation", f"{account_name}  |  {from_date} to {to_date}", firm)

    # Summary section
    s = data["summary"]
    diff = s["difference"]
    status = "Reconciled ✓" if abs(diff) < 0.01 else f"Difference: ₹{diff:,.2f}"
    sum_rows = [
        ["Bank Net", _money(s["bank_net"]),   "Ledger Net", _money(s["ledger_net"])],
        ["Difference", _money(diff),           "Status",     status],
        ["Bank Lines", str(s["total_bank_lines"]),
         "Unmatched Bank", str(s["unmatched_bank"])],
        ["Unmatched JE", str(s["unmatched_je"]), "", ""],
    ]
    from reportlab.platypus import Table, TableStyle, Spacer
    from reportlab.lib import colors
    elems.append(Spacer(1, 6))
    elems.append(_para("Reconciliation Summary", 11, True))
    elems.append(Spacer(1, 4))
    t = Table(sum_rows, colWidths=[100, 100, 100, 150])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR",  (0, 0), (-1, -1), colors.white),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("GRID",       (0, 0), (-1, -1), 0.3, colors.HexColor("#2c3e50")),
        ("PADDING",    (0, 0), (-1, -1), 4),
        ("FONTNAME",   (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME",   (2, 0), (2, -1), "Helvetica-Bold"),
    ]))
    elems.append(t)
    elems.append(Spacer(1, 10))

    if data["bank"]:
        elems.append(_para("Bank Statement Entries", 11, True))
        elems.append(Spacer(1, 4))
        elems += _multi_col_pdf(_BANK_HDR, _bank_rows_list(data), [60, 180, 65, 65, 45])
        elems.append(Spacer(1, 10))

    if data["je"]:
        elems.append(_para("Ledger Entries", 11, True))
        elems.append(Spacer(1, 4))
        elems += _multi_col_pdf(_JE_HDR, _je_rows_list(data), [60, 170, 80, 65, 45])

    doc.build(elems)


def export_recon_excel(data, account_name, from_date, to_date, firm, filepath):
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)

    # Summary sheet
    ws = wb.create_sheet("Summary")
    _xl_header(ws, "Bank Reconciliation", f"{account_name}  |  {from_date} to {to_date}", firm)
    s = data["summary"]
    diff = s["difference"]
    ws.append(["Metric", "Value"])
    for k, v in [("Bank Net", s["bank_net"]), ("Ledger Net", s["ledger_net"]),
                 ("Difference", diff), ("Status", "Reconciled" if abs(diff) < 0.01 else "Open"),
                 ("Bank Lines", s["total_bank_lines"]),
                 ("Unmatched Bank", s["unmatched_bank"]),
                 ("Unmatched JE", s["unmatched_je"])]:
        ws.append([k, v])
    _xl_col_widths(ws, [25, 20])

    # Bank sheet
    if data["bank"]:
        ws2 = wb.create_sheet("Bank Statement")
        _xl_header(ws2, "Bank Statement", f"{account_name}  |  {from_date} to {to_date}", firm)
        _xl_multi_col(ws2, _BANK_HDR, _bank_rows_list(data), [2, 3, 4], 5)
        _xl_col_widths(ws2, [12, 35, 12, 12, 10])

    # JE sheet
    if data["je"]:
        ws3 = wb.create_sheet("Ledger Entries")
        _xl_header(ws3, "Ledger Entries", f"{account_name}  |  {from_date} to {to_date}", firm)
        _xl_multi_col(ws3, _JE_HDR, _je_rows_list(data), [3, 4], 5)
        _xl_col_widths(ws3, [12, 30, 20, 14, 10])

    wb.save(filepath)


def export_recon_csv(data, account_name, from_date, to_date, filepath):
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Bank Reconciliation"])
        w.writerow(["Account", account_name, "Period", f"{from_date} to {to_date}"])
        s = data["summary"]
        w.writerow(["Bank Net", s["bank_net"], "Ledger Net", s["ledger_net"],
                    "Difference", s["difference"]])
        w.writerow([])
        w.writerow(["-- Bank Statement --"])
        w.writerow(_BANK_HDR)
        for r in _bank_rows_list(data):
            w.writerow(r)
        w.writerow([])
        w.writerow(["-- Ledger Entries --"])
        w.writerow(_JE_HDR)
        for r in _je_rows_list(data):
            w.writerow(r)


# ── Invoice List Exports ───────────────────────────────────────────────────────

_INV_HDR = ["Invoice No.", "Client", "Date", "Due Date",
            "Taxable (₹)", "Tax (₹)", "Discount (₹)", "Grand Total (₹)", "Status"]

def _inv_rows(invoices):
    rows = []
    for inv in invoices:
        tax = (inv.get("cgst_total") or 0) + (inv.get("sgst_total") or 0) + (inv.get("igst_total") or 0)
        rows.append([
            inv.get("invoice_number", ""),
            inv.get("client_name", ""),
            inv.get("invoice_date", ""),
            inv.get("due_date", ""),
            round(inv.get("subtotal", 0), 2),
            round(tax, 2),
            round(inv.get("discount_amt", 0), 2),
            round(inv.get("grand_total", 0), 2),
            inv.get("status", ""),
        ])
    return rows


def export_invoice_list_pdf(invoices, firm, filepath):
    firm_name = (firm.get("firm_name") or "") if firm else ""
    doc = _doc(filepath)
    elems = _report_header("Invoice List", f"All Invoices  ·  {len(invoices)} records", firm_name)

    col_w = [3.0*cm, 3.8*cm, 2.0*cm, 2.0*cm, 2.5*cm, 2.2*cm, 2.2*cm, 2.5*cm, 1.8*cm]
    table_data = [_INV_HDR] + _inv_rows(invoices)

    status_colors = {"Paid": C_GREEN, "Sent": C_BLUE, "Cancelled": C_RED}
    ts = [
        ("BACKGROUND", (0, 0), (-1, 0), C_DARK),
        ("TEXTCOLOR",  (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, 0), 8),
        ("FONTNAME",   (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",   (0, 1), (-1, -1), 7.5),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID",       (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
        ("ALIGN",      (4, 0), (7, -1), "RIGHT"),
        ("ALIGN",      (8, 0), (8, -1), "CENTER"),
    ]
    for i, inv in enumerate(invoices, start=1):
        bg = C_ROW1 if i % 2 == 0 else C_ROW2
        ts.append(("BACKGROUND", (0, i), (-1, i), bg))

    elems.append(Table(table_data, colWidths=col_w, style=TableStyle(ts), repeatRows=1))
    doc.build(elems)


def export_invoice_list_excel(invoices, firm, filepath):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Invoices"

    hdr_fill = PatternFill("solid", fgColor="0F3460")
    hdr_font = Font(bold=True, color="FFFFFF", size=10)
    for ci, h in enumerate(_INV_HDR, 1):
        cell = ws.cell(row=1, column=ci, value=h)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.alignment = Alignment(horizontal="center")

    status_colors_xl = {"Paid": "27AE60", "Sent": "2980B9",
                        "Cancelled": "C0392B", "Draft": "95A5A6"}
    for ri, row in enumerate(_inv_rows(invoices), start=2):
        bg = "EAF4FB" if ri % 2 == 0 else "FFFFFF"
        fill = PatternFill("solid", fgColor=bg)
        status = row[-1]
        sc = status_colors_xl.get(status, "1A1A2E")
        for ci, val in enumerate(row, 1):
            cell = ws.cell(row=ri, column=ci, value=val)
            cell.fill = fill
            if ci == len(row):
                cell.font = Font(bold=True, color=sc)
            if ci in (5, 6, 7, 8):
                cell.number_format = '#,##0.00'
                cell.alignment = Alignment(horizontal="right")

    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 12
    ws.column_dimensions["D"].width = 12
    for col in "EFGHI":
        ws.column_dimensions[col].width = 14

    # Totals row
    tr = len(invoices) + 2
    ws.cell(row=tr, column=4, value="TOTAL").font = Font(bold=True)
    for ci in (5, 6, 7, 8):
        col_letter = ["", "A", "B", "C", "D", "E", "F", "G", "H", "I"][ci]
        ws.cell(row=tr, column=ci,
                value=f"=SUM({col_letter}2:{col_letter}{tr-1})"
                ).font = Font(bold=True)

    wb.save(filepath)


# ── Expense Exports ────────────────────────────────────────────────────────────

_EXP_HDR = ["Date", "Account", "Paid From", "Description", "Reference", "Amount (₹)"]


def _exp_rows(entries):
    return [[e.get("entry_date",""), e.get("expense_account",""),
             e.get("paid_from",""), e.get("narration",""),
             e.get("reference",""), round(e.get("amount",0), 2)]
            for e in entries]


def export_expense_pdf(entries, summary, from_date, to_date, firm, filepath):
    firm_name = (firm.get("firm_name") or "") if firm else ""
    doc = _doc(filepath, land=True)
    elems = _report_header(
        "Expense Report",
        f"{from_date}  to  {to_date}  ·  {len(entries)} entries  ·  "
        f"Total ₹{sum(e.get('amount',0) for e in entries):,.2f}",
        firm_name,
    )

    # Category summary table
    if summary:
        elems.append(_para("Spend by Category", 11, bold=True, color=C_DARK, align=TA_LEFT))
        elems.append(Spacer(1, 0.2*cm))
        cat_data = [["Category", "Amount (₹)"]]
        for r in summary:
            cat_data.append([r.get("account_name",""), _money(r.get("total",0))])
        cat_data.append(["TOTAL", _money(sum(r.get("total",0) for r in summary))])
        cat_ts = TableStyle([
            ("BACKGROUND", (0,0),(-1,0), C_DARK), ("TEXTCOLOR",(0,0),(-1,0), C_WHITE),
            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"), ("FONTSIZE",(0,0),(-1,0),9),
            ("FONTNAME",(0,1),(-1,-2),"Helvetica"), ("FONTSIZE",(0,1),(-1,-2),8.5),
            ("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),
            ("BACKGROUND",(0,-1),(-1,-1), C_MID), ("TEXTCOLOR",(0,-1),(-1,-1), C_GREEN),
            ("ALIGN",(1,0),(1,-1),"RIGHT"),
            ("GRID",(0,0),(-1,-1),0.3, colors.HexColor("#dddddd")),
            ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4),
        ])
        elems.append(Table(cat_data, colWidths=[8*cm,3*cm], style=cat_ts))
        elems.append(Spacer(1, 0.4*cm))

    # Detail table
    elems.append(_para("Expense Detail", 11, bold=True, color=C_DARK, align=TA_LEFT))
    elems.append(Spacer(1, 0.2*cm))
    col_w = [2.0*cm, 3.5*cm, 3.0*cm, 7.0*cm, 2.5*cm, 2.5*cm]
    tdata = [_EXP_HDR] + _exp_rows(entries)
    ts = [
        ("BACKGROUND",(0,0),(-1,0), C_DARK), ("TEXTCOLOR",(0,0),(-1,0), C_WHITE),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"), ("FONTSIZE",(0,0),(-1,0),8),
        ("FONTNAME",(0,1),(-1,-1),"Helvetica"), ("FONTSIZE",(0,1),(-1,-1),7.5),
        ("ALIGN",(5,0),(5,-1),"RIGHT"),
        ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("GRID",(0,0),(-1,-1),0.3, colors.HexColor("#dddddd")),
    ]
    for i in range(1, len(tdata)):
        bg = C_ROW1 if i % 2 == 0 else C_ROW2
        ts.append(("BACKGROUND",(0,i),(-1,i), bg))
    elems.append(Table(tdata, colWidths=col_w, style=TableStyle(ts), repeatRows=1))
    doc.build(elems)


def export_expense_excel(entries, summary, from_date, to_date, firm, filepath):
    wb = openpyxl.Workbook()

    # Summary sheet
    ws_s = wb.active
    ws_s.title = "Summary"
    hdr_fill = PatternFill("solid", fgColor="0F3460")
    hdr_font = Font(bold=True, color="FFFFFF", size=10)
    for ci, h in enumerate(["Category", "Amount (₹)"], 1):
        c = ws_s.cell(row=1, column=ci, value=h)
        c.fill = hdr_fill; c.font = hdr_font
    for ri, r in enumerate(summary, 2):
        ws_s.cell(row=ri, column=1, value=r.get("account_name",""))
        amtc = ws_s.cell(row=ri, column=2, value=round(r.get("total",0),2))
        amtc.number_format = '#,##0.00'
        amtc.alignment = Alignment(horizontal="right")
    tr = len(summary) + 2
    ws_s.cell(row=tr, column=1, value="TOTAL").font = Font(bold=True)
    total_c = ws_s.cell(row=tr, column=2, value=f"=SUM(B2:B{tr-1})")
    total_c.font = Font(bold=True, color="27AE60")
    total_c.number_format = '#,##0.00'
    ws_s.column_dimensions["A"].width = 28
    ws_s.column_dimensions["B"].width = 16

    # Detail sheet
    ws_d = wb.create_sheet("Expenses")
    for ci, h in enumerate(_EXP_HDR, 1):
        c = ws_d.cell(row=1, column=ci, value=h)
        c.fill = hdr_fill; c.font = hdr_font
    for ri, row in enumerate(_exp_rows(entries), 2):
        bg = "EAF4FB" if ri % 2 == 0 else "FFFFFF"
        fill = PatternFill("solid", fgColor=bg)
        for ci, val in enumerate(row, 1):
            cell = ws_d.cell(row=ri, column=ci, value=val)
            cell.fill = fill
            if ci == 6:
                cell.number_format = '#,##0.00'
                cell.alignment = Alignment(horizontal="right")
    # Total row
    tr = len(entries) + 2
    ws_d.cell(row=tr, column=5, value="TOTAL").font = Font(bold=True)
    tc = ws_d.cell(row=tr, column=6, value=f"=SUM(F2:F{tr-1})")
    tc.font = Font(bold=True, color="C0392B"); tc.number_format = '#,##0.00'
    for col, w in zip("ABCDEF", [12, 22, 20, 36, 14, 14]):
        ws_d.column_dimensions[col].width = w

    wb.save(filepath)


# ── Client Ledger Exports ─────────────────────────────────────────────────────

_CL_HDR = ["Date", "Reference", "Type", "Debit (₹)", "Credit (₹)", "Balance (₹)"]


def _cl_rows(data):
    rows = [["Opening Balance", "", "B/F", "", "", f"{data['opening']:,.2f}"]]
    for r in data["rows"]:
        rows.append([
            r["txn_date"],
            r["ref"],
            r["txn_type"],
            f"{r['debit']:,.2f}" if r["debit"] else "",
            f"{r['credit']:,.2f}" if r["credit"] else "",
            f"{r['balance']:,.2f}",
        ])
    return rows


def export_client_ledger_pdf(data, firm, filepath):
    client = data["client"]
    subtitle = (f"{client.get('name', '')}   |   "
                f"{data['from_date']} to {data['to_date']}")
    story = _report_header("Client Ledger Statement", subtitle, firm)
    col_w = [70, 110, 60, 80, 80, 80]
    rows  = _cl_rows(data)
    rows.append(["", "TOTALS", "",
                 f"{data['total_debit']:,.2f}",
                 f"{data['total_credit']:,.2f}",
                 f"{data['closing']:,.2f}"])
    story += _multi_col_pdf(_CL_HDR, rows, col_w)
    doc = _doc(filepath)
    doc.build(story)


def export_client_ledger_excel(data, firm, filepath):
    client = data["client"]
    wb  = openpyxl.Workbook()
    ws  = wb.active
    ws.title = "Client Ledger"
    hdr_fill = PatternFill("solid", fgColor="0F3460")
    hdr_font = Font(bold=True, color="FFFFFF", size=10)

    ws.merge_cells("A1:F1")
    ws["A1"] = f"Client Ledger — {client.get('name', '')} — {data['from_date']} to {data['to_date']}"
    ws["A1"].font = Font(bold=True, size=12)

    for ci, h in enumerate(_CL_HDR, 1):
        c = ws.cell(row=2, column=ci, value=h)
        c.fill = hdr_fill; c.font = hdr_font

    ws.cell(row=3, column=1, value=data["from_date"])
    ws.cell(row=3, column=2, value="Opening Balance")
    ws.cell(row=3, column=3, value="B/F")
    ob_c = ws.cell(row=3, column=6, value=data["opening"])
    ob_c.number_format = '#,##0.00'

    for ri, r in enumerate(data["rows"], 4):
        bg = "EAF4FB" if ri % 2 == 0 else "FFFFFF"
        fill = PatternFill("solid", fgColor=bg)
        vals = [r["txn_date"], r["ref"], r["txn_type"],
                r["debit"] or None, r["credit"] or None, r["balance"]]
        for ci, v in enumerate(vals, 1):
            cell = ws.cell(row=ri, column=ci, value=v)
            cell.fill = fill
            if ci in (4, 5, 6) and v is not None:
                cell.number_format = '#,##0.00'
                cell.alignment = Alignment(horizontal="right")

    tr = len(data["rows"]) + 4
    ws.cell(row=tr, column=2, value="TOTALS").font = Font(bold=True)
    for ci, v in [(4, data["total_debit"]), (5, data["total_credit"]), (6, data["closing"])]:
        c = ws.cell(row=tr, column=ci, value=v)
        c.font = Font(bold=True, color="27AE60" if ci == 5 else "2980B9" if ci == 4 else "C0392B")
        c.number_format = '#,##0.00'

    for col, w in zip("ABCDEF", [12, 22, 10, 14, 14, 14]):
        ws.column_dimensions[col].width = w
    wb.save(filepath)


def export_client_ledger_csv(data, filepath):
    client = data["client"]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([f"Client Ledger — {client.get('name', '')}"])
        writer.writerow([f"Period: {data['from_date']} to {data['to_date']}"])
        writer.writerow([])
        writer.writerow(_CL_HDR)
        writer.writerow([data["from_date"], "Opening Balance", "B/F", "", "", data["opening"]])
        for r in data["rows"]:
            writer.writerow([r["txn_date"], r["ref"], r["txn_type"],
                             r["debit"] or "", r["credit"] or "", r["balance"]])
        writer.writerow([])
        writer.writerow(["", "TOTALS", "",
                         data["total_debit"], data["total_credit"], data["closing"]])


# ── Stock Valuation Exports ───────────────────────────────────────────────────

_SV_HDR = ["SKU", "Product Name", "HSN Code", "Unit", "Qty",
           "Cost Price", "Sale Price", "Cost Value", "Sale Value", "Margin %"]


def export_stock_valuation_pdf(data, firm, filepath):
    from datetime import datetime as _dt
    subtitle = f"As at {_dt.now().strftime('%d %b %Y')}   |   {data['item_count']} products"
    story = _report_header("Stock Valuation Report", subtitle, firm)
    col_w = [60, 130, 55, 40, 35, 65, 65, 75, 75, 55]
    rows = []
    for it in data["items"]:
        rows.append([
            it["sku"], it["name"][:30], it.get("hsn_code") or "—",
            it.get("unit") or "pcs", str(it["stock_quantity"]),
            f"{it['cost']:,.2f}", f"{it['unit_price']:,.2f}",
            f"{it['cost_value']:,.2f}", f"{it['sale_value']:,.2f}",
            f"{it['margin_pct']:.1f}%",
        ])
    rows.append([
        "", "TOTAL", "", "", "",
        "", "",
        f"{data['total_cost_value']:,.2f}",
        f"{data['total_sale_value']:,.2f}",
        f"{data['total_margin_pct']:.1f}%",
    ])
    story += _multi_col_pdf(_SV_HDR, rows, col_w)
    doc = _doc(filepath)
    doc.build(story)


def export_stock_valuation_excel(data, firm, filepath):
    import datetime as _datetime
    wb = Workbook()
    ws = wb.active
    ws.title = "Stock Valuation"
    firm_name = firm.get("firm_name", "") if firm else ""
    ws.append([firm_name])
    ws.append(["Stock Valuation Report"])
    ws.append([f"Generated: {_datetime.datetime.now().strftime('%d %b %Y %H:%M')}"])
    ws.append([])
    ws.append(_SV_HDR)
    hdr_row = ws.max_row
    for it in data["items"]:
        ws.append(_safe_row([
            it["sku"], it["name"], it.get("hsn_code") or "",
            it.get("unit") or "pcs", it["stock_quantity"],
            it["cost"], it["unit_price"],
            it["cost_value"], it["sale_value"],
            it["margin_pct"],
        ]))
    tr = ws.max_row + 1
    ws.cell(row=tr, column=1, value="TOTAL")
    ws.cell(row=tr, column=8, value=data["total_cost_value"])
    ws.cell(row=tr, column=9, value=data["total_sale_value"])
    ws.cell(row=tr, column=10, value=data["total_margin_pct"])
    for cell in ws[hdr_row]:
        cell.fill = PatternFill("solid", fgColor="0F3460")
        cell.font = Font(bold=True, color="FFFFFF")
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = max(
            (len(str(c.value)) for c in col if c.value), default=10) + 4
    wb.save(filepath)


def export_stock_valuation_csv(data, filepath):
    import datetime as _datetime
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Stock Valuation Report"])
        writer.writerow([f"Generated: {_datetime.datetime.now().strftime('%d %b %Y %H:%M')}"])
        writer.writerow([])
        writer.writerow(_SV_HDR)
        for it in data["items"]:
            writer.writerow([
                it["sku"], it["name"], it.get("hsn_code") or "",
                it.get("unit") or "pcs", it["stock_quantity"],
                it["cost"], it["unit_price"],
                it["cost_value"], it["sale_value"],
                it["margin_pct"],
            ])
        writer.writerow([])
        writer.writerow(["TOTAL", "", "", "", "",
                         "", "",
                         data["total_cost_value"],
                         data["total_sale_value"],
                         data["total_margin_pct"]])


# ── Sales Summary Exports ────────────────────────────────────────────────────

_SS_HDR = ["Period", "Invoices", "Revenue (₹)", "Avg Order (₹)"]


def export_sales_summary_pdf(data, firm, filepath):
    from datetime import datetime as _dt
    subtitle = (f"{data['from_date']} to {data['to_date']}  |  "
                f"Group by: {data['group_by']}  |  "
                f"Total: ₹{data['total_revenue']:,.2f}")
    story = _report_header("Sales Summary Report", subtitle, firm)
    col_w = [120, 70, 110, 110]
    rows = [[r["period"], str(r["invoice_count"]),
             f"{r['revenue']:,.2f}", f"{r['avg_order']:,.2f}"]
            for r in data["rows"]]
    rows.append(["TOTAL", str(data["total_invoices"]),
                 f"{data['total_revenue']:,.2f}", ""])
    story += _multi_col_pdf(_SS_HDR, rows, col_w)
    doc = _doc(filepath)
    doc.build(story)


def export_sales_summary_excel(data, firm, filepath):
    import datetime as _dt
    wb = Workbook()
    ws = wb.active
    ws.title = "Sales Summary"
    firm_name = firm.get("firm_name", "") if firm else ""
    ws.append([firm_name])
    ws.append(["Sales Summary Report"])
    ws.append([f"Period: {data['from_date']} to {data['to_date']}  |  Group: {data['group_by']}"])
    ws.append([f"Generated: {_dt.datetime.now().strftime('%d %b %Y %H:%M')}"])
    ws.append([])
    ws.append(_SS_HDR)
    hdr_row = ws.max_row
    for r in data["rows"]:
        ws.append([r["period"], r["invoice_count"], r["revenue"], r["avg_order"]])
    tr = ws.max_row + 1
    ws.cell(row=tr, column=1, value="TOTAL")
    ws.cell(row=tr, column=2, value=data["total_invoices"])
    ws.cell(row=tr, column=3, value=data["total_revenue"])
    for cell in ws[hdr_row]:
        cell.fill = PatternFill("solid", fgColor="0F3460")
        cell.font = Font(bold=True, color="FFFFFF")
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = max(
            (len(str(c.value)) for c in col if c.value), default=10) + 4

    # Top clients sheet
    if data.get("top_clients"):
        ws2 = wb.create_sheet("Top Clients")
        ws2.append(["Client", "Invoices", "Revenue (₹)"])
        for c in data["top_clients"]:
            ws2.append([c["name"], c["cnt"], c["revenue"]])

    # Top products sheet
    if data.get("top_products"):
        ws3 = wb.create_sheet("Top Products")
        ws3.append(["Product", "Qty Sold", "Revenue (₹)"])
        for p in data["top_products"]:
            ws3.append([p["description"], p["qty"], p["revenue"]])

    wb.save(filepath)


def export_sales_summary_csv(data, filepath):
    import datetime as _dt
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Sales Summary Report"])
        writer.writerow([f"Period: {data['from_date']} to {data['to_date']}"])
        writer.writerow([f"Group by: {data['group_by']}"])
        writer.writerow([])
        writer.writerow(_SS_HDR)
        for r in data["rows"]:
            writer.writerow([r["period"], r["invoice_count"], r["revenue"], r["avg_order"]])
        writer.writerow([])
        writer.writerow(["TOTAL", data["total_invoices"], data["total_revenue"], ""])
        writer.writerow([])
        writer.writerow(["Top Clients", "", "", ""])
        writer.writerow(["Client", "Invoices", "Revenue", ""])
        for c in data.get("top_clients", []):
            writer.writerow([c["name"], c["cnt"], c["revenue"], ""])
        writer.writerow([])
        writer.writerow(["Top Products", "", "", ""])
        writer.writerow(["Product", "Qty", "Revenue", ""])
        for p in data.get("top_products", []):
            writer.writerow([p["description"], p["qty"], p["revenue"], ""])


# ══════════════════════════════════════════════════════════════════════════════
# Payments Received
# ══════════════════════════════════════════════════════════════════════════════

_PMT_HDR = ["Date", "Invoice #", "Client", "Amount (₹)", "Mode", "Reference"]
_PMT_CW  = [2.5*cm, 2.5*cm, 5*cm, 2.5*cm, 2.5*cm, 4*cm]  # landscape total ~19cm


def _pmt_ref(p):
    n = p.get("narration", "")
    return n.split("– Ref: ", 1)[1] if "– Ref: " in n else "—"


def export_payment_receipt_pdf(payment, invoice, firm, filepath):
    """Generate a single A5 payment receipt PDF."""
    from reportlab.lib.pagesizes import A5
    from reportlab.lib.units import cm as _cm

    doc = SimpleDocTemplate(
        filepath, pagesize=A5,
        leftMargin=1.5*_cm, rightMargin=1.5*_cm,
        topMargin=1.5*_cm, bottomMargin=1.5*_cm,
    )
    firm_name = (firm.get("firm_name") or "") if firm else ""
    story = _report_header("PAYMENT RECEIPT", "", firm_name)

    pay_date    = payment.get("payment_date", "")
    inv_number  = payment.get("invoice_number", "")
    client_name = payment.get("client_name", "")
    amount      = float(payment.get("amount", 0))
    mode        = payment.get("payment_mode", "—")
    ref         = _pmt_ref(payment)

    try:
        from invoice_pdf import amount_in_words
        words = amount_in_words(amount).title()
    except Exception:
        words = ""

    tbl_data = [
        ["Field", "Value"],
        ["Receipt Date", pay_date],
        ["Invoice #", inv_number],
        ["Client", client_name],
        ["Amount Received", f"₹ {amount:,.2f}"],
        ["Amount in Words", words],
        ["Payment Mode", mode],
        ["Reference", ref],
    ]
    colw = [4.5*_cm, 8.5*_cm]
    t = Table(tbl_data, colWidths=colw)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), C_DARK),
        ("TEXTCOLOR",     (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME",      (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 10),
        ("BACKGROUND",    (0, 4), (-1, 4), colors.HexColor("#e8f8f5")),
        ("TEXTCOLOR",     (0, 4), (-1, 4), C_GREEN),
        ("FONTNAME",      (0, 4), (-1, 4), "Helvetica-Bold"),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_ROW1, C_ROW2]),
        ("GRID",          (0, 0), (-1, -1), 0.4, C_GREY),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 1*_cm))
    story.append(_para("— Authorised Signatory —", 9, color=C_GREY))
    doc.build(story)


def export_payments_pdf(payments, firm, filepath):
    firm_name  = (firm.get("firm_name") or "") if firm else ""
    total      = sum(p["amount"] for p in payments)
    doc        = _doc(filepath, land=True)
    story      = _report_header(
        "PAYMENTS RECEIVED",
        f"{len(payments)} payment(s)  |  Total: ₹ {total:,.2f}",
        firm_name,
    )
    rows = [{"cells": [p.get("payment_date", ""), p.get("invoice_number", ""),
                       p.get("client_name", ""), f"{p['amount']:,.2f}",
                       p.get("payment_mode", ""), _pmt_ref(p)],
             "style": "data"} for p in payments]
    rows.append({"cells": ["TOTAL", "", "", f"{total:,.2f}", "", ""], "style": "total"})
    story.append(_multi_col_pdf(_PMT_HDR, rows, _PMT_CW))
    doc.build(story)


def export_payments_excel(payments, firm, filepath):
    firm_name = (firm.get("firm_name") or "") if firm else ""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Payments Received"
    hdr_fill = PatternFill("solid", fgColor="0F3460")
    hdr_font = Font(color="FFFFFF", bold=True, size=10)
    if firm_name:
        ws.append([firm_name])
        ws["A1"].font = Font(bold=True, size=12)
    ws.append(["PAYMENTS RECEIVED"])
    ws.append([])
    ws.append(_PMT_HDR)
    hdr_row = ws.max_row
    for cell in ws[hdr_row]:
        cell.fill = hdr_fill
        cell.font = hdr_font
    for p in payments:
        ws.append(_safe_row([p.get("payment_date", ""), p.get("invoice_number", ""),
                             p.get("client_name", ""), p["amount"],
                             p.get("payment_mode", ""), _pmt_ref(p)]))
    total_row = ws.max_row + 1
    ws.append(["TOTAL", "", "", sum(p["amount"] for p in payments), "", ""])
    for cell in ws[total_row]:
        cell.font = Font(bold=True)
    for col_idx, w in enumerate([14, 14, 28, 14, 14, 24], 1):
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = w
    wb.save(filepath)


def export_payments_csv(payments, filepath):
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Payments Received"])
        writer.writerow([])
        writer.writerow(_PMT_HDR)
        for p in payments:
            writer.writerow([p.get("payment_date", ""), p.get("invoice_number", ""),
                             p.get("client_name", ""), p["amount"],
                             p.get("payment_mode", ""), _pmt_ref(p)])
        writer.writerow([])
        writer.writerow(["TOTAL", "", "", sum(p["amount"] for p in payments), "", ""])


# ── Purchases ─────────────────────────────────────────────────────────────────

_PUR_HDR = ["Date", "Bill #", "Vendor", "Subtotal (₹)", "GST (₹)", "Grand Total (₹)", "Status"]
_PUR_CW  = [2.2*cm, 2.5*cm, 5*cm, 2.5*cm, 2.2*cm, 2.8*cm, 2*cm]  # landscape


def export_purchases_pdf(purchases, firm, filepath):
    rows = []
    for p in purchases:
        gst_p = p.get("cgst_total", 0) + p.get("sgst_total", 0) + p.get("igst_total", 0)
        rows.append({"cells": [
            str(p.get("bill_date", "")),
            str(p.get("bill_number", "") or "—"),
            str(p.get("vendor_name", "") or "—"),
            f"{p.get('subtotal', 0):,.2f}",
            f"{gst_p:,.2f}",
            f"{p.get('grand_total', 0):,.2f}",
            str(p.get("status", "")),
        ], "style": "data"})
    grand = sum(p.get("grand_total", 0) for p in purchases)
    rows.append({"cells": ["Total", "", "", "", "", f"{grand:,.2f}", ""], "style": "total"})

    firm_name = firm.get("firm_name", "") if firm else ""
    elems = _report_header("Purchases Register", "", firm_name)
    elems += _multi_col_pdf(_PUR_HDR, rows, _PUR_CW)
    doc = _doc(filepath, land=True)
    doc.build(elems)


def export_purchases_excel(purchases, firm, filepath):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Purchases"

    firm_name = firm.get("firm_name", "Purchases Register") if firm else "Purchases Register"
    ws.append([firm_name])
    ws["A1"].font = openpyxl.styles.Font(bold=True, size=14)
    ws.append(["Purchases Register"])
    ws.append([])
    ws.append(_PUR_HDR)

    hdr_fill = openpyxl.styles.PatternFill("solid", fgColor="8E44AD")
    hdr_font = openpyxl.styles.Font(bold=True, color="FFFFFF")
    for cell in ws[4]:
        cell.fill = hdr_fill
        cell.font = hdr_font

    for p in purchases:
        gst_p = p.get("cgst_total", 0) + p.get("sgst_total", 0) + p.get("igst_total", 0)
        ws.append(_safe_row([
            p.get("bill_date", ""),
            p.get("bill_number", "") or "—",
            p.get("vendor_name", "") or "—",
            round(p.get("subtotal", 0), 2),
            round(gst_p, 2),
            round(p.get("grand_total", 0), 2),
            p.get("status", ""),
        ]))

    grand = sum(p.get("grand_total", 0) for p in purchases)
    ws.append(["TOTAL", "", "", "", "", round(grand, 2), ""])
    last = ws.max_row
    tot_font = openpyxl.styles.Font(bold=True)
    for cell in ws[last]:
        cell.font = tot_font

    for col, w in zip(["A","B","C","D","E","F","G"], [12, 14, 28, 14, 12, 16, 10]):
        ws.column_dimensions[col].width = w

    wb.save(filepath)


# ── TDS Export ────────────────────────────────────────────────────────────────

_TDS_HDR = ["Date", "Type", "Section", "Deductee", "PAN",
            "Taxable Amt (₹)", "Rate %", "TDS Amt (₹)", "Status"]
_TDS_CW  = [2.0*cm, 1.8*cm, 1.8*cm, 4.5*cm, 2.5*cm, 2.5*cm, 1.4*cm, 2.5*cm, 1.8*cm]


def export_tds_pdf(entries, firm, filepath):
    rows = []
    total_tds = 0.0
    for e in entries:
        total_tds += e.get("total_tds", 0)
        rows.append({"cells": [
            e.get("entry_date", ""),
            e.get("tds_type", ""),
            e.get("section", ""),
            (e.get("deductee_name") or "")[:30],
            e.get("deductee_pan") or "—",
            f"{e.get('taxable_amount', 0):,.2f}",
            f"{e.get('tds_rate', 0)}%",
            f"{e.get('total_tds', 0):,.2f}",
            e.get("status", ""),
        ], "style": "data"})
    rows.append({"cells": ["TOTAL", "", "", "", "", "", "", f"{total_tds:,.2f}", ""],
                 "style": "total"})

    doc_title = f"TDS / TCS Report — {firm.get('firm_name','')}"
    elems = _doc_header(firm, doc_title)
    elems += _multi_col_pdf(_TDS_HDR, rows, _TDS_CW)
    _build_pdf(elems, filepath, pagesize=_rl_land(A4))


def export_tds_excel(entries, firm, filepath):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "TDS Report"

    hdr_fill = PatternFill("solid", fgColor="8E44AD")
    hdr_font = Font(bold=True, color="FFFFFF")
    for ci, h in enumerate(_TDS_HDR, 1):
        cell = ws.cell(row=1, column=ci, value=h)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.alignment = Alignment(horizontal="center")

    total_tds = 0.0
    for e in entries:
        total_tds += e.get("total_tds", 0)
        ws.append([
            e.get("entry_date", ""),
            e.get("tds_type", ""),
            e.get("section", ""),
            e.get("deductee_name") or "",
            e.get("deductee_pan") or "",
            round(e.get("taxable_amount", 0), 2),
            e.get("tds_rate", 0),
            round(e.get("total_tds", 0), 2),
            e.get("status", ""),
        ])

    last = ws.max_row + 1
    ws.cell(row=last, column=1, value="TOTAL")
    ws.cell(row=last, column=8, value=round(total_tds, 2))
    for c in range(1, 10):
        ws.cell(row=last, column=c).font = Font(bold=True)

    for col, w in zip(["A","B","C","D","E","F","G","H","I"],
                      [12, 11, 12, 28, 14, 16, 8, 14, 11]):
        ws.column_dimensions[col].width = w

    wb.save(filepath)


# ── Credit / Debit Notes exports ──────────────────────────────────────────────

def export_cdn_pdf(notes, filepath):
    """Export list of Credit/Debit Notes as a landscape A4 PDF."""
    total_cn = sum(n.get("grand_total", 0) for n in notes if n.get("note_type") == "Credit")
    total_dn = sum(n.get("grand_total", 0) for n in notes if n.get("note_type") == "Debit")
    doc = _doc(filepath, land=True)
    story = _report_header(
        "CREDIT / DEBIT NOTES REGISTER",
        f"{len(notes)} note(s)  |  CN Total: ₹ {total_cn:,.2f}  |  DN Total: ₹ {total_dn:,.2f}",
        "",
    )

    col_headers = ["Note #", "Date", "Type", "Party", "Orig. Invoice",
                   "Subtotal ₹", "Tax ₹", "Grand Total ₹", "Status"]
    col_widths  = [3.0, 2.2, 1.6, 4.5, 3.0, 2.8, 2.4, 3.2, 1.8]

    rows = []
    for n in notes:
        tax = (n.get("cgst_total", 0) + n.get("sgst_total", 0)
               + n.get("igst_total", 0))
        rows.append({"cells": [
            n.get("note_number", ""),
            n.get("note_date", ""),
            n.get("note_type", ""),
            (n.get("client_name") or "—")[:30],
            n.get("original_invoice_no") or "—",
            f"{n.get('subtotal', 0):,.2f}",
            f"{tax:,.2f}",
            f"{n.get('grand_total', 0):,.2f}",
            n.get("status", ""),
        ], "style": "data"})

    rows.append({"cells": [
        "TOTAL", "", "", "", "",
        f"{sum(n.get('subtotal',0) for n in notes):,.2f}",
        f"{sum((n.get('cgst_total',0)+n.get('sgst_total',0)+n.get('igst_total',0)) for n in notes):,.2f}",
        f"{sum(n.get('grand_total',0) for n in notes):,.2f}",
        "",
    ], "style": "total"})

    story += _multi_col_pdf(col_headers, rows, col_widths)
    doc.build(story)


def export_cdn_excel(notes, filepath):
    """Export list of Credit/Debit Notes as an Excel file."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Credit Debit Notes"

    hdr_fill = PatternFill(fill_type="solid", fgColor="1A5276")   # dark blue
    hdr_font = Font(bold=True, color="FFFFFF", size=10)
    headers  = ["Note #", "Date", "Type", "Party", "Orig. Invoice",
                "Subtotal ₹", "CGST ₹", "SGST ₹", "IGST ₹", "Grand Total ₹", "Status"]
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.alignment = Alignment(horizontal="center")

    total_tds = 0.0
    for n in notes:
        ws.append([
            n.get("note_number", ""),
            n.get("note_date", ""),
            n.get("note_type", ""),
            n.get("client_name") or "",
            n.get("original_invoice_no") or "",
            round(n.get("subtotal", 0), 2),
            round(n.get("cgst_total", 0), 2),
            round(n.get("sgst_total", 0), 2),
            round(n.get("igst_total", 0), 2),
            round(n.get("grand_total", 0), 2),
            n.get("status", ""),
        ])
        total_tds += n.get("grand_total", 0)

    last = ws.max_row + 1
    ws.cell(row=last, column=1, value="TOTAL")
    ws.cell(row=last, column=10, value=round(total_tds, 2))
    for c in range(1, 12):
        ws.cell(row=last, column=c).font = Font(bold=True)

    for col, w in zip(["A","B","C","D","E","F","G","H","I","J","K"],
                      [14, 11, 10, 28, 16, 12, 10, 10, 10, 14, 10]):
        ws.column_dimensions[col].width = w

    wb.save(filepath)
