"""
E-Way Bill (EWB) integration for Indian GST compliance.
Handles EWB generation, cancellation, and vehicle update via NIC API.

Requires: requests, pycryptodome  (pip install requests pycryptodome)
API reference: https://ewaybillgst.gov.in/apidocs/
"""
import base64
import json
import os
from datetime import datetime

try:
    import requests as _req
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

SANDBOX_URL = "https://ewaybill-sandbox.nic.in"
PROD_URL    = "https://ewaybillgst.gov.in"


# ── AES helpers (same NIC ECB protocol as IRP) ────────────────────────────────

def _aes_encrypt(key: bytes, data: bytes) -> bytes:
    cipher = AES.new(key[:16], AES.MODE_ECB)
    return cipher.encrypt(pad(data, AES.block_size))


def _aes_decrypt(key: bytes, data: bytes) -> bytes:
    cipher = AES.new(key[:16], AES.MODE_ECB)
    return unpad(cipher.decrypt(data), AES.block_size)


def _b64e(b: bytes) -> str:
    return base64.b64encode(b).decode()


def _b64d(s: str) -> bytes:
    return base64.b64decode(s)


# ── EWB API Client ────────────────────────────────────────────────────────────

class EWBClient:
    """Client for the NIC E-Way Bill API."""

    def __init__(self, gstin: str, username: str, password: str,
                 sandbox: bool = True):
        self.gstin    = gstin.upper().strip()
        self.username = username.strip()
        self.password = password
        self.base_url = SANDBOX_URL if sandbox else PROD_URL
        self._token: str  = ""
        self._sek: bytes  = b""

    def _check_deps(self):
        if not HAS_REQUESTS:
            raise RuntimeError("Package 'requests' not installed.\nRun: pip install requests")
        if not HAS_CRYPTO:
            raise RuntimeError("Package 'pycryptodome' not installed.\nRun: pip install pycryptodome")

    def _base_headers(self) -> dict:
        return {
            "gstin":        self.gstin,
            "Content-Type": "application/json",
            "Accept":       "application/json",
        }

    def _auth_headers(self) -> dict:
        h = self._base_headers()
        h["authtoken"]  = self._token
        h["user-name"]  = self.username
        return h

    def authenticate(self) -> str:
        """Authenticate and store auth token + sek. Returns token."""
        self._check_deps()
        app_key  = _b64e(os.urandom(24))[:32]
        enc_pwd  = _b64e(_aes_encrypt(app_key[:16].encode(), self.password.encode()))
        body_obj = {
            "action":   "ACCESSTOKEN",
            "username": self.username,
            "password": enc_pwd,
            "appkey":   app_key,
        }
        enc_body = _b64e(_aes_encrypt(app_key[:16].encode(),
                                      json.dumps(body_obj).encode()))
        resp = _req.post(
            f"{self.base_url}/ewb/ewayapi",
            headers=self._base_headers(),
            json={"action": "ACCESSTOKEN", "data": enc_body},
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("status") != "1":
            raise ValueError(f"EWB auth failed: {body.get('error', body)}")
        dec = json.loads(_aes_decrypt(app_key[:16].encode(), _b64d(body["data"])))
        self._token = dec["authtoken"]
        sek_raw     = _aes_decrypt(app_key[:16].encode(), _b64d(dec["sek"]))
        self._sek   = sek_raw[:16]
        return self._token

    def _enc(self, data: dict) -> str:
        return _b64e(_aes_encrypt(self._sek, json.dumps(data).encode()))

    def _dec(self, enc_b64: str) -> dict:
        return json.loads(_aes_decrypt(self._sek, _b64d(enc_b64)))

    def _post(self, action: str, payload: dict) -> dict:
        self._check_deps()
        if not self._token:
            self.authenticate()
        resp = _req.post(
            f"{self.base_url}/ewb/ewayapi",
            headers=self._auth_headers(),
            json={"action": action, "data": self._enc(payload)},
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("status") != "1":
            raise ValueError(f"EWB API error ({action}): {body.get('error', body)}")
        return self._dec(body["data"])

    def generate_ewb(self, ewb_json: dict) -> dict:
        """
        Generate an E-Way Bill.
        Returns dict with keys: ewayBillNo, ewayBillDate, validUpto, alert, etc.
        """
        return self._post("GENEWAYBILL", ewb_json)

    def cancel_ewb(self, ewb_no: str, cancel_reason: int = 2,
                   cancel_remarks: str = "Data entry mistake") -> dict:
        """
        Cancel an E-Way Bill.
        cancel_reason: 1=Duplicate, 2=Order Cancelled, 3=Data Entry Mistake, 4=Others
        """
        return self._post("CANEWB", {
            "ewbNo":         int(ewb_no),
            "cancelRsnCode": cancel_reason,
            "cancelRmrk":    cancel_remarks,
        })

    def update_vehicle(self, ewb_no: str, vehicle_no: str,
                       from_place: str, from_state: int,
                       reason_code: int = 4, reason_remarks: str = "",
                       trans_mode: str = "1") -> dict:
        """Update vehicle number for an existing EWB."""
        return self._post("VEHEWB", {
            "ewbNo":       int(ewb_no),
            "vehicleNo":   vehicle_no.upper().replace(" ", ""),
            "fromPlace":   from_place,
            "fromState":   from_state,
            "reasonCode":  str(reason_code),
            "reasonRem":   reason_remarks,
            "transMode":   trans_mode,
        })

    def get_ewb_details(self, ewb_no: str) -> dict:
        """Fetch details of an existing EWB."""
        return self._post("GETEWAYBILL", {"ewbNo": int(ewb_no)})


# ── State codes (same as E-Invoice) ──────────────────────────────────────────

_STATE_CODES = {
    "Andhra Pradesh": 37, "Arunachal Pradesh": 12, "Assam": 18,
    "Bihar": 10, "Chhattisgarh": 22, "Goa": 30, "Gujarat": 24,
    "Haryana": 6, "Himachal Pradesh": 2, "Jharkhand": 20,
    "Karnataka": 29, "Kerala": 32, "Madhya Pradesh": 23,
    "Maharashtra": 27, "Manipur": 14, "Meghalaya": 17,
    "Mizoram": 15, "Nagaland": 13, "Odisha": 21, "Punjab": 3,
    "Rajasthan": 8, "Sikkim": 11, "Tamil Nadu": 33,
    "Telangana": 36, "Tripura": 16, "Uttar Pradesh": 9,
    "Uttarakhand": 5, "West Bengal": 19, "Delhi": 7,
    "Jammu & Kashmir": 1, "Ladakh": 38, "Chandigarh": 4,
    "Puducherry": 34, "Andaman & Nicobar": 35, "Lakshadweep": 31,
    "Dadra & Nagar Haveli": 26, "Daman & Diu": 25,
}

TRANS_MODES = {"Road": "1", "Rail": "2", "Air": "3", "Ship": "4"}
SUPPLY_TYPES = {"Outward": "O", "Inward": "I"}
SUB_SUPPLY_TYPES = {
    "Supply": 1, "Import": 2, "Export": 3, "Job Work": 4,
    "For Own Use": 5, "Job Work Returns": 6, "Goods Returns": 7,
    "Sales Return": 8, "Others": 9,
}


def _pin(v) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return 0


def _fmt_date(iso_date: str) -> str:
    """Convert YYYY-MM-DD to DD/MM/YYYY for EWB portal."""
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return iso_date


# ── EWB JSON Builder ──────────────────────────────────────────────────────────

def build_ewb_json(invoice: dict, items: list, firm: dict, client: dict,
                   transporter_id: str = "", vehicle_no: str = "",
                   trans_mode: str = "1", trans_distance: int = 0,
                   trans_doc_no: str = "", trans_doc_date: str = "",
                   supply_type: str = "O", sub_supply_type: int = 1) -> dict:
    """
    Build NIC E-Way Bill JSON payload.

    Args:
        invoice       : dict from get_invoice_full
        items         : list of invoice_item dicts
        firm          : dict from get_firm_settings (the supplier)
        client        : dict from get_all_clients (the recipient)
        transporter_id: GSTIN of the transporter (or leave blank)
        vehicle_no    : Vehicle registration number (e.g. TN01AB1234)
        trans_mode    : "1"=Road, "2"=Rail, "3"=Air, "4"=Ship
        trans_distance: Distance in km
        trans_doc_no  : Transporter document number (for rail/air/ship)
        trans_doc_date: Transporter document date (YYYY-MM-DD)
        supply_type   : "O"=Outward, "I"=Inward
        sub_supply_type: 1=Supply, 2=Import, 3=Export, 4=Job Work ...
    Returns:
        dict ready to pass to EWBClient.generate_ewb()
    """
    seller_state_code = _STATE_CODES.get(firm.get("state", ""), 0)
    buyer_state_code  = _STATE_CODES.get(client.get("state", ""), seller_state_code)
    buyer_gstin       = (client.get("gstin") or "").strip().upper() or "URP"

    item_list = []
    for it in items:
        taxable = round(float(it.get("taxable_value") or
                              float(it.get("quantity", 1)) * float(it.get("unit_price", 0))), 2)
        gst_rate = float(it.get("gst_rate", 0))
        # Determine IGST vs CGST/SGST based on supply type
        is_inter = (seller_state_code != buyer_state_code)
        igst_rate = gst_rate if is_inter else 0.0
        cgst_rate = 0.0 if is_inter else gst_rate / 2
        sgst_rate = 0.0 if is_inter else gst_rate / 2

        item_list.append({
            "productName": it.get("description", "")[:300],
            "productDesc": it.get("description", "")[:300],
            "hsnCode":     str(it.get("hsn_code") or ""),
            "quantity":    round(float(it.get("quantity", 1)), 3),
            "qtyUnit":     (it.get("unit") or "NOS").upper()[:3],
            "cgstRate":    cgst_rate,
            "sgstRate":    sgst_rate,
            "igstRate":    igst_rate,
            "cessRate":    0.0,
            "cessNonAdvol": 0.0,
            "taxableAmount": taxable,
        })

    ewb = {
        "supplyType":     supply_type,
        "subSupplyType":  sub_supply_type,
        "subSupplyDesc":  "",
        "docType":        "INV",
        "docNo":          invoice.get("invoice_number", ""),
        "docDate":        _fmt_date(invoice.get("invoice_date", "")),
        "fromGstin":      (firm.get("gstin") or "").strip().upper(),
        "fromTrdName":    firm.get("firm_name", ""),
        "fromAddr1":      firm.get("address", "") or ".",
        "fromAddr2":      "",
        "fromPlace":      firm.get("city", ""),
        "fromPincode":    _pin(firm.get("pincode")),
        "fromStateCode":  seller_state_code,
        "actFromStateCode": seller_state_code,
        "toGstin":        buyer_gstin,
        "toTrdName":      client.get("name", ""),
        "toAddr1":        client.get("address", "") or ".",
        "toAddr2":        "",
        "toPlace":        client.get("city", ""),
        "toPincode":      _pin(client.get("pincode")),
        "toStateCode":    buyer_state_code,
        "actToStateCode": buyer_state_code,
        "totalValue":     round(float(invoice.get("subtotal", 0)), 2),
        "cgstValue":      round(float(invoice.get("cgst_total", 0)), 2),
        "sgstValue":      round(float(invoice.get("sgst_total", 0)), 2),
        "igstValue":      round(float(invoice.get("igst_total", 0)), 2),
        "cessValue":      0.0,
        "cessNonAdvolValue": 0.0,
        "otherValue":     0.0,
        "totInvValue":    round(float(invoice.get("grand_total", 0)), 2),
        "transactionType": 1,
        "dispatchFromGSTIN": (firm.get("gstin") or "").strip().upper(),
        "dispatchFromTradeName": firm.get("firm_name", ""),
        "shipToGSTIN":    buyer_gstin,
        "shipToTradeName": client.get("name", ""),
        "transporterId":  transporter_id.strip().upper() if transporter_id else "",
        "transporterName": "",
        "transDocNo":     trans_doc_no,
        "transMode":      trans_mode,
        "transDistance":  trans_distance,
        "vehicleNo":      vehicle_no.upper().replace(" ", "") if vehicle_no else "",
        "vehicleType":    "R",
        "itemList":       item_list,
    }

    if trans_doc_date:
        ewb["transDocDate"] = _fmt_date(trans_doc_date)

    return ewb
