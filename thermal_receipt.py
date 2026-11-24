"""
Thermal receipt printer — zero external dependencies.

Two backends:
  * Windows printer  — sends raw ESC/POS bytes via Win32 winspool (ctypes)
  * Network printer  — sends raw ESC/POS bytes to IP:port (socket, default 9100)

Configuration stored in config.json under "printer" key:
  {
    "enabled":    true,
    "type":       "windows",    // "windows" | "network"
    "name":       "EPSON TM-T82",   // Windows printer name
    "ip":         "192.168.1.100",  // network printer IP
    "port":       9100,
    "width":      80,           // 80 or 58 (mm)
    "auto_print": true
  }

Public API
----------
  load_config()                -> dict
  save_config(cfg)
  is_enabled()                 -> bool
  list_windows_printers()      -> list[str]
  print_receipt(firm, items, invoice_number, invoice_date, cashier_name)
  test_print()
"""

import ctypes
import json
import os
import socket
import subprocess
import sys

# ---------------------------------------------------------------------------
# ESC/POS byte constants
# ---------------------------------------------------------------------------
_ESC = b"\x1b"
_GS  = b"\x1d"

_INIT         = _ESC + b"@"           # Initialise printer
_ALIGN_LEFT   = _ESC + b"a\x00"
_ALIGN_CENTER = _ESC + b"a\x01"
_ALIGN_RIGHT  = _ESC + b"a\x02"
_BOLD_ON      = _ESC + b"E\x01"
_BOLD_OFF     = _ESC + b"E\x00"
_DOUBLE_ON    = _ESC + b"!\x30"      # double width + height
_DOUBLE_OFF   = _ESC + b"!\x00"
_LF           = b"\n"
_FEED         = lambda n: _ESC + b"d" + bytes([n])
_CUT          = _GS + b"V\x41\x03"  # partial cut, 3 mm

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _config_path() -> str:
    base = os.path.dirname(sys.executable if getattr(sys, "frozen", False)
                           else os.path.abspath(__file__))
    return os.path.join(base, "config.json")


def load_config() -> dict:
    """Return the printer section of config.json (or {} if absent)."""
    try:
        with open(_config_path(), encoding="utf-8") as f:
            return json.load(f).get("printer", {})
    except Exception:
        return {}


def save_config(printer_cfg: dict) -> None:
    """Write printer settings back into config.json."""
    path = _config_path()
    try:
        with open(path, encoding="utf-8") as f:
            full = json.load(f)
    except Exception:
        full = {}
    full["printer"] = printer_cfg
    with open(path, "w", encoding="utf-8") as f:
        json.dump(full, f, indent=2)


def is_enabled() -> bool:
    return bool(load_config().get("enabled", False))


# ---------------------------------------------------------------------------
# Printer discovery
# ---------------------------------------------------------------------------

def list_windows_printers() -> list:
    """Return names of all installed Windows printers."""
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-Printer | Select-Object -ExpandProperty Name"],
            capture_output=True, text=True, timeout=8,
        )
        return [p.strip() for p in result.stdout.splitlines() if p.strip()]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Transport backends
# ---------------------------------------------------------------------------

def _send_windows(printer_name: str, data: bytes) -> None:
    """Send raw bytes to a Windows printer via Win32 winspool (ctypes)."""
    winspool = ctypes.windll.winspool

    h = ctypes.c_void_p()
    if not winspool.OpenPrinterW(printer_name, ctypes.byref(h), None):
        raise OSError(f"Cannot open printer '{printer_name}'")

    class _DOC_INFO_1(ctypes.Structure):
        _fields_ = [
            ("pDocName",    ctypes.c_wchar_p),
            ("pOutputFile", ctypes.c_wchar_p),
            ("pDatatype",   ctypes.c_wchar_p),
        ]

    di = _DOC_INFO_1()
    di.pDocName    = "Receipt"
    di.pOutputFile = None
    di.pDatatype   = "RAW"

    job = winspool.StartDocPrinterW(h, 1, ctypes.byref(di))
    if not job:
        winspool.ClosePrinter(h)
        raise OSError("StartDocPrinter failed")

    try:
        winspool.StartPagePrinter(h)
        written = ctypes.c_ulong(0)
        buf = ctypes.create_string_buffer(data)
        winspool.WritePrinter(h, buf, len(data), ctypes.byref(written))
        winspool.EndPagePrinter(h)
    finally:
        winspool.EndDocPrinter(h)
        winspool.ClosePrinter(h)


