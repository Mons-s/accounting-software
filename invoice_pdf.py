"""
GST Invoice PDF Generator using ReportLab.
Generates a compliant Indian GST Tax Invoice (A4).
"""
import io
import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable, KeepTogether, Image as RLImage,
)

# ── Color palette ─────────────────────────────────────────────────────────────
C_DARK    = colors.HexColor("#0f3460")
C_MID     = colors.HexColor("#16213e")
C_ACCENT  = colors.HexColor("#e94560")
C_LIGHT   = colors.HexColor("#eaf0fb")
C_LGRAY   = colors.HexColor("#f5f5f5")
C_WHITE   = colors.white
C_BLACK   = colors.black
C_GREEN   = colors.HexColor("#27ae60")

# ── Styles ────────────────────────────────────────────────────────────────────
def _style(name, **kwargs):
    base = {"fontName": "Helvetica", "fontSize": 9, "leading": 12,
            "textColor": C_BLACK, **kwargs}
    return ParagraphStyle(name, **base)

S_FIRM_NAME = _style("firm_name", fontSize=16, fontName="Helvetica-Bold",
                      textColor=C_DARK, leading=20, alignment=TA_CENTER)
S_FIRM_SUB  = _style("firm_sub", fontSize=8, textColor=colors.HexColor("#555"),
                      alignment=TA_CENTER, leading=11)
S_TITLE     = _style("title", fontSize=13, fontName="Helvetica-Bold",
                      textColor=C_ACCENT, alignment=TA_CENTER, leading=16)
S_LABEL     = _style("label", fontSize=8, textColor=colors.HexColor("#888"))
S_VALUE     = _style("value", fontSize=9, fontName="Helvetica-Bold", textColor=C_DARK)
S_NORMAL    = _style("normal", fontSize=8, leading=11)
S_BOLD      = _style("bold", fontSize=8, fontName="Helvetica-Bold")
S_RIGHT     = _style("right", fontSize=8, alignment=TA_RIGHT)
S_RIGHT_B   = _style("right_b", fontSize=8, fontName="Helvetica-Bold", alignment=TA_RIGHT)
S_TOTAL_LBL = _style("total_lbl", fontSize=10, fontName="Helvetica-Bold",
                      textColor=C_WHITE, alignment=TA_RIGHT)
S_TOTAL_VAL = _style("total_val", fontSize=11, fontName="Helvetica-Bold",
                      textColor=C_WHITE, alignment=TA_RIGHT)
S_WORDS     = _style("words", fontSize=8, fontName="Helvetica-Oblique",
                      textColor=C_DARK)
S_FOOTER    = _style("footer", fontSize=7, textColor=colors.grey, alignment=TA_CENTER)


# ── Amount in words (Indian system) ──────────────────────────────────────────

_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
         "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
         "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty",
         "Sixty", "Seventy", "Eighty", "Ninety"]


def _w100(n):
    if n < 20:
        return _ONES[n]
    t = _TENS[n // 10]
    o = _ONES[n % 10]
    return t + (" " + o if o else "")


def _w999(n):
    if n < 100:
        return _w100(n)
    h = _ONES[n // 100] + " Hundred"
    rem = _w100(n % 100)
    return h + (" " + rem if rem else "")


def _num_to_words(n: int) -> str:
    if n == 0:
        return "Zero"
    parts = []
    for label, div in [("Crore", 10_000_000), ("Lakh", 100_000),
                        ("Thousand", 1_000), ("", 1)]:
        chunk = n // div
        n %= div
        if chunk:
            parts.append(_w999(chunk) + (" " + label if label else ""))
    return " ".join(parts)


def amount_in_words(amount: float) -> str:
    rupees = int(amount)
    paise = round((amount - rupees) * 100)
    text = "Rupees " + _num_to_words(rupees)
    if paise:
        text += " and " + _num_to_words(paise) + " Paise"
    return text + " Only"


# ── PDF builder ───────────────────────────────────────────────────────────────

def _p(text, style=None):
    return Paragraph(str(text) if text else "", style or S_NORMAL)


def _tbl_style(cmds):
    return TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN",   (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
    ] + cmds)


