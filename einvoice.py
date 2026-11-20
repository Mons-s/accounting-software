"""
E-Invoicing (IRP/NIC) integration for Indian GST compliance.
Handles IRN generation, cancellation, and IRP JSON schema building.

Requires: requests, pycryptodome  (pip install requests pycryptodome)
"""
import base64
import io
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

SANDBOX_URL = "https://einvoice1-sandbox.nic.in"
PROD_URL    = "https://einvoice1.nic.in"


# ── AES helpers ───────────────────────────────────────────────────────────────

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


# ── IRP Client ────────────────────────────────────────────────────────────────

class IRPClient:
    """Client for the NIC IRP e-invoicing API (v1.03)."""

    def __init__(self, gstin: str, client_id: str, client_secret: str,
                 username: str, password: str, sandbox: bool = True):
        self.gstin         = gstin.upper().strip()
        self.client_id     = client_id.strip()
        self.client_secret = client_secret.strip()
        self.username      = username.strip()
        self.password      = password
        self.base_url      = SANDBOX_URL if sandbox else PROD_URL
        self._token: str   = ""
        self._sek: bytes   = b""

    def _check_deps(self):
        if not HAS_REQUESTS:
            raise RuntimeError(
                "Package 'requests' is not installed.\n"
                "Run:  pip install requests"
            )
        if not HAS_CRYPTO:
            raise RuntimeError(
                "Package 'pycryptodome' is not installed.\n"
                "Run:  pip install pycryptodome"
            )

    def _base_headers(self) -> dict:
        return {
            "client-id":     self.client_id,
            "client-secret": self.client_secret,
            "gstin":         self.gstin,
            "Content-Type":  "application/json",
        }

    def _auth_headers(self) -> dict:
        h = self._base_headers()
        h["user-name"]  = self.username
        h["auth-token"] = self._token
        return h

    def authenticate(self) -> str:
        """Authenticate with IRP and store auth_token + sek. Returns token."""
        self._check_deps()

        # Random 32-char app_key
        app_key = _b64e(os.urandom(24))[:32]

        # Encrypt password with AES-ECB using first 16 bytes of app_key
        enc_pwd = _b64e(_aes_encrypt(app_key[:16].encode(), self.password.encode()))

        auth_dict = {
            "UserName":               self.username,
            "Password":               enc_pwd,
            "AppKey":                 app_key,
            "ForceRefreshAccessToken": False,
        }
        # Encrypt the whole dict then base64-encode
        payload_bytes = json.dumps(auth_dict).encode()
        encrypted     = _b64e(_aes_encrypt(app_key[:16].encode(), payload_bytes))

        resp = _req.post(
            f"{self.base_url}/iapi/v1.03/authenticate",
            headers=self._base_headers(),
            json={"Data": encrypted},
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("Status") != 1:
            errs = body.get("ErrorDetails") or body
            raise ValueError(f"IRP authentication failed: {errs}")

        # Decrypt response data with app_key
        dec_data = json.loads(
            _aes_decrypt(app_key[:16].encode(), _b64d(body["Data"]))
        )
        self._token = dec_data["AuthToken"]
        # SEK is AES-encrypted with app_key; decrypt to get session key
        sek_raw     = _aes_decrypt(app_key[:16].encode(), _b64d(dec_data["Sek"]))
        self._sek   = sek_raw[:16]
        return self._token

    def _encrypt_payload(self, data: dict) -> str:
        return _b64e(_aes_encrypt(self._sek, json.dumps(data).encode()))

    def _decrypt_response(self, encrypted_b64: str) -> dict:
        return json.loads(_aes_decrypt(self._sek, _b64d(encrypted_b64)))

    def generate_irn(self, invoice_json: dict) -> dict:
        """
        Generate IRN for an invoice.
        Returns dict with keys: Irn, AckNo, AckDt, SignedQRCode, SignedInvoice.
        """
        self._check_deps()
        if not self._token:
            self.authenticate()

        resp = _req.post(
            f"{self.base_url}/iapi/v1.03/invoice",
            headers=self._auth_headers(),
            json={"Data": self._encrypt_payload(invoice_json)},
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("Status") != 1:
            errs = body.get("ErrorDetails") or body
            raise ValueError(f"IRN generation failed: {errs}")
        return self._decrypt_response(body["Data"])

    def cancel_irn(self, irn: str, reason_code: int = 1,
                   remark: str = "Data entry mistake") -> dict:
        """
        Cancel an IRN.
        reason_code: 1=Duplicate, 2=Data Entry Mistake, 3=Order Cancelled, 4=Other
        """
        self._check_deps()
        if not self._token:
            self.authenticate()
        payload = {"Irn": irn, "CnlRsn": reason_code, "CnlRem": remark}
        resp = _req.post(
            f"{self.base_url}/iapi/v1.03/invoice/cancel",
            headers=self._auth_headers(),
            json={"Data": self._encrypt_payload(payload)},
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("Status") != 1:
            errs = body.get("ErrorDetails") or body
            raise ValueError(f"IRN cancellation failed: {errs}")
        return self._decrypt_response(body["Data"])

    def get_irn_details(self, irn: str) -> dict:
        """Fetch details of an already-generated IRN."""
        self._check_deps()
        if not self._token:
            self.authenticate()
        resp = _req.get(
            f"{self.base_url}/iapi/v1.03/invoice/irn/{irn}",
            headers=self._auth_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("Status") != 1:
            raise ValueError(f"IRN fetch failed: {body.get('ErrorDetails', body)}")
        return self._decrypt_response(body["Data"])


# ── IRP JSON Schema Builder ───────────────────────────────────────────────────

_STATE_CODES = {
    "Andhra Pradesh": "37", "Arunachal Pradesh": "12", "Assam": "18",
    "Bihar": "10", "Chhattisgarh": "22", "Goa": "30", "Gujarat": "24",
    "Haryana": "06", "Himachal Pradesh": "02", "Jharkhand": "20",
    "Karnataka": "29", "Kerala": "32", "Madhya Pradesh": "23",
    "Maharashtra": "27", "Manipur": "14", "Meghalaya": "17",
    "Mizoram": "15", "Nagaland": "13", "Odisha": "21", "Punjab": "03",
    "Rajasthan": "08", "Sikkim": "11", "Tamil Nadu": "33",
    "Telangana": "36", "Tripura": "16", "Uttar Pradesh": "09",
    "Uttarakhand": "05", "West Bengal": "19", "Delhi": "07",
    "Jammu & Kashmir": "01", "Ladakh": "38", "Chandigarh": "04",
    "Puducherry": "34", "Andaman & Nicobar": "35", "Lakshadweep": "31",
    "Dadra & Nagar Haveli": "26", "Daman & Diu": "25",
}


def _sc(state: str) -> str:
    return _STATE_CODES.get(state, "")


def _pin(v) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return 0


def _fmt_date(iso_date: str) -> str:
    """Convert YYYY-MM-DD to DD/MM/YYYY for IRP."""
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return iso_date


def build_einvoice_json(invoice: dict, items: list,
                        firm: dict, client: dict) -> dict:
    """
    Build IRP v1.1 compliant e-invoice JSON payload.

    Args:
        invoice : dict from get_invoice_full  (invoice row)
        items   : list of invoice_item dicts
        firm    : dict from get_firm_settings
        client  : dict from get_all_clients / get_client
    Returns:
        dict ready to send to IRPClient.generate_irn()
    """
    buyer_gstin = (client.get("gstin") or "").strip().upper()
    seller_state = firm.get("state", "")
    buyer_state  = client.get("state", "")

    einv = {
        "Version": "1.1",
        "TranDtls": {
            "TaxSch": "GST",
            "SupTyp": "B2B" if buyer_gstin else "B2C",
            "RegRev": "N",
            "EcmGstin": None,
            "IgstOnIntra": "N",
        },
        "DocDtls": {
            "Typ": "INV",
            "No":  invoice.get("invoice_number", ""),
            "Dt":  _fmt_date(invoice.get("invoice_date", "")),
        },
        "SellerDtls": {
            "Gstin": (firm.get("gstin") or "").strip().upper(),
            "LglNm": firm.get("firm_name", ""),
            "TrdNm": firm.get("firm_name", ""),
            "Addr1": firm.get("address", "") or ".",
            "Addr2": "",
            "Loc":   firm.get("city", ""),
            "Pin":   _pin(firm.get("pincode")),
            "Stcd":  _sc(seller_state),
            "Ph":    firm.get("phone", ""),
            "Em":    firm.get("email", ""),
        },
        "BuyerDtls": {
            "Gstin": buyer_gstin or "URP",
            "LglNm": client.get("name", ""),
            "TrdNm": client.get("name", ""),
            "Pos":   _sc(buyer_state or seller_state),
            "Addr1": client.get("address", "") or ".",
            "Addr2": "",
            "Loc":   client.get("city", ""),
            "Pin":   _pin(client.get("pincode")),
            "Stcd":  _sc(buyer_state),
            "Ph":    client.get("phone", ""),
            "Em":    client.get("email", ""),
        },
        "ItemList": [],
        "ValDtls": {
            "AssVal":    round(invoice.get("subtotal", 0), 2),
            "CgstVal":   round(invoice.get("cgst_total", 0), 2),
            "SgstVal":   round(invoice.get("sgst_total", 0), 2),
            "IgstVal":   round(invoice.get("igst_total", 0), 2),
            "CesVal":    0.0,
            "StCesVal":  0.0,
            "Discount":  round(invoice.get("discount_amt", 0), 2),
            "OthChrg":   0.0,
            "RndOffAmt": 0.0,
            "TotInvVal": round(invoice.get("grand_total", 0), 2),
        },
        "PayDtls": {
            "Nm":      firm.get("bank_name", ""),
            "AccDet":  firm.get("bank_account", ""),
            "Ifsc":    firm.get("bank_ifsc", ""),
            "PayTerm": "30",
            "CrDay":   0,
            "PaidAmt": 0.0,
            "PaymtDue": round(invoice.get("grand_total", 0), 2),
        },
    }

    for idx, it in enumerate(items, 1):
        taxable = round(it.get("taxable_value", 0), 2)
        einv["ItemList"].append({
            "SlNo":     str(idx),
            "PrdDesc":  it.get("description", ""),
            "IsServc":  "N",
            "HsnCd":    it.get("hsn_code", "") or "",
            "Barcde":   "",
            "Qty":      round(float(it.get("quantity", 1)), 3),
            "FreeQty":  0.0,
            "Unit":     (it.get("unit") or "NOS").upper()[:3],
            "UnitPrice": round(float(it.get("unit_price", 0)), 2),
            "TotAmt":   round(float(it.get("quantity", 1)) * float(it.get("unit_price", 0)), 2),
            "Discount":  0.0,
            "PreTaxVal": taxable,
            "AssAmt":    taxable,
            "GstRt":     float(it.get("gst_rate", 0)),
            "IgstAmt":   round(float(it.get("igst_amt", 0)), 2),
            "CgstAmt":   round(float(it.get("cgst_amt", 0)), 2),
            "SgstAmt":   round(float(it.get("sgst_amt", 0)), 2),
            "CesRt":     0.0,
            "CesAmt":    0.0,
            "CesNonAdvlAmt":    0.0,
            "StateCesRt":       0.0,
            "StateCesAmt":      0.0,
            "StateCesNonAdvlAmt": 0.0,
            "OthChrg":   0.0,
            "TotItemVal": round(float(it.get("total_amt", 0)), 2),
            "OrdLineRef": str(idx),
            "OrgCntry":  "",
            "PrdSlNo":   "",
            "BchDtls":   {"Nm": "", "ExpDt": "", "WrDt": ""},
            "AttribDtls": [],
        })

    return einv


# ── QR code generator ─────────────────────────────────────────────────────────

def build_qr_image_bytes(qr_data: str) -> bytes:
    """
    Generate a QR code PNG from the SignedQRCode string returned by IRP.
    Returns PNG bytes.
    """
    import qrcode as _qrc
    qr = _qrc.QRCode(
        version=None,
        error_correction=_qrc.constants.ERROR_CORRECT_M,
        box_size=4,
        border=1,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
