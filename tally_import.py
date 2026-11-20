"""
Tally XML import parser.
Supports Tally ERP 9 and Tally Prime export formats.
"""
try:
    import defusedxml.ElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET  # local files only — XXE risk is acceptable
from datetime import datetime


def _text(el, tag, default=""):
    child = el.find(tag)
    return (child.text or "").strip() if child is not None else default


def _find_text(el, *tags):
    for tag in tags:
        val = el.findtext(f".//{tag}", "")
        if val and val.strip():
            return val.strip()
    return ""


def _parse_tally_date(date_str):
    date_str = (date_str or "").strip()
    if len(date_str) == 8:
        try:
            return datetime.strptime(date_str, "%Y%m%d").strftime("%Y-%m-%d")
        except ValueError:
            pass
    if "-" in date_str or "/" in date_str:
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
    return ""


def _parse_rate(rate_text):
    """Parse Tally rate strings like '420.00 /Nos' or '420.00/Nos'."""
    rate_text = (rate_text or "").strip()
    if not rate_text:
        return 0.0
    part = rate_text.split("/")[0].strip()
    try:
        return float(part)
    except ValueError:
        return 0.0


def _parse_qty(qty_text):
    """Parse Tally qty strings like ' 1 Nos' or '1.00 Nos'."""
    qty_text = (qty_text or "").strip()
    if not qty_text:
        return 0.0
    parts = qty_text.split()
    try:
        return float(parts[0])
    except (ValueError, IndexError):
        return 0.0


def _parse_amount(amt_text):
    try:
        return abs(float((amt_text or "").strip()))
    except (ValueError, TypeError):
        return 0.0


# ── Ledger (Client) parser ────────────────────────────────────────────────────

def _parse_ledgers(root):
    ledgers = []
    seen = set()
    for ledger in root.iter("LEDGER"):
        name = (ledger.get("NAME") or _text(ledger, "NAME") or "").strip()
        if not name or name in seen:
            continue

        # Filter out internal Tally ledgers (Cash, Bank, Sales, Purchase, etc.)
        parent_grp = (_text(ledger, "PARENT") or
                      _find_text(ledger, "PARENT")).lower()
        skip_groups = {"sundry debtors", "sundry creditors", ""}
        # Keep only party ledgers (sundry debtors / creditors)
        # If no group info, include all to be safe
        if parent_grp and parent_grp not in skip_groups and "debtor" not in parent_grp and "creditor" not in parent_grp:
            # Try to check if it looks like a party via GSTIN
            gstin = _find_text(ledger, "PARTYGSTIN", "GSTIN")
            if not gstin:
                continue

        address_els = ledger.findall(".//ADDRESS")
        address = ", ".join(
            el.text.strip() for el in address_els if el.text and el.text.strip()
        )

        gstin = _find_text(ledger, "PARTYGSTIN", "GSTIN")
        state = _text(ledger, "STATENAME")
        email = _text(ledger, "EMAIL")
        phone = _find_text(ledger, "LEDPHONE", "PHONE", "MOBILE")

        seen.add(name)
        ledgers.append({
            "name": name,
            "address": address,
            "gstin": gstin,
            "state": state,
            "email": email,
            "phone": phone,
        })
    return ledgers


# ── Stock Item (Product) parser ───────────────────────────────────────────────

def _parse_stock_items(root):
    items = []
    seen = set()
    for item in root.iter("STOCKITEM"):
        name = (item.get("NAME") or _text(item, "NAME") or "").strip()
        if not name or name in seen:
            continue

        unit = _find_text(item, "BASEUNITS", "ADDITIONALUNITS")
        hsn = _find_text(item, "HSNCODE")

        # GST rate — try several paths
        gst_rate = 0.0
        for tag in ["IGSTRATE", "TAXRATE", "GSTRATE"]:
            val = item.findtext(f".//{tag}", "")
            if val and val.strip():
                try:
                    gst_rate = float(val.strip())
                    break
                except ValueError:
                    pass

        rate = _parse_rate(_text(item, "OPENINGRATE"))

        seen.add(name)
        items.append({
            "name": name,
            "unit": unit or "pcs",
            "hsn_code": hsn,
            "gst_rate": gst_rate,
            "selling_price": rate,
        })
    return items