def generate_invoice_pdf(invoice, items, firm, output_path: str) -> str:
    """
    invoice: sqlite3.Row or dict-like
    items:   list of sqlite3.Row or dict-like
    firm:    sqlite3.Row or dict-like
    output_path: full path for the PDF file
    Returns output_path.
    """
    supply_type = invoice["supply_type"]  # 'intra' or 'inter'
    is_intra = supply_type == "intra"

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
    )
    W = A4[0] - 24 * mm  # usable width ≈ 165 mm → 467 pt

    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    story.append(_p(firm["firm_name"] or "Your Firm", S_FIRM_NAME))
    addr_line = ", ".join(filter(None, [
        firm["address"], firm["city"], firm["state"], firm["pincode"]
    ]))
    story.append(_p(addr_line, S_FIRM_SUB))
    contact_line = " | ".join(filter(None, [
        ("📞 " + firm["phone"]) if firm["phone"] else "",
        ("✉ " + firm["email"]) if firm["email"] else "",
        ("GSTIN: " + firm["gstin"]) if firm["gstin"] else "",
    ]))
    story.append(_p(contact_line, S_FIRM_SUB))
    story.append(HRFlowable(width=W, thickness=2, color=C_DARK, spaceAfter=4))
    story.append(_p("TAX INVOICE", S_TITLE))
    story.append(HRFlowable(width=W, thickness=1, color=C_ACCENT, spaceAfter=6))

    # ── Invoice meta + Bill To ────────────────────────────────────────────────
    meta_col = W * 0.42
    client_col = W - meta_col - 4 * mm

    meta_rows = [
        [_p("Invoice No.", S_LABEL), _p(invoice["invoice_number"], S_VALUE)],
        [_p("Date", S_LABEL),        _p(invoice["invoice_date"], S_VALUE)],
        [_p("Due Date", S_LABEL),    _p(invoice["due_date"] or "—", S_VALUE)],
        [_p("Supply Type", S_LABEL), _p("Intra-State (CGST + SGST)" if is_intra else "Inter-State (IGST)", S_VALUE)],
        [_p("Status", S_LABEL),      _p(invoice["status"], S_VALUE)],
    ]
    meta_tbl = Table(meta_rows, colWidths=[meta_col * 0.38, meta_col * 0.62])
    meta_tbl.setStyle(_tbl_style([
        ("BACKGROUND", (0, 0), (-1, -1), C_LGRAY),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#ddd")),
    ]))

    client_data = [
        [_p("BILL TO", _style("bt_hdr", fontSize=8, fontName="Helvetica-Bold", textColor=C_WHITE))],
        [_p(invoice["client_name"], _style("cn", fontSize=10, fontName="Helvetica-Bold", textColor=C_DARK))],
        [_p(invoice["client_address"] or "", S_NORMAL)],
        [_p("GSTIN: " + (invoice["client_gstin"] or "Unregistered"), S_NORMAL)],
        [_p("State: " + (invoice["client_state"] or "—"), S_NORMAL)],
        [_p(" | ".join(filter(None, [invoice.get("client_email", ""), invoice.get("client_phone", "")])), S_NORMAL)],
    ]
    client_tbl = Table(client_data, colWidths=[client_col])
    client_tbl.setStyle(_tbl_style([
        ("BACKGROUND", (0, 0), (-1, 0), C_DARK),
        ("BACKGROUND", (0, 1), (-1, -1), C_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, C_DARK),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#ccc")),
    ]))

    top_tbl = Table([[meta_tbl, client_tbl]], colWidths=[meta_col, client_col],
                    spaceBefore=4, spaceAfter=8)
    top_tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                  ("LEFTPADDING",  (0, 0), (-1, -1), 0),
                                  ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                  ("TOPPADDING",   (0, 0), (-1, -1), 0),
                                  ("BOTTOMPADDING",(0, 0), (-1, -1), 0)]))
    story.append(top_tbl)

    # ── Items table ───────────────────────────────────────────────────────────
    if is_intra:
        hdr = ["#", "Description", "HSN", "Qty", "Unit", "Rate (₹)",
               "Taxable (₹)", "CGST%", "CGST (₹)", "SGST%", "SGST (₹)", "Total (₹)"]
        col_w = [8*mm, 46*mm, 14*mm, 10*mm, 10*mm, 18*mm,
                 20*mm, 10*mm, 15*mm, 10*mm, 15*mm, 21*mm]
    else:
        hdr = ["#", "Description", "HSN", "Qty", "Unit", "Rate (₹)",
               "Taxable (₹)", "IGST%", "IGST (₹)", "Total (₹)"]
        col_w = [8*mm, 55*mm, 14*mm, 12*mm, 12*mm, 20*mm,
                 24*mm, 12*mm, 20*mm, 30*mm]

    hdr_row = [_p(h, _style(f"h{i}", fontSize=7, fontName="Helvetica-Bold",
                             textColor=C_WHITE, alignment=TA_CENTER))
               for i, h in enumerate(hdr)]
    rows = [hdr_row]

    for idx, it in enumerate(items, 1):
        if is_intra:
            row = [
                _p(str(idx), _style("n", alignment=TA_CENTER)),
                _p(it["description"]),
                _p(it["hsn_code"] or ""),
                _p(f"{it['quantity']:g}", _style("r", alignment=TA_RIGHT)),
                _p(it["unit"]),
                _p(f"{it['unit_price']:,.2f}", _style("r", alignment=TA_RIGHT)),
                _p(f"{it['taxable_value']:,.2f}", _style("r", alignment=TA_RIGHT)),
                _p(f"{it['cgst_rate']:g}%", _style("r", alignment=TA_CENTER)),
                _p(f"{it['cgst_amt']:,.2f}", _style("r", alignment=TA_RIGHT)),
                _p(f"{it['sgst_rate']:g}%", _style("r", alignment=TA_CENTER)),
                _p(f"{it['sgst_amt']:,.2f}", _style("r", alignment=TA_RIGHT)),
                _p(f"{it['total_amt']:,.2f}", _style("rb", fontName="Helvetica-Bold", alignment=TA_RIGHT)),
            ]
        else:
            row = [
                _p(str(idx), _style("n", alignment=TA_CENTER)),
                _p(it["description"]),
                _p(it["hsn_code"] or ""),
                _p(f"{it['quantity']:g}", _style("r", alignment=TA_RIGHT)),
                _p(it["unit"]),
                _p(f"{it['unit_price']:,.2f}", _style("r", alignment=TA_RIGHT)),
                _p(f"{it['taxable_value']:,.2f}", _style("r", alignment=TA_RIGHT)),
                _p(f"{it['igst_rate']:g}%", _style("r", alignment=TA_CENTER)),
                _p(f"{it['igst_amt']:,.2f}", _style("r", alignment=TA_RIGHT)),
                _p(f"{it['total_amt']:,.2f}", _style("rb", fontName="Helvetica-Bold", alignment=TA_RIGHT)),
            ]
        rows.append(row)

    item_tbl = Table(rows, colWidths=col_w, repeatRows=1)
    n_rows = len(rows)
    banded = [("BACKGROUND", (0, i), (-1, i), C_LGRAY)
              for i in range(2, n_rows, 2)]
    item_tbl.setStyle(_tbl_style([
        ("BACKGROUND", (0, 0), (-1, 0), C_DARK),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#ccc")),
        ("LINEBELOW", (0, 0), (-1, 0), 1, C_ACCENT),
        ("ALIGN", (0, 1), (0, -1), "CENTER"),
    ] + banded))
    story.append(item_tbl)
    story.append(Spacer(1, 4))

    # ── Tax summary ───────────────────────────────────────────────────────────
    tax_col_w = W * 0.5
    summary_col_w = W - tax_col_w

    tax_rows_data: list = []
    tax_rows_data.append([
        _p("Taxable Amount:", S_BOLD),
        _p(f"₹ {invoice['subtotal']:,.2f}", S_RIGHT_B),
    ])
    if is_intra:
        tax_rows_data.append([_p("CGST:", S_NORMAL), _p(f"₹ {invoice['cgst_total']:,.2f}", S_RIGHT)])
        tax_rows_data.append([_p("SGST:", S_NORMAL), _p(f"₹ {invoice['sgst_total']:,.2f}", S_RIGHT)])
    else:
        tax_rows_data.append([_p("IGST:", S_NORMAL), _p(f"₹ {invoice['igst_total']:,.2f}", S_RIGHT)])

    summary_tbl = Table(tax_rows_data, colWidths=[summary_col_w * 0.55, summary_col_w * 0.45])
    summary_tbl.setStyle(_tbl_style([
        ("BACKGROUND", (0, 0), (-1, -1), C_LIGHT),
        ("BOX",  (0, 0), (-1, -1), 0.5, C_DARK),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#ccc")),
    ]))

    grand_tbl = Table(
        [[_p("GRAND TOTAL", S_TOTAL_LBL), _p(f"₹ {invoice['grand_total']:,.2f}", S_TOTAL_VAL)]],
        colWidths=[summary_col_w * 0.55, summary_col_w * 0.45],
    )
    grand_tbl.setStyle(_tbl_style([
        ("BACKGROUND", (0, 0), (-1, -1), C_DARK),
        ("BOX", (0, 0), (-1, -1), 1, C_ACCENT),
    ]))

    right_stack = Table([[summary_tbl], [grand_tbl]],
                        colWidths=[summary_col_w])
    right_stack.setStyle(TableStyle([
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING",   (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
    ]))

    words_tbl = Table(
        [[_p(f"Amount in Words:\n{amount_in_words(invoice['grand_total'])}", S_WORDS)]],
        colWidths=[tax_col_w],
    )
    words_tbl.setStyle(_tbl_style([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffbe6")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e6c700")),
    ]))

    combined = Table([[words_tbl, right_stack]],
                     colWidths=[tax_col_w, summary_col_w])
    combined.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING",   (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
    ]))
    story.append(combined)
    story.append(Spacer(1, 6))

    # ── Notes / Terms ─────────────────────────────────────────────────────────
    if invoice["notes"] or firm["terms"]:
        terms_data = []
        if firm["terms"]:
            terms_data.append([_p("Terms & Conditions:", S_BOLD)])
            for line in (firm["terms"] or "").split("\n"):
                if line.strip():
                    terms_data.append([_p("• " + line.strip(), S_NORMAL)])
        if invoice["notes"]:
            terms_data.append([_p("Notes: " + invoice["notes"], S_NORMAL)])
        terms_tbl = Table(terms_data, colWidths=[W * 0.6])
        terms_tbl.setStyle(_tbl_style([
            ("BACKGROUND", (0, 0), (-1, -1), C_LGRAY),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#ccc")),
        ]))
        story.append(KeepTogether(terms_tbl))
        story.append(Spacer(1, 6))

    # ── Bank details + Signature ──────────────────────────────────────────────
    bank_rows = []
    if firm["bank_name"]:
        bank_rows.append([_p("Bank Details:", S_BOLD), _p("")])
        bank_rows.append([_p("Bank Name:", S_LABEL), _p(firm["bank_name"], S_VALUE)])
    if firm["bank_account"]:
        bank_rows.append([_p("Account No.:", S_LABEL), _p(firm["bank_account"], S_VALUE)])
    if firm["bank_ifsc"]:
        bank_rows.append([_p("IFSC Code:", S_LABEL), _p(firm["bank_ifsc"], S_VALUE)])
    if firm["bank_branch"]:
        bank_rows.append([_p("Branch:", S_LABEL), _p(firm["bank_branch"], S_VALUE)])

    bank_tbl = Table(bank_rows or [[_p("")]], colWidths=[W * 0.25, W * 0.35])
    bank_tbl.setStyle(_tbl_style([
        ("BACKGROUND", (0, 0), (-1, -1), C_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, C_DARK),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#ccc")),
    ]))

    sig_tbl = Table([
        [_p(f"For {firm['firm_name'] or 'Company'}", _style("for_co", fontSize=8, fontName="Helvetica-Bold", alignment=TA_CENTER))],
        [_p("\n\n\n", S_NORMAL)],
        [_p(firm["signature_name"] or "Authorised Signatory",
            _style("sig", fontSize=8, fontName="Helvetica-Bold",
                   alignment=TA_CENTER, textColor=C_DARK))],
    ], colWidths=[W * 0.35])
    sig_tbl.setStyle(_tbl_style([
        ("BACKGROUND", (0, 0), (-1, -1), C_LGRAY),
        ("BOX", (0, 0), (-1, -1), 0.5, C_DARK),
        ("LINEABOVE", (0, 2), (-1, 2), 0.5, C_DARK),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))

    bottom = Table([[bank_tbl, sig_tbl]], colWidths=[W * 0.6, W * 0.4])
    bottom.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING",   (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
    ]))
    story.append(bottom)
    story.append(Spacer(1, 6))

    # ── UPI QR Code ──────────────────────────────────────────────────────────
    upi_id = (firm.get("upi_id") or "").strip()
    if upi_id:
        try:
            import qrcode as _qrc
            upi_url = (
                f"upi://pay?pa={upi_id}"
                f"&pn={firm.get('firm_name', '').replace(' ', '%20')}"
                f"&am={invoice['grand_total']:.2f}"
                f"&cu=INR"
                f"&tn={invoice.get('invoice_number', '')}"
            )
            qr_img_obj = _qrc.make(upi_url)
            buf = io.BytesIO()
            qr_img_obj.save(buf, format="PNG")
            buf.seek(0)
            qr_size = 42 * mm
            qr_rl = RLImage(buf, width=qr_size, height=qr_size)
            S_QR_LBL = _style("qr_lbl", fontSize=8, fontName="Helvetica-Bold",
                               alignment=TA_CENTER, textColor=C_DARK)
            S_QR_SUB = _style("qr_sub", fontSize=7, alignment=TA_CENTER,
                               textColor=colors.HexColor("#555"))
            qr_cell = Table(
                [[qr_rl], [_p("Scan to Pay", S_QR_LBL)], [_p(upi_id, S_QR_SUB)]],
                colWidths=[qr_size + 8 * mm],
            )
            qr_cell.setStyle(TableStyle([
                ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
                ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING",    (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("BACKGROUND",    (0, 0), (-1, -1), C_LIGHT),
                ("BOX",           (0, 0), (-1, -1), 0.5, C_DARK),
            ]))
            pad_cell = Table([[_p("")]], colWidths=[W - qr_size - 8 * mm])
            pad_cell.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0)]))
            upi_row = Table([[pad_cell, qr_cell]], colWidths=[W - qr_size - 8 * mm, qr_size + 8 * mm])
            upi_row.setStyle(TableStyle([
                ("VALIGN",        (0, 0), (-1, -1), "BOTTOM"),
                ("LEFTPADDING",   (0, 0), (-1, -1), 0),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
                ("TOPPADDING",    (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            story.append(upi_row)
            story.append(Spacer(1, 6))
        except Exception:
            pass

    # ── E-Invoice IRN block ───────────────────────────────────────────────────
    irn        = (invoice.get("irn") or "").strip()
    ack_number = (invoice.get("ack_number") or "").strip()
    ack_date   = (invoice.get("ack_date") or "").strip()
    signed_qr  = (invoice.get("signed_qr") or "").strip()

    if irn:
        S_IRN_LBL  = _style("irn_lbl", fontSize=7, fontName="Helvetica-Bold",
                             textColor=C_DARK)
        S_IRN_VAL  = _style("irn_val", fontSize=7, fontName="Helvetica",
                             textColor=colors.HexColor("#222"))
        S_IRN_HEAD = _style("irn_head", fontSize=8, fontName="Helvetica-Bold",
                             textColor=C_WHITE, alignment=TA_CENTER)

        irn_rows = [
            [_p("E-INVOICE DETAILS", S_IRN_HEAD), _p(""), _p("")],
            [_p("IRN:", S_IRN_LBL), _p(irn, S_IRN_VAL), _p("")],
            [_p("Ack No:", S_IRN_LBL), _p(ack_number, S_IRN_VAL),
             _p(f"Ack Date: {ack_date}", S_IRN_VAL)],
        ]

        # Build QR image if signed_qr data is available
        qr_elem = None
        if signed_qr:
            try:
                from einvoice import build_qr_image_bytes
                qr_png = build_qr_image_bytes(signed_qr)
                qr_buf = io.BytesIO(qr_png)
                qr_sz  = 30 * mm
                qr_elem = RLImage(qr_buf, width=qr_sz, height=qr_sz)
            except Exception:
                pass

        irn_w = [20 * mm, W * 0.55, W * 0.25] if not qr_elem else [20 * mm, W * 0.45, W * 0.20]
        irn_tbl = Table(irn_rows, colWidths=irn_w)
        irn_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), C_DARK),
            ("BACKGROUND",    (0, 1), (-1, -1), C_LIGHT),
            ("SPAN",          (0, 0), (-1, 0)),
            ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#ccc")),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ]))

        if qr_elem:
            qr_sz  = 30 * mm
            S_QR_S = _style("qr_s", fontSize=6, alignment=TA_CENTER, textColor=C_DARK)
            qr_cell_tbl = Table(
                [[qr_elem], [_p("Scan to\nVerify", S_QR_S)]],
                colWidths=[qr_sz + 4 * mm],
            )
            qr_cell_tbl.setStyle(TableStyle([
                ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
                ("BACKGROUND", (0, 0), (-1, -1), C_LIGHT),
                ("BOX",        (0, 0), (-1, -1), 0.5, C_DARK),
            ]))
            irn_row_tbl = Table(
                [[irn_tbl, qr_cell_tbl]],
                colWidths=[W - qr_sz - 4 * mm, qr_sz + 4 * mm],
            )
            irn_row_tbl.setStyle(TableStyle([
                ("VALIGN",         (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING",    (0, 0), (-1, -1), 0),
                ("RIGHTPADDING",   (0, 0), (-1, -1), 0),
                ("TOPPADDING",     (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING",  (0, 0), (-1, -1), 0),
            ]))
            story.append(irn_row_tbl)
        else:
            story.append(irn_tbl)
        story.append(Spacer(1, 4))

    # Footer
    story.append(HRFlowable(width=W, thickness=0.5, color=C_DARK))
    story.append(_p(
        "This is a computer-generated invoice. No signature required. | "
        f"Generated on {datetime.now().strftime('%d %b %Y %I:%M %p')}",
        S_FOOTER,
    ))

    doc.build(story)


# ── Credit / Debit Note PDF ───────────────────────────────────────────────────

def generate_cdn_pdf(note, items, firm, output_path: str) -> str:
    """
    Generate a Credit Note or Debit Note PDF.
    note  : dict from get_cdn (credit_debit_notes row)
    items : list of dicts from cdn_items
    firm  : dict from get_firm_settings
    """
    note_type   = note.get("note_type", "Credit")  # 'Credit' or 'Debit'
    supply_type = note.get("supply_type", "intra")
    is_intra    = supply_type == "intra"
    doc_title   = "CREDIT NOTE" if note_type == "Credit" else "DEBIT NOTE"
    accent      = colors.HexColor("#2ecc71") if note_type == "Credit" else colors.HexColor("#e74c3c")

    # Reuse accent for title style
    s_title = _style("cdn_title", fontSize=13, fontName="Helvetica-Bold",
                     textColor=accent, alignment=TA_CENTER, leading=16)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        topMargin=12 * mm, bottomMargin=12 * mm,
        leftMargin=12 * mm, rightMargin=12 * mm,
    )
    W = A4[0] - 24 * mm
    story = []

    # ── Firm header ───────────────────────────────────────────────────────────
    story.append(_p(firm.get("firm_name") or "Your Firm", S_FIRM_NAME))
    addr_line = ", ".join(filter(None, [
        firm.get("address"), firm.get("city"),
        firm.get("state"), firm.get("pincode")
    ]))
    story.append(_p(addr_line, S_FIRM_SUB))
    contact = " | ".join(filter(None, [
        f"Ph: {firm['phone']}" if firm.get("phone") else "",
        f"Email: {firm['email']}" if firm.get("email") else "",
        f"GSTIN: {firm['gstin']}" if firm.get("gstin") else "",
    ]))
    if contact:
        story.append(_p(contact, S_FIRM_SUB))
    story.append(Spacer(1, 4))

    # ── Document title ────────────────────────────────────────────────────────
    story.append(HRFlowable(width=W, thickness=1, color=accent))
    story.append(_p(doc_title, s_title))
    story.append(HRFlowable(width=W, thickness=1, color=accent))
    story.append(Spacer(1, 6))

    # ── Note details + Client details ─────────────────────────────────────────
    left_data = [
        [_p("Note Number", S_LABEL),
         _p(note.get("note_number", ""), S_VALUE)],
        [_p("Note Date", S_LABEL),
         _p(note.get("note_date", ""), S_VALUE)],
        [_p("Original Invoice", S_LABEL),
         _p(note.get("original_invoice_no") or "—", S_VALUE)],
        [_p("Reason", S_LABEL),
         _p(note.get("reason") or "—", S_NORMAL)],
    ]
    right_data = [
        [_p("Bill To", S_LABEL), _p("")],
        [_p("", S_LABEL),
         _p(note.get("client_name") or "—", S_VALUE)],
    ]

    left_tbl  = Table(left_data,  colWidths=[30*mm, W/2 - 34*mm])
    right_tbl = Table(right_data, colWidths=[20*mm, W/2 - 10*mm])
    for t in (left_tbl, right_tbl):
        t.setStyle(_tbl_style([
            ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ]))
    meta_tbl = Table([[left_tbl, right_tbl]], colWidths=[W/2, W/2])
    meta_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 8))

    # ── Items table ───────────────────────────────────────────────────────────
    if is_intra:
        hdrs = ["#", "Description", "HSN", "Qty", "Rate", "Taxable",
                "CGST", "SGST", "Total"]
        col_w = [8*mm, 50*mm, 18*mm, 14*mm, 20*mm, 22*mm, 20*mm, 20*mm, 22*mm]
    else:
        hdrs = ["#", "Description", "HSN", "Qty", "Rate", "Taxable", "IGST", "Total"]
        col_w = [8*mm, 55*mm, 18*mm, 14*mm, 20*mm, 22*mm, 24*mm, 24*mm]

    rows = [[_p(h, S_BOLD) for h in hdrs]]
    for idx, it in enumerate(items, 1):
        if is_intra:
            rows.append([
                _p(str(idx), S_NORMAL),
                _p(it.get("description",""), S_NORMAL),
                _p(it.get("hsn_code","") or "", S_NORMAL),
                _p(str(it.get("quantity",1)), S_RIGHT),
                _p(f"{it.get('unit_price',0):,.2f}", S_RIGHT),
                _p(f"{it.get('taxable_value',0):,.2f}", S_RIGHT),
                _p(f"{it.get('cgst_amt',0):,.2f}\n({it.get('gst_rate',0)/2}%)", S_RIGHT),
                _p(f"{it.get('sgst_amt',0):,.2f}\n({it.get('gst_rate',0)/2}%)", S_RIGHT),
                _p(f"{it.get('total_amt',0):,.2f}", S_RIGHT_B),
            ])
        else:
            rows.append([
                _p(str(idx), S_NORMAL),
                _p(it.get("description",""), S_NORMAL),
                _p(it.get("hsn_code","") or "", S_NORMAL),
                _p(str(it.get("quantity",1)), S_RIGHT),
                _p(f"{it.get('unit_price',0):,.2f}", S_RIGHT),
                _p(f"{it.get('taxable_value',0):,.2f}", S_RIGHT),
                _p(f"{it.get('igst_amt',0):,.2f}\n({it.get('gst_rate',0)}%)", S_RIGHT),
                _p(f"{it.get('total_amt',0):,.2f}", S_RIGHT_B),
            ])

    item_tbl = Table(rows, colWidths=col_w, repeatRows=1)
    item_tbl.setStyle(_tbl_style([
        ("BACKGROUND",   (0, 0), (-1, 0),  C_DARK),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  C_WHITE),
        ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("LINEBELOW",    (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_LGRAY, C_WHITE]),
        ("BOX",          (0, 0), (-1, -1), 0.5, C_DARK),
    ]))
    story.append(item_tbl)
    story.append(Spacer(1, 6))

    # ── Totals ────────────────────────────────────────────────────────────────
    gst_lbl = "CGST + SGST" if is_intra else "IGST"
    gst_val = (note.get("cgst_total",0) + note.get("sgst_total",0)
               if is_intra else note.get("igst_total",0))
    tot_rows = [
        [_p("Subtotal", S_LABEL),  _p(f"₹ {note.get('subtotal',0):,.2f}", S_RIGHT)],
        [_p(gst_lbl, S_LABEL),     _p(f"₹ {gst_val:,.2f}", S_RIGHT)],
    ]
    if note.get("discount_amt", 0):
        tot_rows.append([_p("Discount", S_LABEL),
                         _p(f"₹ {note.get('discount_amt',0):,.2f}", S_RIGHT)])
    grand = note.get("grand_total", 0)
    tot_rows.append([
        _p(f"Grand Total", _style("gt_lbl", fontSize=10, fontName="Helvetica-Bold",
                                   textColor=C_WHITE, alignment=TA_RIGHT)),
        _p(f"₹ {grand:,.2f}", _style("gt_val", fontSize=11, fontName="Helvetica-Bold",
                                       textColor=C_WHITE, alignment=TA_RIGHT)),
    ])
    tot_tbl = Table(tot_rows, colWidths=[W - 60*mm, 60*mm])
    tot_tbl.setStyle(_tbl_style([
        ("BACKGROUND",  (0, len(tot_rows)-1), (-1, len(tot_rows)-1), accent),
        ("LINEBELOW",   (0, 0), (-1, -2), 0.3, colors.lightgrey),
        ("BOX",         (0, 0), (-1, -1), 0.5, C_DARK),
    ]))
    tot_wrapper = Table([[None, tot_tbl]], colWidths=[W - 100*mm, 100*mm])
    tot_wrapper.setStyle(TableStyle([
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(tot_wrapper)
    story.append(Spacer(1, 4))
    story.append(_p(f"Amount: {amount_in_words(grand)}", S_WORDS))
    story.append(Spacer(1, 6))

    # ── Notes ─────────────────────────────────────────────────────────────────
    if note.get("notes"):
        story.append(_p(f"Notes: {note['notes']}", S_NORMAL))
        story.append(Spacer(1, 4))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width=W, thickness=0.5, color=C_DARK))
    story.append(_p(
        f"This is a computer-generated {doc_title.title()}. | "
        f"Generated on {datetime.now().strftime('%d %b %Y %I:%M %p')}",
        S_FOOTER,
    ))

    doc.build(story)
    return output_path
    return output_path