def _send_network(ip: str, port: int, data: bytes, timeout: float = 5.0) -> None:
    """Send raw bytes to a network-connected printer (port 9100 by default)."""
    with socket.create_connection((ip, port), timeout=timeout) as s:
        s.sendall(data)


# ---------------------------------------------------------------------------
# ESC/POS receipt formatter
# ---------------------------------------------------------------------------

def _enc(text: str) -> bytes:
    """Encode to cp437 (default ESC/POS charset), replacing unknown chars."""
    return text.encode("cp437", errors="replace")


def _center_text(text: str, width: int) -> bytes:
    """Return centred text line + LF (uses ESC a 1 mode)."""
    return _ALIGN_CENTER + _enc(text[:width]) + _LF


def _divider(ch: str, width: int) -> bytes:
    return _ALIGN_LEFT + _enc(ch * width) + _LF


def format_receipt(
    *,
    firm_name:    str,
    firm_address: str = "",
    firm_city:    str = "",
    firm_state:   str = "",
    firm_gstin:   str = "",
    firm_phone:   str = "",
    invoice_number: str,
    invoice_date:   str,
    cashier_name:   str,
    items: list,     # list of dicts: description, quantity, unit_price, gst_rate
    subtotal:    float,
    gst_total:   float,
    grand_total: float,
    width: int = 48,   # chars: 80mm -> 48, 58mm -> 32
) -> bytes:
    """Build ESC/POS byte string for a receipt."""
    W = width
    r = b""
    r += _INIT

    # ── Shop header ──────────────────────────────────────────────────────────
    r += _ALIGN_CENTER
    r += _BOLD_ON + _DOUBLE_ON
    r += _enc(firm_name[:W]) + _LF
    r += _BOLD_OFF + _DOUBLE_OFF

    if firm_address:
        r += _enc(firm_address[:W]) + _LF
    loc = ", ".join(p for p in [firm_city, firm_state] if p)
    if loc:
        r += _enc(loc[:W]) + _LF
    if firm_gstin:
        r += _enc(f"GSTIN: {firm_gstin}"[:W]) + _LF
    if firm_phone:
        r += _enc(f"Ph: {firm_phone}"[:W]) + _LF

    r += _divider("=", W)

    # ── Bill metadata ─────────────────────────────────────────────────────────
    r += _ALIGN_LEFT
    date_str = (invoice_date or "")[:10]
    r += _enc(f"Bill  : {invoice_number}") + _LF
    r += _enc(f"Date  : {date_str}") + _LF
    r += _enc(f"Cashier: {cashier_name[:W - 9]}") + _LF

    r += _divider("-", W)

    # ── Column header ─────────────────────────────────────────────────────────
    if W >= 44:
        nm_w = W - 14           # name column width
        r += _BOLD_ON
        r += _enc(f"{'Item':<{nm_w}}{'Qty':>5}{'Total':>9}") + _LF
        r += _BOLD_OFF
    else:
        nm_w = W - 11
        r += _BOLD_ON
        r += _enc(f"{'Item':<{nm_w}}{'Qty':>4}{'Tot':>7}") + _LF
        r += _BOLD_OFF

    r += _divider("-", W)

    # ── Items ─────────────────────────────────────────────────────────────────
    for it in items:
        name  = str(it.get("description", ""))
        qty   = float(it.get("quantity", 1))
        price = float(it.get("unit_price", 0))
        grate = float(it.get("gst_rate", 0))
        # item total inclusive of GST
        taxable = round(qty * price, 2)
        gst_amt = round(taxable * grate / 100, 2)
        line_tot = round(taxable + gst_amt, 2)

        if W >= 44:
            # Wrap long names
            while len(name) > nm_w:
                r += _enc(name[:nm_w]) + _LF
                name = name[nm_w:]
            r += _enc(
                f"{name:<{nm_w}}{qty:>{5}g}{line_tot:>{9},.2f}"
            ) + _LF
        else:
            while len(name) > nm_w:
                r += _enc(name[:nm_w]) + _LF
                name = name[nm_w:]
            r += _enc(f"{name:<{nm_w}}{qty:>{4}g}{line_tot:>{7},.2f}") + _LF

    r += _divider("-", W)

    # ── Totals ────────────────────────────────────────────────────────────────
    r += _ALIGN_RIGHT
    if W >= 44:
        r += _enc(f"Subtotal : Rs.{subtotal:>10,.2f}") + _LF
        r += _enc(f"GST      : Rs.{gst_total:>10,.2f}") + _LF
        r += _BOLD_ON
        r += _enc(f"TOTAL    : Rs.{grand_total:>10,.2f}") + _LF
        r += _BOLD_OFF
    else:
        r += _enc(f"Sub  Rs.{subtotal:>8,.2f}") + _LF
        r += _enc(f"GST  Rs.{gst_total:>8,.2f}") + _LF
        r += _BOLD_ON
        r += _enc(f"TOT  Rs.{grand_total:>8,.2f}") + _LF
        r += _BOLD_OFF

    r += _ALIGN_CENTER
    r += _divider("=", W)
    r += _enc("Thank you! Visit again!") + _LF
    r += _divider("=", W)

    r += _FEED(4)
    r += _CUT
    return r


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def print_receipt(
    *,
    firm:           dict,
    items:          list,
    invoice_number: str,
    invoice_date:   str,
    cashier_name:   str,
    subtotal:       float,
    gst_total:      float,
    grand_total:    float,
) -> None:
    """
    Format and send a receipt to the configured printer.
    Raises an exception on failure (caller should catch and show to user).
    """
    cfg   = load_config()
    width = 48 if cfg.get("width", 80) >= 70 else 32

    data = format_receipt(
        firm_name      = firm.get("firm_name", "") or "Shop",
        firm_address   = firm.get("address", ""),
        firm_city      = firm.get("city", ""),
        firm_state     = firm.get("state", ""),
        firm_gstin     = firm.get("gstin", ""),
        firm_phone     = firm.get("phone", ""),
        invoice_number = invoice_number,
        invoice_date   = invoice_date,
        cashier_name   = cashier_name,
        items          = items,
        subtotal       = subtotal,
        gst_total      = gst_total,
        grand_total    = grand_total,
        width          = width,
    )

    ptype = cfg.get("type", "windows")
    if ptype == "network":
        ip   = cfg.get("ip", "").strip()
        port = int(cfg.get("port") or 9100)
        if not ip:
            raise ValueError("Network printer IP not configured.")
        _send_network(ip, port, data)
    else:
        name = cfg.get("name", "").strip()
        if not name:
            raise ValueError("Windows printer name not configured.")
        _send_windows(name, data)