# ── Voucher (Invoice) parser ──────────────────────────────────────────────────

def _is_sales_voucher(voucher):
    vtype = (voucher.get("VCHTYPE") or "").strip()
    if vtype:
        return "Sales" in vtype
    vtype_name = _text(voucher, "VOUCHERTYPENAME")
    return "Sales" in vtype_name


def _parse_vouchers(root):
    vouchers = []
    seen = set()
    for voucher in root.iter("VOUCHER"):
        if not _is_sales_voucher(voucher):
            continue

        inv_no = _text(voucher, "VOUCHERNUMBER")
        if not inv_no or inv_no in seen:
            continue

        date_str = _text(voucher, "DATE") or _text(voucher, "EFFECTIVEDATE")
        inv_date = _parse_tally_date(date_str)
        party = _text(voucher, "PARTYLEDGERNAME")

        # Items from inventory entries
        line_items = []
        for entry in voucher.findall(".//ALLINVENTORYENTRIES.LIST"):
            stock_name = _text(entry, "STOCKITEMNAME")
            if not stock_name:
                continue

            qty_text = (_text(entry, "BILLEDQTY") or _text(entry, "ACTUALQTY"))
            qty = _parse_qty(qty_text)

            rate = _parse_rate(_text(entry, "RATE"))
            amount = _parse_amount(_text(entry, "AMOUNT"))

            if rate == 0.0 and qty:
                rate = round(amount / qty, 2) if qty else 0.0

            # HSN from HSNDETAILS
            hsn = _find_text(entry, "HSNCODE")

            # GST from GSTDETAILS or RATEDETAILS
            gst_rate = 18.0
            for tag in ["IGSTRATE", "TAXRATE", "GSTRATE"]:
                val = entry.findtext(f".//{tag}", "")
                if val:
                    try:
                        gst_rate = float(val.strip())
                        break
                    except ValueError:
                        pass

            unit = ""
            qty_text2 = _text(entry, "BILLEDQTY") or _text(entry, "ACTUALQTY")
            parts = qty_text2.strip().split()
            if len(parts) >= 2:
                unit = parts[-1]

            line_items.append({
                "description": stock_name,
                "hsn_code": hsn,
                "quantity": qty if qty else 1.0,
                "unit": unit or "pcs",
                "unit_price": rate,
                "gst_rate": gst_rate,
            })

        # Grand total from party ledger debit entry
        grand_total = 0.0
        for entry in voucher.findall(".//ALLLEDGERENTRIES.LIST"):
            led = _text(entry, "LEDGERNAME")
            positive = _text(entry, "ISDEEMEDPOSITIVE")
            if led == party or positive == "Yes":
                grand_total = _parse_amount(_text(entry, "AMOUNT"))
                break
        if not grand_total:
            grand_total = sum(
                it["quantity"] * it["unit_price"] for it in line_items
            )

        # Determine supply type from GST ledger names
        supply_type = "inter"
        for entry in voucher.findall(".//ALLLEDGERENTRIES.LIST"):
            led = _text(entry, "LEDGERNAME").lower()
            if "cgst" in led or "sgst" in led:
                supply_type = "intra"
                break

        seen.add(inv_no)
        vouchers.append({
            "invoice_number": inv_no,
            "invoice_date": inv_date,
            "party_name": party,
            "supply_type": supply_type,
            "items": line_items,
            "grand_total": grand_total,
        })
    return vouchers


# ── Main entry point ──────────────────────────────────────────────────────────

def parse_tally_xml(filepath):
    """
    Parse a Tally XML export file.
    Returns dict with keys: ledgers, stock_items, vouchers.
    Each is a list of dicts ready for DB import.
    """
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
    except ET.ParseError as e:
        raise ValueError(f"Invalid XML file: {e}")

    return {
        "ledgers": _parse_ledgers(root),
        "stock_items": _parse_stock_items(root),
        "vouchers": _parse_vouchers(root),
    }