def test_print() -> None:
    """Print a short test page to verify printer connectivity."""
    cfg   = load_config()
    width = 48 if cfg.get("width", 80) >= 70 else 32
    W = width

    r  = _INIT
    r += _ALIGN_CENTER
    r += _BOLD_ON + _enc("TEST PRINT") + _LF + _BOLD_OFF
    r += _enc("Printer is working!") + _LF
    r += _divider("-", W)
    r += _ALIGN_LEFT
    r += _enc("Type   : " + cfg.get("type", "windows")) + _LF
    if cfg.get("type") == "network":
        r += _enc(f"IP     : {cfg.get('ip', '')}:{cfg.get('port', 9100)}") + _LF
    else:
        r += _enc(f"Printer: {cfg.get('name', '')}") + _LF
    r += _enc(f"Width  : {cfg.get('width', 80)}mm ({W} chars)") + _LF
    r += _divider("-", W)
    r += _ALIGN_CENTER
    r += _enc("If you can read this, it works!") + _LF
    r += _FEED(4)
    r += _CUT

    ptype = cfg.get("type", "windows")
    if ptype == "network":
        ip   = cfg.get("ip", "").strip()
        port = int(cfg.get("port") or 9100)
        if not ip:
            raise ValueError("Network printer IP not configured.")
        _send_network(ip, port, r)
    else:
        name = cfg.get("name", "").strip()
        if not name:
            raise ValueError("Windows printer name not configured.")
        _send_windows(name, r)
