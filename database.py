import sqlite3
import os
import sys
import json
import hashlib
from datetime import datetime, timedelta

# When frozen by PyInstaller, store the DB next to the .exe, not in the temp bundle.
if getattr(sys, "frozen", False):
    _app_dir = os.path.dirname(sys.executable)
else:
    _app_dir = os.path.dirname(os.path.abspath(__file__))

DB_PATH     = os.path.join(_app_dir, "accounting.db")
CONFIG_PATH = os.path.join(_app_dir, "config.json")


def get_config():
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            address TEXT,
            gstin TEXT DEFAULT '',
            state TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sku TEXT UNIQUE NOT NULL,
            description TEXT,
            unit_price REAL NOT NULL DEFAULT 0.0,
            stock_quantity INTEGER NOT NULL DEFAULT 0,
            low_stock_threshold INTEGER NOT NULL DEFAULT 10,
            unit TEXT DEFAULT 'pcs',
            hsn_code TEXT DEFAULT '',
            gst_rate REAL DEFAULT 18.0,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_code TEXT UNIQUE NOT NULL,
            client_id INTEGER NOT NULL,
            status TEXT DEFAULT 'Pending',
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (client_id) REFERENCES clients(id)
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            unit_price REAL NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );

        CREATE TABLE IF NOT EXISTS stock_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            alert_type TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );

        CREATE TABLE IF NOT EXISTS firm_settings (
            id INTEGER PRIMARY KEY DEFAULT 1,
            firm_name TEXT DEFAULT '',
            address TEXT DEFAULT '',
            city TEXT DEFAULT '',
            state TEXT DEFAULT '',
            pincode TEXT DEFAULT '',
            gstin TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            bank_name TEXT DEFAULT '',
            bank_account TEXT DEFAULT '',
            bank_ifsc TEXT DEFAULT '',
            bank_branch TEXT DEFAULT '',
            terms TEXT DEFAULT 'Payment due within 30 days of invoice date.',
            signature_name TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT UNIQUE NOT NULL,
            client_id INTEGER NOT NULL,
            invoice_date TEXT NOT NULL,
            due_date TEXT,
            supply_type TEXT DEFAULT 'intra',
            subtotal REAL NOT NULL DEFAULT 0,
            cgst_total REAL NOT NULL DEFAULT 0,
            sgst_total REAL NOT NULL DEFAULT 0,
            igst_total REAL NOT NULL DEFAULT 0,
            grand_total REAL NOT NULL DEFAULT 0,
            status TEXT DEFAULT 'Draft',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (client_id) REFERENCES clients(id)
        );

        CREATE TABLE IF NOT EXISTS invoice_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            hsn_code TEXT DEFAULT '',
            quantity REAL NOT NULL DEFAULT 1,
            unit TEXT DEFAULT 'pcs',
            unit_price REAL NOT NULL DEFAULT 0,
            gst_rate REAL NOT NULL DEFAULT 18,
            taxable_value REAL NOT NULL DEFAULT 0,
            cgst_rate REAL DEFAULT 0,
            cgst_amt REAL DEFAULT 0,
            sgst_rate REAL DEFAULT 0,
            sgst_amt REAL DEFAULT 0,
            igst_rate REAL DEFAULT 0,
            igst_amt REAL DEFAULT 0,
            total_amt REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id)
        );

        CREATE TABLE IF NOT EXISTS ledger_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            account_type TEXT NOT NULL,
            is_system INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS journal_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_date TEXT NOT NULL,
            narration TEXT NOT NULL,
            reference TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS journal_entry_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            journal_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            debit REAL NOT NULL DEFAULT 0,
            credit REAL NOT NULL DEFAULT 0,
            FOREIGN KEY (journal_id) REFERENCES journal_entries(id),
            FOREIGN KEY (account_id) REFERENCES ledger_accounts(id)
        );

        CREATE TABLE IF NOT EXISTS bank_statement_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            txn_date TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            debit REAL NOT NULL DEFAULT 0,
            credit REAL NOT NULL DEFAULT 0,
            is_matched INTEGER NOT NULL DEFAULT 0,
            matched_je_id INTEGER DEFAULT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (account_id) REFERENCES ledger_accounts(id)
        );

        CREATE TABLE IF NOT EXISTS recurring_invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            frequency TEXT NOT NULL DEFAULT 'monthly',
            next_due TEXT NOT NULL,
            last_generated TEXT DEFAULT NULL,
            notes TEXT DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (client_id) REFERENCES clients(id)
        );

        CREATE TABLE IF NOT EXISTS recurring_invoice_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recurring_id INTEGER NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            hsn_code TEXT DEFAULT '',
            quantity REAL NOT NULL DEFAULT 1,
            unit_price REAL NOT NULL DEFAULT 0,
            gst_rate REAL NOT NULL DEFAULT 18.0,
            FOREIGN KEY (recurring_id) REFERENCES recurring_invoices(id)
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL DEFAULT '',
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'staff',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()
    _migrate_db()


def _migrate_db():
    """Add any missing columns to existing tables without data loss."""
    with get_connection() as conn:
        existing = {col[1] for col in conn.execute("PRAGMA table_info(clients)").fetchall()}
        for col, ddl in [("gstin", "TEXT DEFAULT ''"), ("state", "TEXT DEFAULT ''"),
                         ("credit_limit", "REAL DEFAULT 0")]:
            if col not in existing:
                conn.execute(f"ALTER TABLE clients ADD COLUMN {col} {ddl}")

        existing = {col[1] for col in conn.execute("PRAGMA table_info(products)").fetchall()}
        for col, ddl in [("hsn_code", "TEXT DEFAULT ''"), ("gst_rate", "REAL DEFAULT 18.0"),
                         ("cost_price", "REAL DEFAULT 0.0")]:
            if col not in existing:
                conn.execute(f"ALTER TABLE products ADD COLUMN {col} {ddl}")

        # Seed firm_settings row if absent
        if not conn.execute("SELECT id FROM firm_settings WHERE id=1").fetchone():
            conn.execute("INSERT INTO firm_settings (id) VALUES (1)")

        # New app-preference columns in firm_settings
        fs_cols = {col[1] for col in conn.execute("PRAGMA table_info(firm_settings)").fetchall()}
        for col, ddl in [
            ("invoice_prefix",    "TEXT    DEFAULT 'INV'"),
            ("default_due_days",  "INTEGER DEFAULT 30"),
            ("default_gst_rate",  "REAL    DEFAULT 18.0"),
            ("fiscal_year_start", "INTEGER DEFAULT 4"),
            ("upi_id",            "TEXT    DEFAULT ''"),
            # E-Invoice IRP credentials
            ("irp_client_id",     "TEXT    DEFAULT ''"),
            ("irp_client_secret", "TEXT    DEFAULT ''"),
            ("irp_username",      "TEXT    DEFAULT ''"),
            ("irp_password",      "TEXT    DEFAULT ''"),
            ("einvoice_sandbox",  "INTEGER DEFAULT 1"),
            # E-Way Bill credentials
            ("ewb_username",      "TEXT    DEFAULT ''"),
            ("ewb_password",      "TEXT    DEFAULT ''"),
            ("ewb_sandbox",       "INTEGER DEFAULT 1"),
            # SMTP email settings
            ("smtp_host",         "TEXT    DEFAULT 'smtp.gmail.com'"),
            ("smtp_port",         "INTEGER DEFAULT 587"),
            ("smtp_user",         "TEXT    DEFAULT ''"),
            ("smtp_password",     "TEXT    DEFAULT ''"),
            ("smtp_tls",          "INTEGER DEFAULT 1"),
            ("smtp_from_name",    "TEXT    DEFAULT ''"),
        ]:
            if col not in fs_cols:
                conn.execute(f"ALTER TABLE firm_settings ADD COLUMN {col} {ddl}")

        # Discount column on invoices
        inv_cols = {col[1] for col in conn.execute("PRAGMA table_info(invoices)").fetchall()}
        if "discount_pct" not in inv_cols:
            conn.execute("ALTER TABLE invoices ADD COLUMN discount_pct REAL DEFAULT 0")
        if "discount_amt" not in inv_cols:
            conn.execute("ALTER TABLE invoices ADD COLUMN discount_amt REAL DEFAULT 0")
        # E-Invoice IRN columns
        for col, ddl in [
            ("irn",              "TEXT DEFAULT NULL"),
            ("ack_number",       "TEXT DEFAULT NULL"),
            ("ack_date",         "TEXT DEFAULT NULL"),
            ("einvoice_status",  "TEXT DEFAULT 'Not Generated'"),
            ("signed_qr",        "TEXT DEFAULT NULL"),
        ]:
            if col not in inv_cols:
                conn.execute(f"ALTER TABLE invoices ADD COLUMN {col} {ddl}")

        # E-Way Bill columns
        for col, ddl in [
            ("ewb_number",       "TEXT DEFAULT NULL"),
            ("ewb_date",         "TEXT DEFAULT NULL"),
            ("ewb_valid_until",  "TEXT DEFAULT NULL"),
            ("ewb_status",       "TEXT DEFAULT 'Not Generated'"),
            ("ewb_vehicle_no",   "TEXT DEFAULT NULL"),
            ("ewb_transporter_id","TEXT DEFAULT NULL"),
        ]:
            if col not in inv_cols:
                conn.execute(f"ALTER TABLE invoices ADD COLUMN {col} {ddl}")

        # Credit / Debit Notes tables
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "credit_debit_notes" not in tables:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS credit_debit_notes (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    note_type           TEXT    NOT NULL DEFAULT 'Credit',
                    note_number         TEXT    NOT NULL DEFAULT '',
                    note_date           TEXT    NOT NULL,
                    original_invoice_id INTEGER DEFAULT NULL,
                    original_invoice_no TEXT    DEFAULT '',
                    client_id           INTEGER DEFAULT NULL,
                    client_name         TEXT    DEFAULT '',
                    reason              TEXT    DEFAULT '',
                    supply_type         TEXT    DEFAULT 'intra',
                    subtotal            REAL    DEFAULT 0,
                    cgst_total          REAL    DEFAULT 0,
                    sgst_total          REAL    DEFAULT 0,
                    igst_total          REAL    DEFAULT 0,
                    discount_amt        REAL    DEFAULT 0,
                    grand_total         REAL    DEFAULT 0,
                    status              TEXT    DEFAULT 'Draft',
                    notes               TEXT    DEFAULT '',
                    created_at          TEXT    DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cdn_items (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    note_id         INTEGER NOT NULL,
                    description     TEXT    DEFAULT '',
                    hsn_code        TEXT    DEFAULT '',
                    quantity        REAL    DEFAULT 1,
                    unit            TEXT    DEFAULT 'NOS',
                    unit_price      REAL    DEFAULT 0,
                    gst_rate        REAL    DEFAULT 18,
                    taxable_value   REAL    DEFAULT 0,
                    cgst_amt        REAL    DEFAULT 0,
                    sgst_amt        REAL    DEFAULT 0,
                    igst_amt        REAL    DEFAULT 0,
                    total_amt       REAL    DEFAULT 0
                )
            """)
            conn.commit()

        # Godowns / multi-warehouse tables
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "godowns" not in tables:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS godowns (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT    NOT NULL UNIQUE,
                    location    TEXT    DEFAULT '',
                    address     TEXT    DEFAULT '',
                    is_active   INTEGER DEFAULT 1,
                    created_at  TEXT    DEFAULT (datetime('now'))
                )
            """)
            conn.execute("INSERT OR IGNORE INTO godowns (name, location) VALUES ('Main Warehouse', 'Default')")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS godown_stock (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id  INTEGER NOT NULL,
                    godown_id   INTEGER NOT NULL,
                    quantity    REAL    NOT NULL DEFAULT 0,
                    UNIQUE(product_id, godown_id),
                    FOREIGN KEY (product_id) REFERENCES products(id),
                    FOREIGN KEY (godown_id)  REFERENCES godowns(id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stock_transfers (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id      INTEGER NOT NULL,
                    from_godown_id  INTEGER NOT NULL,
                    to_godown_id    INTEGER NOT NULL,
                    quantity        REAL    NOT NULL DEFAULT 0,
                    transfer_date   TEXT    NOT NULL,
                    notes           TEXT    DEFAULT '',
                    created_at      TEXT    DEFAULT (datetime('now')),
                    FOREIGN KEY (product_id)     REFERENCES products(id),
                    FOREIGN KEY (from_godown_id) REFERENCES godowns(id),
                    FOREIGN KEY (to_godown_id)   REFERENCES godowns(id)
                )
            """)
            conn.commit()

        # TDS entries table
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "tds_entries" not in tables:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tds_entries (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_date      TEXT    NOT NULL,
                    tds_type        TEXT    NOT NULL DEFAULT 'Payable',
                    section         TEXT    NOT NULL DEFAULT '194Q',
                    deductee_name   TEXT    NOT NULL DEFAULT '',
                    deductee_pan    TEXT    DEFAULT '',
                    description     TEXT    DEFAULT '',
                    taxable_amount  REAL    NOT NULL DEFAULT 0,
                    tds_rate        REAL    NOT NULL DEFAULT 0,
                    tds_amount      REAL    NOT NULL DEFAULT 0,
                    surcharge       REAL    DEFAULT 0,
                    cess            REAL    DEFAULT 0,
                    total_tds       REAL    NOT NULL DEFAULT 0,
                    payment_date    TEXT    DEFAULT NULL,
                    challan_no      TEXT    DEFAULT '',
                    challan_date    TEXT    DEFAULT NULL,
                    bsr_code        TEXT    DEFAULT '',
                    status          TEXT    NOT NULL DEFAULT 'Pending',
                    reference_id    INTEGER DEFAULT NULL,
                    reference_type  TEXT    DEFAULT '',
                    notes           TEXT    DEFAULT '',
                    created_at      TEXT    DEFAULT (datetime('now'))
                )
            """)
            conn.commit()

        # Users table (for existing databases that pre-date multi-user)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "users" not in tables:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    full_name TEXT NOT NULL DEFAULT '',
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'staff',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)

        # Payment reminders log
        if "payment_reminders" not in tables:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS payment_reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    invoice_id INTEGER NOT NULL,
                    reminder_date TEXT NOT NULL,
                    method TEXT NOT NULL DEFAULT 'WhatsApp',
                    notes TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
                )
            """)

        # Vendors / Suppliers
        if "vendors" not in tables:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vendors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    gstin TEXT DEFAULT '',
                    phone TEXT DEFAULT '',
                    email TEXT DEFAULT '',
                    address TEXT DEFAULT '',
                    state TEXT DEFAULT '',
                    created_at TEXT DEFAULT (date('now'))
                )
            """)

        # Purchase bills header
        if "purchases" not in tables:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS purchases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vendor_id INTEGER REFERENCES vendors(id),
                    bill_number TEXT DEFAULT '',
                    bill_date TEXT NOT NULL,
                    due_date TEXT DEFAULT '',
                    subtotal REAL DEFAULT 0.0,
                    cgst_total REAL DEFAULT 0.0,
                    sgst_total REAL DEFAULT 0.0,
                    igst_total REAL DEFAULT 0.0,
                    grand_total REAL NOT NULL DEFAULT 0.0,
                    status TEXT DEFAULT 'Unpaid',
                    supply_type TEXT DEFAULT 'intra',
                    notes TEXT DEFAULT '',
                    je_id INTEGER DEFAULT NULL,
                    created_at TEXT DEFAULT (date('now'))
                )
            """)

        # Purchase bill line items
        if "purchase_items" not in tables:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS purchase_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    purchase_id INTEGER NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
                    description TEXT NOT NULL,
                    quantity REAL DEFAULT 1.0,
                    unit_price REAL NOT NULL,
                    gst_rate REAL DEFAULT 18.0,
                    taxable_value REAL NOT NULL DEFAULT 0.0,
                    cgst_amt REAL DEFAULT 0.0,
                    sgst_amt REAL DEFAULT 0.0,
                    igst_amt REAL DEFAULT 0.0,
                    total_amt REAL NOT NULL DEFAULT 0.0
                )
            """)

        # Fixed Assets tables
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "fixed_assets" not in tables:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS fixed_assets (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_code          TEXT    UNIQUE NOT NULL,
                    name                TEXT    NOT NULL,
                    category            TEXT    NOT NULL DEFAULT 'Other',
                    description         TEXT    DEFAULT '',
                    purchase_date       TEXT    NOT NULL,
                    purchase_cost       REAL    NOT NULL DEFAULT 0,
                    salvage_value       REAL    NOT NULL DEFAULT 0,
                    useful_life_years   REAL    NOT NULL DEFAULT 5,
                    depreciation_method TEXT    NOT NULL DEFAULT 'SLM',
                    depreciation_rate   REAL    NOT NULL DEFAULT 20.0,
                    location            TEXT    DEFAULT '',
                    vendor              TEXT    DEFAULT '',
                    invoice_no          TEXT    DEFAULT '',
                    status              TEXT    NOT NULL DEFAULT 'Active',
                    disposal_date       TEXT    DEFAULT NULL,
                    disposal_value      REAL    DEFAULT 0,
                    notes               TEXT    DEFAULT '',
                    created_at          TEXT    DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS asset_depreciation (
                    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id                 INTEGER NOT NULL REFERENCES fixed_assets(id) ON DELETE CASCADE,
                    financial_year           TEXT    NOT NULL,
                    opening_nbv              REAL    NOT NULL DEFAULT 0,
                    depreciation_amount      REAL    NOT NULL DEFAULT 0,
                    accumulated_depreciation REAL    NOT NULL DEFAULT 0,
                    closing_nbv              REAL    NOT NULL DEFAULT 0,
                    entry_date               TEXT    NOT NULL DEFAULT (date('now')),
                    notes                    TEXT    DEFAULT '',
                    created_at               TEXT    DEFAULT (datetime('now')),
                    UNIQUE(asset_id, financial_year)
                )
            """)

        # Payroll tables
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "employees" not in tables:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS employees (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    emp_code            TEXT    UNIQUE NOT NULL,
                    name                TEXT    NOT NULL,
                    designation         TEXT    DEFAULT '',
                    department          TEXT    DEFAULT '',
                    joining_date        TEXT    DEFAULT '',
                    dob                 TEXT    DEFAULT '',
                    pan                 TEXT    DEFAULT '',
                    uan                 TEXT    DEFAULT '',
                    bank_account        TEXT    DEFAULT '',
                    bank_name           TEXT    DEFAULT '',
                    ifsc                TEXT    DEFAULT '',
                    basic               REAL    NOT NULL DEFAULT 0,
                    hra                 REAL    NOT NULL DEFAULT 0,
                    da                  REAL    NOT NULL DEFAULT 0,
                    special_allowance   REAL    NOT NULL DEFAULT 0,
                    other_allowance     REAL    NOT NULL DEFAULT 0,
                    pf_applicable       INTEGER NOT NULL DEFAULT 1,
                    esi_applicable      INTEGER NOT NULL DEFAULT 1,
                    pt_applicable       INTEGER NOT NULL DEFAULT 1,
                    tds_monthly         REAL    NOT NULL DEFAULT 0,
                    status              TEXT    NOT NULL DEFAULT 'Active',
                    notes               TEXT    DEFAULT '',
                    created_at          TEXT    DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS payroll_months (
                    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id             INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                    month                   INTEGER NOT NULL,
                    year                    INTEGER NOT NULL,
                    working_days            REAL    NOT NULL DEFAULT 26,
                    present_days            REAL    NOT NULL DEFAULT 26,
                    lop_days                REAL    NOT NULL DEFAULT 0,
                    basic_earned            REAL    NOT NULL DEFAULT 0,
                    hra_earned              REAL    NOT NULL DEFAULT 0,
                    da_earned               REAL    NOT NULL DEFAULT 0,
                    special_allowance_earned REAL   NOT NULL DEFAULT 0,
                    other_allowance_earned  REAL    NOT NULL DEFAULT 0,
                    gross_earnings          REAL    NOT NULL DEFAULT 0,
                    pf_employee             REAL    NOT NULL DEFAULT 0,
                    esi_employee            REAL    NOT NULL DEFAULT 0,
                    pt_deduction            REAL    NOT NULL DEFAULT 0,
                    tds_deduction           REAL    NOT NULL DEFAULT 0,
                    advance_deduction       REAL    NOT NULL DEFAULT 0,
                    other_deductions        REAL    NOT NULL DEFAULT 0,
                    total_deductions        REAL    NOT NULL DEFAULT 0,
                    net_pay                 REAL    NOT NULL DEFAULT 0,
                    status                  TEXT    NOT NULL DEFAULT 'Draft',
                    payment_date            TEXT    DEFAULT '',
                    payment_ref             TEXT    DEFAULT '',
                    notes                   TEXT    DEFAULT '',
                    created_at              TEXT    DEFAULT (datetime('now')),
                    UNIQUE(employee_id, month, year)
                )
            """)

        # Advance Payments table
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "advance_payments" not in tables:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS advance_payments (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    payment_type     TEXT    NOT NULL DEFAULT 'Received',
                    party_type       TEXT    NOT NULL DEFAULT 'Customer',
                    party_name       TEXT    NOT NULL DEFAULT '',
                    party_id         INTEGER DEFAULT NULL,
                    advance_no       TEXT    NOT NULL DEFAULT '',
                    advance_date     TEXT    NOT NULL,
                    amount           REAL    NOT NULL DEFAULT 0,
                    adjusted_amount  REAL    NOT NULL DEFAULT 0,
                    payment_mode     TEXT    NOT NULL DEFAULT 'Bank Transfer',
                    bank_ref         TEXT    DEFAULT '',
                    linked_ref       TEXT    DEFAULT '',
                    status           TEXT    NOT NULL DEFAULT 'Open',
                    narration        TEXT    DEFAULT '',
                    notes            TEXT    DEFAULT '',
                    created_at       TEXT    DEFAULT (datetime('now'))
                )
            """)

        # Cheques / PDC table
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "cheques" not in tables:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cheques (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    cheque_type      TEXT    NOT NULL DEFAULT 'Inward',
                    cheque_no        TEXT    NOT NULL DEFAULT '',
                    bank_name        TEXT    NOT NULL DEFAULT '',
                    branch           TEXT    DEFAULT '',
                    amount           REAL    NOT NULL DEFAULT 0,
                    cheque_date      TEXT    NOT NULL,
                    party_name       TEXT    NOT NULL DEFAULT '',
                    party_type       TEXT    NOT NULL DEFAULT 'Customer',
                    party_id         INTEGER DEFAULT NULL,
                    received_date    TEXT    DEFAULT '',
                    status           TEXT    NOT NULL DEFAULT 'Pending',
                    presented_date   TEXT    DEFAULT '',
                    cleared_date     TEXT    DEFAULT '',
                    bounce_date      TEXT    DEFAULT '',
                    bounce_reason    TEXT    DEFAULT '',
                    linked_ref       TEXT    DEFAULT '',
                    narration        TEXT    DEFAULT '',
                    notes            TEXT    DEFAULT '',
                    created_at       TEXT    DEFAULT (datetime('now'))
                )
            """)

        conn.commit()

    _seed_ledger_accounts()
    _seed_default_admin()


def _seed_ledger_accounts():
    """Seed the standard chart of accounts (idempotent via INSERT OR IGNORE)."""
    accounts = [
        ("1001", "Accounts Receivable",  "Asset"),
        ("1002", "Cash in Hand",         "Asset"),
        ("1003", "Bank Account",         "Asset"),
        ("1004", "Closing Stock",        "Asset"),
        ("1011", "Input CGST",           "Asset"),
        ("1012", "Input SGST",           "Asset"),
        ("1013", "Input IGST",           "Asset"),
        ("2001", "Accounts Payable",     "Liability"),
        ("2101", "CGST Payable",         "Liability"),
        ("2102", "SGST Payable",         "Liability"),
        ("2103", "IGST Payable",         "Liability"),
        ("3001", "Sales",                "Income"),
        ("3002", "Other Income",         "Income"),
        ("4001", "Purchases",            "Expense"),
        ("4002", "Salaries & Wages",     "Expense"),
        ("4003", "Rent",                 "Expense"),
        ("4004", "Utilities",            "Expense"),
        ("4005", "Other Expenses",       "Expense"),
        ("5001", "Owner's Capital",      "Equity"),
        ("5002", "Retained Earnings",    "Equity"),
    ]
    with get_connection() as conn:
        for code, name, atype in accounts:
            conn.execute(
                "INSERT OR IGNORE INTO ledger_accounts (code,name,account_type,is_system) VALUES (?,?,?,1)",
                (code, name, atype),
            )
        conn.commit()


# ── Users / Auth ──────────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return salt.hex() + ":" + dk.hex()


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
        return dk.hex() == dk_hex
    except Exception:
        return False


def _seed_default_admin():
    with get_connection() as conn:
        exists = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO users (username, full_name, password_hash, role) VALUES (?,?,?,?)",
                ("admin", "Administrator", _hash_password("admin123"), "admin"),
            )
            conn.commit()


def authenticate_user(username: str, password: str):
    """Return user dict on success, None on failure."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username=? AND is_active=1", (username,)
        ).fetchone()
    if row and _verify_password(password, row["password_hash"]):
        return dict(row)
    return None


def get_all_users():
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id,username,full_name,role,is_active,created_at FROM users ORDER BY username"
        ).fetchall()]


def create_user(username: str, full_name: str, password: str, role: str = "staff") -> bool:
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO users (username,full_name,password_hash,role) VALUES (?,?,?,?)",
                (username.strip(), full_name.strip(), _hash_password(password), role),
            )
            conn.commit()
        return True
    except Exception:
        return False


def update_user(user_id: int, username: str, full_name: str, role: str, is_active: bool):
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET username=?,full_name=?,role=?,is_active=? WHERE id=?",
            (username.strip(), full_name.strip(), role, 1 if is_active else 0, user_id),
        )
        conn.commit()


def change_password(user_id: int, new_password: str):
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (_hash_password(new_password), user_id),
        )
        conn.commit()


def delete_user(user_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        conn.commit()


# ── Clients ──────────────────────────────────────────────────────────────────

def get_all_clients():
    with get_connection() as conn:
        return conn.execute("SELECT * FROM clients ORDER BY name").fetchall()


def add_client(name, email="", phone="", address="", gstin="", state="", credit_limit=0.0):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO clients (name, email, phone, address, gstin, state, credit_limit) VALUES (?,?,?,?,?,?,?)",
            (name, email, phone, address, gstin, state, credit_limit),
        )
        conn.commit()


def update_client(client_id, name, email, phone, address, gstin="", state="", credit_limit=0.0):
    with get_connection() as conn:
        conn.execute(
            "UPDATE clients SET name=?,email=?,phone=?,address=?,gstin=?,state=?,credit_limit=? WHERE id=?",
            (name, email, phone, address, gstin, state, credit_limit, client_id),
        )
        conn.commit()


def get_client_outstanding(client_id) -> float:
    """Return total outstanding (unpaid) amount across all non-cancelled invoices for a client."""
    with get_connection() as conn:
        inv_total = conn.execute("""
            SELECT COALESCE(SUM(grand_total), 0) FROM invoices
            WHERE client_id = ? AND status NOT IN ('Paid', 'Cancelled')
        """, (client_id,)).fetchone()[0] or 0.0
        paid_total = conn.execute("""
            SELECT COALESCE(SUM(jl.credit), 0)
            FROM journal_entries je
            JOIN journal_entry_lines jl ON je.id = jl.journal_id
            JOIN ledger_accounts la     ON jl.account_id = la.id AND la.code = '1001'
            JOIN invoices i             ON je.reference = i.invoice_number
            WHERE i.client_id = ? AND jl.credit > 0
        """, (client_id,)).fetchone()[0] or 0.0
    return round(max(inv_total - paid_total, 0.0), 2)


def delete_client(client_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM clients WHERE id=?", (client_id,))
        conn.commit()


# ── Godowns / Warehouses ─────────────────────────────────────────────────────

def get_all_godowns(active_only: bool = False):
    with get_connection() as conn:
        q = "SELECT * FROM godowns"
        if active_only:
            q += " WHERE is_active=1"
        q += " ORDER BY name"
        return conn.execute(q).fetchall()


def get_godown(godown_id: int):
    with get_connection() as conn:
        return conn.execute("SELECT * FROM godowns WHERE id=?", (godown_id,)).fetchone()


def add_godown(name: str, location: str = "", address: str = "") -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO godowns (name, location, address) VALUES (?,?,?)",
            (name.strip(), location.strip(), address.strip()),
        )
        conn.commit()
        return cur.lastrowid


def update_godown(godown_id: int, name: str, location: str, address: str, is_active: int):
    with get_connection() as conn:
        conn.execute(
            "UPDATE godowns SET name=?, location=?, address=?, is_active=? WHERE id=?",
            (name.strip(), location.strip(), address.strip(), is_active, godown_id),
        )
        conn.commit()


def delete_godown(godown_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM godown_stock WHERE godown_id=?", (godown_id,))
        conn.execute("DELETE FROM godowns WHERE id=?", (godown_id,))
        conn.commit()


def get_godown_stock(godown_id: int):
    """Return all products and their quantities for a specific godown."""
    with get_connection() as conn:
        return conn.execute("""
            SELECT p.id, p.name, p.sku, p.unit, p.low_stock_threshold,
                   COALESCE(gs.quantity, 0) AS quantity
            FROM products p
            LEFT JOIN godown_stock gs ON gs.product_id=p.id AND gs.godown_id=?
            ORDER BY p.name
        """, (godown_id,)).fetchall()


def get_product_godown_stock(product_id: int):
    """Return per-godown quantities for one product."""
    with get_connection() as conn:
        return conn.execute("""
            SELECT g.id, g.name AS godown_name, g.location,
                   COALESCE(gs.quantity, 0) AS quantity
            FROM godowns g
            LEFT JOIN godown_stock gs ON gs.godown_id=g.id AND gs.product_id=?
            WHERE g.is_active=1
            ORDER BY g.name
        """, (product_id,)).fetchall()


def set_godown_stock(product_id: int, godown_id: int, quantity: float):
    """Insert or replace godown quantity for a product."""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO godown_stock (product_id, godown_id, quantity)
               VALUES (?,?,?)
               ON CONFLICT(product_id, godown_id) DO UPDATE SET quantity=excluded.quantity""",
            (product_id, godown_id, max(0.0, float(quantity))),
        )
        conn.commit()


def transfer_stock(product_id: int, from_godown_id: int, to_godown_id: int,
                   quantity: float, transfer_date: str, notes: str = "") -> bool:
    """
    Move `quantity` units of product from one godown to another.
    Returns False if the source godown doesn't have enough stock.
    """
    with get_connection() as conn:
        from_row = conn.execute(
            "SELECT quantity FROM godown_stock WHERE product_id=? AND godown_id=?",
            (product_id, from_godown_id),
        ).fetchone()
        from_qty = from_row["quantity"] if from_row else 0.0
        if from_qty < quantity:
            return False

        new_from = from_qty - quantity
        to_row = conn.execute(
            "SELECT quantity FROM godown_stock WHERE product_id=? AND godown_id=?",
            (product_id, to_godown_id),
        ).fetchone()
        new_to = (to_row["quantity"] if to_row else 0.0) + quantity

        conn.execute(
            """INSERT INTO godown_stock (product_id, godown_id, quantity)
               VALUES (?,?,?)
               ON CONFLICT(product_id, godown_id) DO UPDATE SET quantity=excluded.quantity""",
            (product_id, from_godown_id, new_from),
        )
        conn.execute(
            """INSERT INTO godown_stock (product_id, godown_id, quantity)
               VALUES (?,?,?)
               ON CONFLICT(product_id, godown_id) DO UPDATE SET quantity=excluded.quantity""",
            (product_id, to_godown_id, new_to),
        )
        conn.execute(
            """INSERT INTO stock_transfers
               (product_id, from_godown_id, to_godown_id, quantity, transfer_date, notes)
               VALUES (?,?,?,?,?,?)""",
            (product_id, from_godown_id, to_godown_id, quantity, transfer_date, notes),
        )
        conn.commit()
        return True


def get_stock_transfers(product_id: int = None, godown_id: int = None,
                        from_date: str = "", to_date: str = ""):
    with get_connection() as conn:
        q = """
            SELECT st.*, p.name AS product_name, p.sku,
                   fg.name AS from_godown, tg.name AS to_godown
            FROM stock_transfers st
            JOIN products p  ON p.id  = st.product_id
            JOIN godowns  fg ON fg.id = st.from_godown_id
            JOIN godowns  tg ON tg.id = st.to_godown_id
            WHERE 1=1
        """
        params = []
        if product_id:
            q += " AND st.product_id=?"; params.append(product_id)
        if godown_id:
            q += " AND (st.from_godown_id=? OR st.to_godown_id=?)"; params += [godown_id, godown_id]
        if from_date:
            q += " AND st.transfer_date>=?"; params.append(from_date)
        if to_date:
            q += " AND st.transfer_date<=?"; params.append(to_date)
        q += " ORDER BY st.transfer_date DESC, st.id DESC"
        return conn.execute(q, params).fetchall()


def get_godown_summary():
    """Total stock value and product count per godown."""
    with get_connection() as conn:
        return conn.execute("""
            SELECT g.id, g.name, g.location, g.is_active,
                   COUNT(DISTINCT gs.product_id) AS product_count,
                   COALESCE(SUM(gs.quantity), 0) AS total_units,
                   COALESCE(SUM(gs.quantity * p.cost_price), 0) AS stock_value
            FROM godowns g
            LEFT JOIN godown_stock gs ON gs.godown_id = g.id
            LEFT JOIN products      p  ON p.id = gs.product_id
            GROUP BY g.id
            ORDER BY g.name
        """).fetchall()


# ── Products / Stock ──────────────────────────────────────────────────────────

def get_all_products():
    with get_connection() as conn:
        return conn.execute("SELECT * FROM products ORDER BY name").fetchall()


def get_low_stock_products():
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM products WHERE stock_quantity <= low_stock_threshold ORDER BY stock_quantity"
        ).fetchall()


def add_product(name, sku, description, unit_price, stock_quantity,
                low_stock_threshold, unit="pcs", hsn_code="", gst_rate=18.0, cost_price=0.0):
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO products
               (name,sku,description,unit_price,stock_quantity,low_stock_threshold,unit,hsn_code,gst_rate,cost_price)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (name, sku, description, unit_price, stock_quantity,
             low_stock_threshold, unit, hsn_code, gst_rate, cost_price),
        )
        conn.commit()


def update_product(product_id, name, sku, description, unit_price, stock_quantity,
                   low_stock_threshold, unit, hsn_code="", gst_rate=18.0, cost_price=0.0):
    with get_connection() as conn:
        conn.execute(
            """UPDATE products SET name=?,sku=?,description=?,unit_price=?,
               stock_quantity=?,low_stock_threshold=?,unit=?,hsn_code=?,gst_rate=?,cost_price=? WHERE id=?""",
            (name, sku, description, unit_price, stock_quantity,
             low_stock_threshold, unit, hsn_code, gst_rate, cost_price, product_id),
        )
        conn.commit()


def delete_product(product_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM products WHERE id=?", (product_id,))
        conn.commit()


def adjust_stock(product_id, delta):
    with get_connection() as conn:
        conn.execute(
            "UPDATE products SET stock_quantity = MAX(0, stock_quantity + ?) WHERE id=?",
            (delta, product_id),
        )
        conn.commit()


# ── Orders ───────────────────────────────────────────────────────────────────

def get_all_orders():
    with get_connection() as conn:
        return conn.execute(
            """SELECT o.*, c.name AS client_name
               FROM orders o JOIN clients c ON o.client_id = c.id
               ORDER BY o.created_at DESC"""
        ).fetchall()


def get_order_by_code(order_code):
    with get_connection() as conn:
        order = conn.execute(
            """SELECT o.*, c.name AS client_name, c.email AS client_email,
                      c.phone AS client_phone
               FROM orders o JOIN clients c ON o.client_id = c.id
               WHERE o.order_code = ?""",
            (order_code,),
        ).fetchone()
        if not order:
            return None, []
        items = conn.execute(
            """SELECT oi.*, p.name AS product_name, p.sku, p.unit
               FROM order_items oi JOIN products p ON oi.product_id = p.id
               WHERE oi.order_id = ?""",
            (order["id"],),
        ).fetchall()
        return order, items


def add_order(order_code, client_id, items, status="Pending", notes=""):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO orders (order_code, client_id, status, notes) VALUES (?,?,?,?)",
            (order_code, client_id, status, notes),
        )
        order_id = cur.lastrowid
        for item in items:
            cur.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (?,?,?,?)",
                (order_id, item["product_id"], item["quantity"], item["unit_price"]),
            )
            cur.execute(
                "UPDATE products SET stock_quantity = MAX(0, stock_quantity - ?) WHERE id=?",
                (item["quantity"], item["product_id"]),
            )
        conn.commit()
    check_and_create_alerts()


def update_order_status(order_id, status):
    with get_connection() as conn:
        conn.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
        conn.commit()


def delete_order(order_id):
    with get_connection() as conn:
        items = conn.execute(
            "SELECT product_id, quantity FROM order_items WHERE order_id=?", (order_id,)
        ).fetchall()
        for item in items:
            conn.execute(
                "UPDATE products SET stock_quantity = stock_quantity + ? WHERE id=?",
                (item["quantity"], item["product_id"]),
            )
        conn.execute("DELETE FROM order_items WHERE order_id=?", (order_id,))
        conn.execute("DELETE FROM orders WHERE id=?", (order_id,))
        conn.commit()


# ── Alerts ───────────────────────────────────────────────────────────────────

def check_and_create_alerts():
    low = get_low_stock_products()
    with get_connection() as conn:
        for p in low:
            exists = conn.execute(
                "SELECT id FROM stock_alerts WHERE product_id=? AND is_read=0", (p["id"],)
            ).fetchone()
            if not exists:
                msg = (
                    f"LOW STOCK: {p['name']} (SKU: {p['sku']}) — "
                    f"only {p['stock_quantity']} {p['unit']} remaining "
                    f"(threshold: {p['low_stock_threshold']})"
                )
                conn.execute(
                    "INSERT INTO stock_alerts (product_id, alert_type, message) VALUES (?,?,?)",
                    (p["id"], "low_stock", msg),
                )
        conn.commit()


def get_unread_alerts():
    with get_connection() as conn:
        return conn.execute(
            """SELECT sa.*, p.name AS product_name, p.stock_quantity, p.unit
               FROM stock_alerts sa JOIN products p ON sa.product_id = p.id
               WHERE sa.is_read = 0 ORDER BY sa.created_at DESC"""
        ).fetchall()


def mark_alert_read(alert_id):
    with get_connection() as conn:
        conn.execute("UPDATE stock_alerts SET is_read=1 WHERE id=?", (alert_id,))
        conn.commit()


def mark_all_alerts_read():
    with get_connection() as conn:
        conn.execute("UPDATE stock_alerts SET is_read=1")
        conn.commit()


# ── Firm Settings ─────────────────────────────────────────────────────────────

def get_firm_settings():
    with get_connection() as conn:
        return conn.execute("SELECT * FROM firm_settings WHERE id=1").fetchone()


def save_firm_settings(firm_name, address, city, state, pincode, gstin,
                       phone, email, bank_name, bank_account, bank_ifsc,
                       bank_branch, terms, signature_name,
                       invoice_prefix="INV", default_due_days=30,
                       default_gst_rate=18.0, fiscal_year_start=4, upi_id="",
                       irp_client_id="", irp_client_secret="",
                       irp_username="", irp_password="", einvoice_sandbox=1,
                       ewb_username="", ewb_password="", ewb_sandbox=1,
                       smtp_host="smtp.gmail.com", smtp_port=587,
                       smtp_user="", smtp_password="", smtp_tls=1,
                       smtp_from_name=""):
    with get_connection() as conn:
        conn.execute(
            """UPDATE firm_settings SET firm_name=?,address=?,city=?,state=?,pincode=?,
               gstin=?,phone=?,email=?,bank_name=?,bank_account=?,bank_ifsc=?,
               bank_branch=?,terms=?,signature_name=?,
               invoice_prefix=?,default_due_days=?,default_gst_rate=?,fiscal_year_start=?,
               upi_id=?,irp_client_id=?,irp_client_secret=?,
               irp_username=?,irp_password=?,einvoice_sandbox=?,
               ewb_username=?,ewb_password=?,ewb_sandbox=?,
               smtp_host=?,smtp_port=?,smtp_user=?,smtp_password=?,
               smtp_tls=?,smtp_from_name=?
               WHERE id=1""",
            (firm_name, address, city, state, pincode, gstin, phone, email,
             bank_name, bank_account, bank_ifsc, bank_branch, terms, signature_name,
             invoice_prefix, default_due_days, default_gst_rate, fiscal_year_start, upi_id,
             irp_client_id, irp_client_secret, irp_username, irp_password, einvoice_sandbox,
             ewb_username, ewb_password, ewb_sandbox,
             smtp_host, smtp_port, smtp_user, smtp_password, smtp_tls, smtp_from_name),
        )
        conn.commit()


def update_invoice_irn(invoice_id: int, irn: str, ack_number: str,
                       ack_date: str, signed_qr: str = "",
                       status: str = "Generated"):
    with get_connection() as conn:
        conn.execute(
            """UPDATE invoices SET irn=?,ack_number=?,ack_date=?,
               einvoice_status=?,signed_qr=? WHERE id=?""",
            (irn, ack_number, ack_date, status, signed_qr, invoice_id),
        )
        conn.commit()


def update_invoice_ewb(invoice_id: int, ewb_number: str, ewb_date: str,
                       ewb_valid_until: str, vehicle_no: str = "",
                       transporter_id: str = "",
                       status: str = "Generated"):
    with get_connection() as conn:
        conn.execute(
            """UPDATE invoices SET ewb_number=?,ewb_date=?,ewb_valid_until=?,
               ewb_status=?,ewb_vehicle_no=?,ewb_transporter_id=? WHERE id=?""",
            (ewb_number, ewb_date, ewb_valid_until, status,
             vehicle_no, transporter_id, invoice_id),
        )
        conn.commit()


# ── Invoices ──────────────────────────────────────────────────────────────────

def generate_invoice_number():
    firm   = get_firm_settings()
    prefix = (dict(firm).get("invoice_prefix") or "INV") if firm else "INV"
    year   = datetime.now().year
    with get_connection() as conn:
        last = conn.execute(
            "SELECT invoice_number FROM invoices WHERE invoice_number LIKE ? ORDER BY id DESC LIMIT 1",
            (f"{prefix}-{year}-%",),
        ).fetchone()
    num = int(last["invoice_number"].split("-")[-1]) + 1 if last else 1
    return f"{prefix}-{year}-{num:04d}"


def get_all_invoices():
    with get_connection() as conn:
        return conn.execute(
            """SELECT i.*, c.name AS client_name
               FROM invoices i JOIN clients c ON i.client_id = c.id
               ORDER BY i.created_at DESC"""
        ).fetchall()


def get_invoice_full(invoice_id):
    with get_connection() as conn:
        inv = conn.execute(
            """SELECT i.*, c.name AS client_name, c.address AS client_address,
                      c.gstin AS client_gstin, c.state AS client_state,
                      c.email AS client_email, c.phone AS client_phone
               FROM invoices i JOIN clients c ON i.client_id = c.id
               WHERE i.id=?""",
            (invoice_id,),
        ).fetchone()
        items = conn.execute(
            "SELECT * FROM invoice_items WHERE invoice_id=? ORDER BY id",
            (invoice_id,),
        ).fetchall()
        firm = conn.execute("SELECT * FROM firm_settings WHERE id=1").fetchone()
        return inv, items, firm


def get_sales_summary(from_date: str, to_date: str, group_by: str = "day"):
    """
    Return daily or weekly sales totals for a date range.
    group_by: 'day' | 'week'
    Returns a dict with 'rows' (list of period / invoice_count / revenue / avg_order),
    summary KPIs, and top-client / top-product breakdowns.
    """
    with get_connection() as conn:
        # Daily rows
        daily = conn.execute("""
            SELECT invoice_date AS period,
                   COUNT(*) AS invoice_count,
                   COALESCE(SUM(grand_total), 0) AS revenue
            FROM invoices
            WHERE invoice_date BETWEEN ? AND ?
              AND status NOT IN ('Cancelled')
            GROUP BY invoice_date
            ORDER BY invoice_date
        """, (from_date, to_date)).fetchall()

        # Top clients
        top_clients = conn.execute("""
            SELECT c.name, COUNT(*) AS cnt, COALESCE(SUM(i.grand_total), 0) AS revenue
            FROM invoices i JOIN clients c ON i.client_id = c.id
            WHERE i.invoice_date BETWEEN ? AND ?
              AND i.status NOT IN ('Cancelled')
            GROUP BY c.id ORDER BY revenue DESC LIMIT 5
        """, (from_date, to_date)).fetchall()

        # Top products
        top_products = conn.execute("""
            SELECT ii.description, SUM(ii.quantity) AS qty,
                   SUM(ii.quantity * ii.unit_price) AS revenue
            FROM invoice_items ii
            JOIN invoices i ON ii.invoice_id = i.id
            WHERE i.invoice_date BETWEEN ? AND ?
              AND i.status NOT IN ('Cancelled')
            GROUP BY ii.description ORDER BY revenue DESC LIMIT 5
        """, (from_date, to_date)).fetchall()

    daily_rows = [dict(r) for r in daily]

    if group_by == "week":
        from datetime import date as _date, timedelta as _td
        buckets = {}
        for r in daily_rows:
            d = _date.fromisoformat(r["period"])
            week_start = (d - _td(days=d.weekday())).isoformat()
            if week_start not in buckets:
                buckets[week_start] = {"period": week_start, "invoice_count": 0, "revenue": 0.0}
            buckets[week_start]["invoice_count"] += r["invoice_count"]
            buckets[week_start]["revenue"] += r["revenue"]
        rows = sorted(buckets.values(), key=lambda x: x["period"])
    else:
        rows = daily_rows

    for r in rows:
        r["avg_order"] = round(r["revenue"] / r["invoice_count"], 2) if r["invoice_count"] else 0.0
        r["revenue"] = round(r["revenue"], 2)

    total_revenue = round(sum(r["revenue"] for r in rows), 2)
    total_invoices = sum(r["invoice_count"] for r in rows)
    peak = max(rows, key=lambda r: r["revenue"]) if rows else {}
    avg_per_period = round(total_revenue / len(rows), 2) if rows else 0.0

    return {
        "rows":           rows,
        "total_revenue":  total_revenue,
        "total_invoices": total_invoices,
        "peak_period":    peak.get("period", "—"),
        "peak_revenue":   peak.get("revenue", 0.0),
        "avg_per_period": avg_per_period,
        "from_date":      from_date,
        "to_date":        to_date,
        "group_by":       group_by,
        "top_clients":    [dict(r) for r in top_clients],
        "top_products":   [dict(r) for r in top_products],
    }


def get_invoice_by_number(invoice_number: str):
    """Return basic invoice row (with client_name) matching the invoice number, or None."""
    with get_connection() as conn:
        row = conn.execute(
            """SELECT i.id, i.invoice_number, i.invoice_date, i.due_date,
                      i.grand_total, i.status, c.name AS client_name
               FROM invoices i JOIN clients c ON i.client_id = c.id
               WHERE i.invoice_number = ?""",
            (invoice_number,),
        ).fetchone()
    return dict(row) if row else None


def create_invoice(invoice_number, client_id, invoice_date, due_date,
                   supply_type, items, notes="", status="Draft", discount_pct=0.0):
    """
    items: list of dicts with keys:
      description, hsn_code, quantity, unit, unit_price, gst_rate
    discount_pct: overall percentage discount applied to grand total (post-tax)
    Returns the new invoice id.
    """
    subtotal = 0.0
    cgst_total = sgst_total = igst_total = 0.0

    computed = []
    for it in items:
        taxable = round(it["quantity"] * it["unit_price"], 2)
        gst_rate = it["gst_rate"]
        if supply_type == "intra":
            half = gst_rate / 2
            cgst_amt = round(taxable * half / 100, 2)
            sgst_amt = round(taxable * half / 100, 2)
            igst_amt = 0.0
            total_amt = taxable + cgst_amt + sgst_amt
            cgst_total += cgst_amt
            sgst_total += sgst_amt
        else:
            igst_amt = round(taxable * gst_rate / 100, 2)
            cgst_amt = sgst_amt = 0.0
            total_amt = taxable + igst_amt
            igst_total += igst_amt
        subtotal += taxable
        computed.append({**it,
                         "taxable_value": taxable,
                         "cgst_rate": gst_rate / 2 if supply_type == "intra" else 0,
                         "cgst_amt": cgst_amt,
                         "sgst_rate": gst_rate / 2 if supply_type == "intra" else 0,
                         "sgst_amt": sgst_amt,
                         "igst_rate": gst_rate if supply_type == "inter" else 0,
                         "igst_amt": igst_amt,
                         "total_amt": round(total_amt, 2)})

    pre_discount = round(subtotal + cgst_total + sgst_total + igst_total, 2)
    discount_amt  = round(pre_discount * max(0.0, min(100.0, discount_pct)) / 100, 2)
    grand_total   = round(pre_discount - discount_amt, 2)

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO invoices
               (invoice_number,client_id,invoice_date,due_date,supply_type,
                subtotal,cgst_total,sgst_total,igst_total,grand_total,
                discount_pct,discount_amt,status,notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (invoice_number, client_id, invoice_date, due_date, supply_type,
             round(subtotal, 2), round(cgst_total, 2), round(sgst_total, 2),
             round(igst_total, 2), grand_total,
             round(discount_pct, 4), discount_amt, status, notes),
        )
        inv_id = cur.lastrowid
        for it in computed:
            cur.execute(
                """INSERT INTO invoice_items
                   (invoice_id,description,hsn_code,quantity,unit,unit_price,gst_rate,
                    taxable_value,cgst_rate,cgst_amt,sgst_rate,sgst_amt,
                    igst_rate,igst_amt,total_amt)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (inv_id, it["description"], it.get("hsn_code", ""),
                 it["quantity"], it.get("unit", "pcs"), it["unit_price"],
                 it["gst_rate"], it["taxable_value"],
                 it["cgst_rate"], it["cgst_amt"],
                 it["sgst_rate"], it["sgst_amt"],
                 it["igst_rate"], it["igst_amt"], it["total_amt"]),
            )
        conn.commit()
    post_invoice_journal(inv_id)
    return inv_id


def update_invoice_status(invoice_id, status):
    with get_connection() as conn:
        conn.execute("UPDATE invoices SET status=? WHERE id=?", (status, invoice_id))
        conn.commit()


def delete_invoice(invoice_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM invoice_items WHERE invoice_id=?", (invoice_id,))
        conn.execute("DELETE FROM invoices WHERE id=?", (invoice_id,))
        conn.commit()


# ── Ledger / Double-Entry Accounting ─────────────────────────────────────────

def get_all_accounts():
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM ledger_accounts ORDER BY code"
        ).fetchall()


def get_account_balances():
    """Returns all accounts with total_debit, total_credit columns."""
    with get_connection() as conn:
        return conn.execute("""
            SELECT la.id, la.code, la.name, la.account_type, la.is_system,
                   COALESCE(SUM(jl.debit), 0)  AS total_debit,
                   COALESCE(SUM(jl.credit), 0) AS total_credit
            FROM ledger_accounts la
            LEFT JOIN journal_entry_lines jl ON la.id = jl.account_id
            GROUP BY la.id
            ORDER BY la.code
        """).fetchall()


def get_account_transactions(account_id, from_date=None, to_date=None):
    with get_connection() as conn:
        query = """
            SELECT je.entry_date, je.narration, je.reference,
                   jl.debit, jl.credit
            FROM journal_entry_lines jl
            JOIN journal_entries je ON jl.journal_id = je.id
            WHERE jl.account_id = ?
        """
        params = [account_id]
        if from_date:
            query += " AND je.entry_date >= ?"
            params.append(from_date)
        if to_date:
            query += " AND je.entry_date <= ?"
            params.append(to_date)
        query += " ORDER BY je.entry_date, je.id"
        return conn.execute(query, params).fetchall()


def get_pl_report(from_date, to_date):
    """Returns dict with income list, expenses list, totals, net_profit."""
    with get_connection() as conn:
        income = conn.execute("""
            SELECT la.name,
                   COALESCE(SUM(jl.credit), 0) - COALESCE(SUM(jl.debit), 0) AS amount
            FROM ledger_accounts la
            LEFT JOIN journal_entry_lines jl ON la.id = jl.account_id
            LEFT JOIN journal_entries je ON jl.journal_id = je.id
                AND je.entry_date BETWEEN ? AND ?
            WHERE la.account_type = 'Income'
            GROUP BY la.id ORDER BY la.code
        """, (from_date, to_date)).fetchall()

        expenses = conn.execute("""
            SELECT la.name,
                   COALESCE(SUM(jl.debit), 0) - COALESCE(SUM(jl.credit), 0) AS amount
            FROM ledger_accounts la
            LEFT JOIN journal_entry_lines jl ON la.id = jl.account_id
            LEFT JOIN journal_entries je ON jl.journal_id = je.id
                AND je.entry_date BETWEEN ? AND ?
            WHERE la.account_type = 'Expense'
            GROUP BY la.id ORDER BY la.code
        """, (from_date, to_date)).fetchall()

    total_income   = sum(r["amount"] for r in income)
    total_expenses = sum(r["amount"] for r in expenses)
    return {
        "income":          [(r["name"], r["amount"]) for r in income],
        "expenses":        [(r["name"], r["amount"]) for r in expenses],
        "total_income":    total_income,
        "total_expenses":  total_expenses,
        "net_profit":      total_income - total_expenses,
    }


def get_debtors_aging(as_of_date):
    """Returns per-client aging buckets for all unpaid invoices as of as_of_date."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT i.id, i.invoice_number, i.invoice_date,
                   COALESCE(i.due_date, i.invoice_date) AS effective_due,
                   i.grand_total, i.status,
                   c.name AS client_name
            FROM invoices i
            JOIN clients c ON i.client_id = c.id
            WHERE i.status NOT IN ('Paid', 'Cancelled')
              AND i.invoice_date <= ?
            ORDER BY c.name, effective_due
        """, (as_of_date,)).fetchall()

    # Buckets: 0-30, 31-60, 61-90, 91-120, 120+
    BUCKETS = [(0, 30), (31, 60), (61, 90), (91, 120), (121, None)]
    LABELS  = ["0–30 days", "31–60 days", "61–90 days", "91–120 days", "120+ days"]

    from datetime import date as _date
    try:
        ref = _date.fromisoformat(as_of_date)
    except ValueError:
        ref = _date.today()

    # Build per-client dict
    clients = {}
    for r in rows:
        d = dict(r)
        try:
            due = _date.fromisoformat(d["effective_due"])
        except ValueError:
            due = ref
        days_overdue = (ref - due).days          # negative = not yet due
        amt = d["grand_total"]
        name = d["client_name"]

        if name not in clients:
            clients[name] = {"name": name, "invoices": [],
                             "buckets": [0.0] * len(BUCKETS), "total": 0.0}

        # Assign to bucket
        for idx, (lo, hi) in enumerate(BUCKETS):
            if hi is None:
                in_bucket = days_overdue >= lo
            else:
                in_bucket = lo <= days_overdue <= hi
            if in_bucket:
                clients[name]["buckets"][idx] += amt
                break
        else:
            # Not yet due → bucket 0
            clients[name]["buckets"][0] += amt

        clients[name]["total"] += amt
        clients[name]["invoices"].append({
            "invoice_number": d["invoice_number"],
            "invoice_date":   d["invoice_date"],
            "due_date":       d["effective_due"],
            "days_overdue":   days_overdue,
            "amount":         amt,
            "status":         d["status"],
        })

    # Grand totals
    grand_buckets = [0.0] * len(BUCKETS)
    grand_total   = 0.0
    for c in clients.values():
        for i, v in enumerate(c["buckets"]):
            grand_buckets[i] += v
        grand_total += c["total"]

    return {
        "labels":        LABELS,
        "clients":       list(clients.values()),
        "grand_buckets": grand_buckets,
        "grand_total":   grand_total,
    }


def get_cash_flow(from_date, to_date):
    """Direct-method cash flow statement.
    Categorises each cash/bank movement as Operating, Investing, or Financing."""
    with get_connection() as conn:
        cash_rows = conn.execute(
            "SELECT id FROM ledger_accounts WHERE code IN ('1002','1003')"
        ).fetchall()
        if not cash_rows:
            empty = {"opening": 0.0, "closing": 0.0, "net": 0.0,
                     "operating": [], "investing": [], "financing": [],
                     "op_total": 0.0, "inv_total": 0.0, "fin_total": 0.0}
            return empty

        cash_ids = [r["id"] for r in cash_rows]
        ph = ",".join("?" * len(cash_ids))

        # Opening cash balance (all entries strictly before from_date)
        open_bal = conn.execute(f"""
            SELECT COALESCE(SUM(jl.debit - jl.credit), 0) AS bal
            FROM journal_entry_lines jl
            JOIN journal_entries je ON jl.journal_id = je.id
            WHERE jl.account_id IN ({ph}) AND je.entry_date < ?
        """, (*cash_ids, from_date)).fetchone()["bal"]

        # All cash-touching entries in period with dominant counter-account type
        rows = conn.execute(f"""
            SELECT je.id, je.entry_date, je.narration,
                   SUM(CASE WHEN jl.account_id IN ({ph})
                       THEN jl.debit - jl.credit ELSE 0 END)  AS cash_net,
                   (SELECT la2.account_type
                    FROM journal_entry_lines x
                    JOIN ledger_accounts la2 ON x.account_id = la2.id
                    WHERE x.journal_id = je.id
                      AND x.account_id NOT IN ({ph})
                    ORDER BY ABS(x.debit - x.credit) DESC LIMIT 1) AS cat_type
            FROM journal_entries je
            JOIN journal_entry_lines jl ON je.id = jl.journal_id
            WHERE je.entry_date BETWEEN ? AND ?
              AND EXISTS (
                SELECT 1 FROM journal_entry_lines ex
                WHERE ex.journal_id = je.id AND ex.account_id IN ({ph})
              )
            GROUP BY je.id
            HAVING cash_net != 0
            ORDER BY je.entry_date, je.id
        """, (*cash_ids, *cash_ids, from_date, to_date, *cash_ids)).fetchall()

    operating, investing, financing = [], [], []
    for r in rows:
        d = dict(r)
        item = {"date": d["entry_date"], "narration": d["narration"], "amount": d["cash_net"]}
        cat = d.get("cat_type") or ""
        if cat == "Equity":
            financing.append(item)
        else:
            operating.append(item)   # Asset / Expense / Liability / Income → Operating

    op_total  = sum(i["amount"] for i in operating)
    inv_total = sum(i["amount"] for i in investing)
    fin_total = sum(i["amount"] for i in financing)
    net       = op_total + inv_total + fin_total
    return {
        "opening":   open_bal,
        "closing":   open_bal + net,
        "operating": operating,
        "investing":  investing,
        "financing":  financing,
        "op_total":   op_total,
        "inv_total":  inv_total,
        "fin_total":  fin_total,
        "net":        net,
    }


def get_trial_balance(as_of_date):
    """Returns list of account rows with debit/credit columns + totals."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT la.code, la.name, la.account_type,
                   COALESCE(SUM(jl.debit),   0) AS total_dr,
                   COALESCE(SUM(jl.credit),  0) AS total_cr
            FROM ledger_accounts la
            LEFT JOIN journal_entry_lines jl ON la.id = jl.account_id
            LEFT JOIN journal_entries je ON jl.journal_id = je.id
                AND je.entry_date <= ?
            GROUP BY la.id
            ORDER BY la.code
        """, (as_of_date,)).fetchall()

    result = []
    for r in rows:
        d = dict(r)
        net = d["total_dr"] - d["total_cr"]
        d["debit"]  = net if net > 0 else 0.0
        d["credit"] = -net if net < 0 else 0.0
        if d["total_dr"] or d["total_cr"]:   # skip untouched accounts
            result.append(d)

    total_dr = sum(r["debit"]  for r in result)
    total_cr = sum(r["credit"] for r in result)
    return {"rows": result, "total_dr": total_dr, "total_cr": total_cr}


def get_balance_sheet(as_of_date):
    """Returns dict with assets, liabilities, equity lists + net_income and totals."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT la.code, la.name, la.account_type,
                   COALESCE(SUM(jl.debit), 0) - COALESCE(SUM(jl.credit), 0) AS raw_balance
            FROM ledger_accounts la
            LEFT JOIN journal_entry_lines jl ON la.id = jl.account_id
            LEFT JOIN journal_entries je ON jl.journal_id = je.id
                AND je.entry_date <= ?
            WHERE la.account_type IN ('Asset', 'Liability', 'Equity')
            GROUP BY la.id
            ORDER BY la.code
        """, (as_of_date,)).fetchall()

        ni_row = conn.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN la.account_type='Income'  THEN jl.credit - jl.debit ELSE 0 END), 0) -
                COALESCE(SUM(CASE WHEN la.account_type='Expense' THEN jl.debit - jl.credit ELSE 0 END), 0)
                AS net_income
            FROM ledger_accounts la
            LEFT JOIN journal_entry_lines jl ON la.id = jl.account_id
            LEFT JOIN journal_entries je ON jl.journal_id = je.id
                AND je.entry_date <= ?
        """, (as_of_date,)).fetchone()

    assets, liabilities, equity = [], [], []
    for r in rows:
        d = dict(r)
        atype = d["account_type"]
        if atype == "Asset":
            d["balance"] = d["raw_balance"]          # debit-normal: positive = asset
            assets.append(d)
        elif atype == "Liability":
            d["balance"] = -d["raw_balance"]         # credit-normal: negate
            liabilities.append(d)
        elif atype == "Equity":
            d["balance"] = -d["raw_balance"]         # credit-normal: negate
            equity.append(d)

    net_income    = dict(ni_row)["net_income"] if ni_row else 0.0
    total_assets  = sum(d["balance"] for d in assets)
    total_liab    = sum(d["balance"] for d in liabilities)
    total_equity  = sum(d["balance"] for d in equity) + net_income
    return {
        "assets":       assets,
        "liabilities":  liabilities,
        "equity":       equity,
        "net_income":   net_income,
        "total_assets": total_assets,
        "total_liab":   total_liab,
        "total_equity": total_equity,
    }


def add_journal_entry(entry_date, narration, reference, lines):
    """
    lines: list of {"account_id": int, "debit": float, "credit": float}
    Raises ValueError if entry is unbalanced.
    """
    total_dr = sum(l["debit"]  for l in lines)
    total_cr = sum(l["credit"] for l in lines)
    if abs(total_dr - total_cr) > 0.01:
        raise ValueError(f"Journal not balanced: Dr {total_dr:.2f} ≠ Cr {total_cr:.2f}")
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO journal_entries (entry_date,narration,reference) VALUES (?,?,?)",
            (entry_date, narration, reference),
        )
        je_id = cur.lastrowid
        for l in lines:
            cur.execute(
                "INSERT INTO journal_entry_lines (journal_id,account_id,debit,credit) VALUES (?,?,?,?)",
                (je_id, l["account_id"], l["debit"], l["credit"]),
            )
        conn.commit()
    return je_id


def get_all_journal_entries(limit=200):
    with get_connection() as conn:
        return conn.execute("""
            SELECT je.id, je.entry_date, je.narration, je.reference, je.created_at,
                   COUNT(jl.id) AS line_count,
                   COALESCE(SUM(jl.debit), 0) AS total_dr
            FROM journal_entries je
            LEFT JOIN journal_entry_lines jl ON je.id = jl.journal_id
            GROUP BY je.id
            ORDER BY je.entry_date DESC, je.id DESC
            LIMIT ?
        """, (limit,)).fetchall()


def post_invoice_journal(invoice_id):
    """Auto-post double-entry lines when an invoice is saved."""
    with get_connection() as conn:
        inv = conn.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv:
            return

        def acct(code):
            row = conn.execute("SELECT id FROM ledger_accounts WHERE code=?", (code,)).fetchone()
            return row[0] if row else None

        ar    = acct("1001")
        sales = acct("3001")
        if not (ar and sales):
            return

        client = conn.execute("SELECT name FROM clients WHERE id=?", (inv["client_id"],)).fetchone()
        narration = f"Sales Invoice {inv['invoice_number']} - {client['name'] if client else 'Client'}"

        lines = [
            {"account_id": ar,    "debit": inv["grand_total"], "credit": 0.0},
            {"account_id": sales, "debit": 0.0, "credit": inv["subtotal"]},
        ]
        if inv["supply_type"] == "intra":
            cgst = acct("2101")
            sgst = acct("2102")
            if cgst and inv["cgst_total"] > 0:
                lines.append({"account_id": cgst, "debit": 0.0, "credit": inv["cgst_total"]})
            if sgst and inv["sgst_total"] > 0:
                lines.append({"account_id": sgst, "debit": 0.0, "credit": inv["sgst_total"]})
        else:
            igst = acct("2103")
            if igst and inv["igst_total"] > 0:
                lines.append({"account_id": igst, "debit": 0.0, "credit": inv["igst_total"]})

    add_journal_entry(inv["invoice_date"], narration, inv["invoice_number"], lines)


# ── Payment Receipts ──────────────────────────────────────────────────────────

def record_payment(invoice_id, amount, payment_date, payment_mode, reference=""):
    """
    Post a customer payment against an invoice.
    Dr Cash/Bank, Cr Accounts Receivable.
    Marks the invoice Paid when the amount covers the grand total.
    """
    with get_connection() as conn:
        inv = conn.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv:
            raise ValueError("Invoice not found.")

        def acct(code):
            row = conn.execute("SELECT id FROM ledger_accounts WHERE code=?", (code,)).fetchone()
            return row[0] if row else None

        ar       = acct("1001")
        pay_code = "1002" if payment_mode == "Cash" else "1003"
        pay_acct = acct(pay_code)
        if not (ar and pay_acct):
            raise ValueError("Ledger accounts not found. Please re-open the app to reseed them.")

        client = conn.execute("SELECT name FROM clients WHERE id=?", (inv["client_id"],)).fetchone()
        client_name = client["name"] if client else "Client"
        ref_part    = f" – Ref: {reference}" if reference else ""
        narration   = f"Payment Received – {inv['invoice_number']} – {client_name}{ref_part}"
        grand_total = inv["grand_total"]
        inv_id_local = invoice_id
        inv_number   = inv["invoice_number"]

    # Get prior paid BEFORE recording the new entry (avoid double-counting)
    prior_paid = sum(p["amount"] for p in get_invoice_payments(inv_id_local))

    lines = [
        {"account_id": pay_acct, "debit": amount, "credit": 0.0},
        {"account_id": ar,       "debit": 0.0,    "credit": amount},
    ]
    # Always use invoice_number as reference for consistent lookup
    add_journal_entry(payment_date, narration, inv_number, lines)

    total_paid = prior_paid + amount
    if total_paid >= grand_total:
        update_invoice_status(inv_id_local, "Paid")
    else:
        update_invoice_status(inv_id_local, "Partially Paid")


def get_invoice_outstanding(invoice_id):
    """Returns (grand_total, total_paid, outstanding) for an invoice."""
    with get_connection() as conn:
        inv = conn.execute("SELECT grand_total FROM invoices WHERE id=?", (invoice_id,)).fetchone()
    if not inv:
        return 0.0, 0.0, 0.0
    grand_total = inv["grand_total"]
    payments = get_invoice_payments(invoice_id)
    total_paid = sum(p["amount"] for p in payments)
    return grand_total, round(total_paid, 2), round(grand_total - total_paid, 2)


def get_invoice_payments(invoice_id):
    """Returns journal lines that credited Accounts Receivable for this invoice."""
    with get_connection() as conn:
        inv = conn.execute("SELECT invoice_number FROM invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv:
            return []
        return conn.execute("""
            SELECT je.entry_date, je.narration, je.reference,
                   jl.credit AS amount, pay_la.name AS paid_into
            FROM journal_entries je
            JOIN journal_entry_lines jl  ON je.id = jl.journal_id
            JOIN ledger_accounts la      ON jl.account_id = la.id AND la.code = '1001'
            LEFT JOIN journal_entry_lines jl2  ON je.id = jl2.journal_id AND jl2.debit > 0
            LEFT JOIN ledger_accounts pay_la   ON jl2.account_id = pay_la.id
            WHERE jl.credit > 0
              AND je.reference = ?
            ORDER BY je.entry_date, je.id
        """, (inv["invoice_number"],)).fetchall()


def get_all_payments(from_date=None, to_date=None):
    """Return all payment transactions across all invoices for the Payments page."""
    with get_connection() as conn:
        q = """
            SELECT je.id AS je_id, je.entry_date AS payment_date,
                   je.narration, je.reference AS invoice_number,
                   jl_cr.credit AS amount,
                   la_dr.code AS pay_code, la_dr.name AS pay_account_name
            FROM journal_entries je
            JOIN journal_entry_lines jl_cr ON je.id = jl_cr.journal_id
            JOIN ledger_accounts la_cr ON jl_cr.account_id = la_cr.id AND la_cr.code = '1001'
            LEFT JOIN journal_entry_lines jl_dr ON je.id = jl_dr.journal_id AND jl_dr.debit > 0
            LEFT JOIN ledger_accounts la_dr ON jl_dr.account_id = la_dr.id
            WHERE jl_cr.credit > 0
              AND je.narration LIKE 'Payment Received%'
        """
        params = []
        if from_date:
            q += " AND je.entry_date >= ?"
            params.append(from_date)
        if to_date:
            q += " AND je.entry_date <= ?"
            params.append(to_date)
        q += " ORDER BY je.entry_date DESC, je.id DESC"
        rows = conn.execute(q, params).fetchall()

        result = []
        for r in rows:
            d = dict(r)
            inv_row = conn.execute(
                """SELECT i.id, c.name AS client_name
                   FROM invoices i JOIN clients c ON i.client_id = c.id
                   WHERE i.invoice_number = ?""",
                (d["invoice_number"],)
            ).fetchone()
            d["client_name"] = inv_row["client_name"] if inv_row else "—"
            d["invoice_id"]  = inv_row["id"] if inv_row else None
            pc = d.get("pay_code", "")
            d["payment_mode"] = "Cash" if pc == "1002" else ("Bank / UPI" if pc == "1003" else (d.get("pay_account_name") or "—"))
            result.append(d)
        return result


# ── Vendors ───────────────────────────────────────────────────────────────────

def add_vendor(name, gstin="", phone="", email="", address="", state=""):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO vendors (name,gstin,phone,email,address,state) VALUES (?,?,?,?,?,?)",
            (name, gstin, phone, email, address, state),
        )
        conn.commit()


def get_all_vendors():
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM vendors ORDER BY name"
        ).fetchall()


def update_vendor(vendor_id, name, gstin="", phone="", email="", address="", state=""):
    with get_connection() as conn:
        conn.execute(
            "UPDATE vendors SET name=?,gstin=?,phone=?,email=?,address=?,state=? WHERE id=?",
            (name, gstin, phone, email, address, state, vendor_id),
        )
        conn.commit()


def delete_vendor(vendor_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM vendors WHERE id=?", (vendor_id,))
        conn.commit()


# ── Purchases ─────────────────────────────────────────────────────────────────

def save_purchase(vendor_id, bill_number, bill_date, due_date, items,
                  supply_type="intra", notes="", payment_mode="Credit"):
    """
    Save a purchase bill, line items, and post the journal entry.
    payment_mode: 'Credit' → Cr 2001 Accounts Payable
                  'Cash'   → Cr 1002 Cash in Hand
                  'Bank'   → Cr 1003 Bank Account
    Returns the new purchase id.
    """
    subtotal   = round(sum(it["taxable_value"] for it in items), 2)
    cgst_total = round(sum(it.get("cgst_amt", 0) for it in items), 2)
    sgst_total = round(sum(it.get("sgst_amt", 0) for it in items), 2)
    igst_total = round(sum(it.get("igst_amt", 0) for it in items), 2)
    grand_total = round(subtotal + cgst_total + sgst_total + igst_total, 2)

    status = "Paid" if payment_mode in ("Cash", "Bank") else "Unpaid"
    vendor_name = "Supplier"

    with get_connection() as conn:
        if vendor_id:
            v = conn.execute("SELECT name FROM vendors WHERE id=?", (vendor_id,)).fetchone()
            if v:
                vendor_name = v["name"]

        conn.execute("""
            INSERT INTO purchases (vendor_id, bill_number, bill_date, due_date,
                subtotal, cgst_total, sgst_total, igst_total, grand_total,
                status, supply_type, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (vendor_id, bill_number, bill_date, due_date,
              subtotal, cgst_total, sgst_total, igst_total, grand_total,
              status, supply_type, notes))
        purchase_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        for it in items:
            conn.execute("""
                INSERT INTO purchase_items
                    (purchase_id, description, quantity, unit_price, gst_rate,
                     taxable_value, cgst_amt, sgst_amt, igst_amt, total_amt)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (purchase_id, it["description"], it["quantity"], it["unit_price"],
                  it["gst_rate"], it["taxable_value"],
                  it.get("cgst_amt", 0), it.get("sgst_amt", 0), it.get("igst_amt", 0),
                  it["total_amt"]))

        def acct(code):
            r = conn.execute("SELECT id FROM ledger_accounts WHERE code=?", (code,)).fetchone()
            return r[0] if r else None

        purch_acct = acct("4001")
        cr_code = "1002" if payment_mode == "Cash" else ("1003" if payment_mode == "Bank" else "2001")
        cr_acct = acct(cr_code)

        narration = f"Purchase – {bill_number or 'No Bill#'} – {vendor_name}"
        lines = [{"account_id": purch_acct, "debit": subtotal, "credit": 0.0}]

        if supply_type == "intra":
            if cgst_total > 0:
                lines.append({"account_id": acct("1011"), "debit": cgst_total, "credit": 0.0})
            if sgst_total > 0:
                lines.append({"account_id": acct("1012"), "debit": sgst_total, "credit": 0.0})
        else:
            if igst_total > 0:
                lines.append({"account_id": acct("1013"), "debit": igst_total, "credit": 0.0})

        lines.append({"account_id": cr_acct, "debit": 0.0, "credit": grand_total})

        conn.commit()

    add_journal_entry(bill_date, narration, bill_number or str(purchase_id), lines)

    with get_connection() as conn:
        je = conn.execute(
            "SELECT id FROM journal_entries ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if je:
            conn.execute("UPDATE purchases SET je_id=? WHERE id=?", (je[0], purchase_id))
        conn.commit()

    return purchase_id


def get_all_purchases(from_date=None, to_date=None, vendor_id=None, status=None):
    with get_connection() as conn:
        q = """
            SELECT p.*, COALESCE(v.name, '—') AS vendor_name
            FROM purchases p
            LEFT JOIN vendors v ON p.vendor_id = v.id
            WHERE 1=1
        """
        params = []
        if from_date:
            q += " AND p.bill_date >= ?"
            params.append(from_date)
        if to_date:
            q += " AND p.bill_date <= ?"
            params.append(to_date)
        if vendor_id:
            q += " AND p.vendor_id = ?"
            params.append(vendor_id)
        if status and status != "All":
            q += " AND p.status = ?"
            params.append(status)
        q += " ORDER BY p.bill_date DESC, p.id DESC"
        return conn.execute(q, params).fetchall()


def get_purchase_full(purchase_id):
    with get_connection() as conn:
        p = conn.execute(
            "SELECT p.*, COALESCE(v.name,'—') AS vendor_name FROM purchases p LEFT JOIN vendors v ON p.vendor_id=v.id WHERE p.id=?",
            (purchase_id,)
        ).fetchone()
        items = conn.execute(
            "SELECT * FROM purchase_items WHERE purchase_id=? ORDER BY id",
            (purchase_id,)
        ).fetchall()
    return p, items


def update_purchase_status(purchase_id, status):
    with get_connection() as conn:
        conn.execute("UPDATE purchases SET status=? WHERE id=?", (status, purchase_id))
        conn.commit()


def delete_purchase(purchase_id):
    with get_connection() as conn:
        je_id = conn.execute("SELECT je_id FROM purchases WHERE id=?", (purchase_id,)).fetchone()
        if je_id and je_id[0]:
            conn.execute("DELETE FROM journal_entry_lines WHERE journal_id=?", (je_id[0],))
            conn.execute("DELETE FROM journal_entries WHERE id=?", (je_id[0],))
        conn.execute("DELETE FROM purchase_items WHERE purchase_id=?", (purchase_id,))
        conn.execute("DELETE FROM purchases WHERE id=?", (purchase_id,))
        conn.commit()


def record_purchase_payment(purchase_id, amount, payment_date, payment_mode, reference=""):
    """Dr Accounts Payable, Cr Cash/Bank. Marks purchase Paid when fully covered."""
    with get_connection() as conn:
        p = conn.execute("SELECT * FROM purchases WHERE id=?", (purchase_id,)).fetchone()
        if not p:
            raise ValueError("Purchase not found.")

        def acct(code):
            r = conn.execute("SELECT id FROM ledger_accounts WHERE code=?", (code,)).fetchone()
            return r[0] if r else None

        ap      = acct("2001")
        pay_code = "1002" if payment_mode == "Cash" else "1003"
        pay_acct = acct(pay_code)
        if not (ap and pay_acct):
            raise ValueError("Ledger accounts not found.")

        vendor_name = conn.execute(
            "SELECT COALESCE(v.name,'Supplier') FROM purchases p LEFT JOIN vendors v ON p.vendor_id=v.id WHERE p.id=?",
            (purchase_id,)
        ).fetchone()[0]
        ref_part  = f" – Ref: {reference}" if reference else ""
        narration = f"Payment to {vendor_name} – {p['bill_number'] or 'Bill#' + str(purchase_id)}{ref_part}"

    lines = [
        {"account_id": ap,       "debit": amount, "credit": 0.0},
        {"account_id": pay_acct, "debit": 0.0,    "credit": amount},
    ]
    add_journal_entry(payment_date, narration, reference or (p["bill_number"] or str(purchase_id)), lines)
    update_purchase_status(purchase_id, "Paid")


# ── Client Statement ─────────────────────────────────────────────────────────

def get_client_statement(client_id):
    """Return all invoices for a client with payment totals and running balance."""
    with get_connection() as conn:
        invoices = conn.execute("""
            SELECT i.id, i.invoice_number, i.invoice_date, i.due_date,
                   i.grand_total, i.status
            FROM invoices i
            WHERE i.client_id = ?
            ORDER BY i.invoice_date, i.id
        """, (client_id,)).fetchall()

        rows = []
        running_balance = 0.0
        for inv in invoices:
            inv = dict(inv)
            # sum of payments against this invoice
            paid = conn.execute("""
                SELECT COALESCE(SUM(jl.credit), 0) AS paid
                FROM journal_entries je
                JOIN journal_entry_lines jl ON je.id = jl.journal_id
                JOIN ledger_accounts la     ON jl.account_id = la.id AND la.code = '1001'
                WHERE jl.credit > 0 AND je.reference = ?
            """, (inv["invoice_number"],)).fetchone()["paid"] or 0.0

            outstanding = round(inv["grand_total"] - paid, 2)
            running_balance += outstanding
            rows.append({**inv, "paid": paid,
                         "outstanding": outstanding,
                         "running_balance": running_balance})
        return rows


# ── Client Ledger ────────────────────────────────────────────────────────────

def get_client_ledger(client_id, from_date: str, to_date: str):
    """
    Return a date-ranged client ledger with opening balance, per-line transactions
    (invoices issued + payments received), running balance, and totals.
    """
    with get_connection() as conn:
        # Opening balance = total invoiced before from_date minus total paid before from_date
        ob_inv = conn.execute("""
            SELECT COALESCE(SUM(grand_total), 0) AS v
            FROM invoices
            WHERE client_id = ? AND invoice_date < ? AND status NOT IN ('Cancelled')
        """, (client_id, from_date)).fetchone()["v"] or 0.0

        ob_paid = conn.execute("""
            SELECT COALESCE(SUM(jl.credit), 0) AS v
            FROM journal_entries je
            JOIN journal_entry_lines jl ON je.id = jl.journal_id
            JOIN ledger_accounts la     ON jl.account_id = la.id AND la.code = '1001'
            JOIN invoices i             ON je.reference = i.invoice_number
            WHERE i.client_id = ? AND jl.credit > 0 AND je.entry_date < ?
        """, (client_id, from_date)).fetchone()["v"] or 0.0

        opening = round(ob_inv - ob_paid, 2)

        # Invoices in period
        inv_rows = conn.execute("""
            SELECT invoice_date AS txn_date, invoice_number AS ref,
                   'Invoice' AS txn_type, grand_total AS debit, 0.0 AS credit,
                   status
            FROM invoices
            WHERE client_id = ? AND invoice_date BETWEEN ? AND ?
              AND status NOT IN ('Cancelled')
            ORDER BY invoice_date, id
        """, (client_id, from_date, to_date)).fetchall()

        # Payments in period (journal lines crediting AR acct 1001 for this client's invoices)
        pay_rows = conn.execute("""
            SELECT je.entry_date AS txn_date, je.reference AS ref,
                   'Payment' AS txn_type, 0.0 AS debit, jl.credit AS credit,
                   '' AS status
            FROM journal_entries je
            JOIN journal_entry_lines jl ON je.id = jl.journal_id
            JOIN ledger_accounts la     ON jl.account_id = la.id AND la.code = '1001'
            JOIN invoices i             ON je.reference = i.invoice_number
            WHERE i.client_id = ? AND jl.credit > 0
              AND je.entry_date BETWEEN ? AND ?
            ORDER BY je.entry_date, je.id
        """, (client_id, from_date, to_date)).fetchall()

        # client info
        client = conn.execute(
            "SELECT id, name, phone, email, gstin FROM clients WHERE id = ?",
            (client_id,)).fetchone()

    # Merge and sort by date
    rows = [dict(r) for r in inv_rows] + [dict(r) for r in pay_rows]
    rows.sort(key=lambda r: (r["txn_date"], 0 if r["txn_type"] == "Invoice" else 1))

    total_debit = total_credit = 0.0
    running = opening
    for r in rows:
        running = round(running + r["debit"] - r["credit"], 2)
        r["balance"] = running
        total_debit  += r["debit"]
        total_credit += r["credit"]

    closing = round(opening + total_debit - total_credit, 2)
    return {
        "client":       dict(client) if client else {},
        "from_date":    from_date,
        "to_date":      to_date,
        "opening":      opening,
        "rows":         rows,
        "total_debit":  round(total_debit, 2),
        "total_credit": round(total_credit, 2),
        "closing":      closing,
    }


# ── Payment Reminders ────────────────────────────────────────────────────────

def get_outstanding_invoices_for_reminders(filter_type="all"):
    """
    Return outstanding (unpaid/partial) invoices with days overdue and reminder history.
    filter_type: 'all' | 'overdue' | 'due_soon' (due within 7 days)
    """
    today = datetime.now().date().isoformat()
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT i.id, i.invoice_number, i.invoice_date, i.due_date,
                   i.grand_total, i.status,
                   c.id AS client_id, c.name AS client_name,
                   c.phone AS client_phone, c.email AS client_email,
                   COALESCE(paid.paid_total, 0) AS paid_total,
                   i.grand_total - COALESCE(paid.paid_total, 0) AS balance_due,
                   COALESCE(rem.reminder_count, 0) AS reminder_count,
                   rem.last_reminder_date
            FROM invoices i
            JOIN clients c ON i.client_id = c.id
            LEFT JOIN (
                SELECT i2.id AS inv_id, COALESCE(SUM(jl.credit), 0) AS paid_total
                FROM journal_entries je
                JOIN journal_entry_lines jl ON je.id = jl.journal_id
                JOIN ledger_accounts la ON jl.account_id = la.id AND la.code = '1001'
                JOIN invoices i2 ON je.reference = i2.invoice_number
                WHERE jl.credit > 0
                GROUP BY i2.id
            ) paid ON paid.inv_id = i.id
            LEFT JOIN (
                SELECT invoice_id,
                       COUNT(*) AS reminder_count,
                       MAX(reminder_date) AS last_reminder_date
                FROM payment_reminders
                GROUP BY invoice_id
            ) rem ON rem.invoice_id = i.id
            WHERE i.status NOT IN ('Paid', 'Cancelled')
            ORDER BY i.due_date ASC, c.name ASC
        """).fetchall()

    result = []
    for r in rows:
        d = dict(r)
        due = d.get("due_date") or d.get("invoice_date") or today
        try:
            from datetime import date as _date
            days_overdue = (_date.fromisoformat(today) - _date.fromisoformat(due)).days
        except Exception:
            days_overdue = 0
        d["days_overdue"] = days_overdue
        if filter_type == "overdue" and days_overdue <= 0:
            continue
        if filter_type == "due_soon" and not (0 >= days_overdue >= -7):
            continue
        result.append(d)
    return result


def add_payment_reminder(invoice_id, reminder_date, method="WhatsApp", notes=""):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO payment_reminders (invoice_id, reminder_date, method, notes) VALUES (?,?,?,?)",
            (invoice_id, reminder_date, method, notes),
        )
        conn.commit()


def get_reminder_history(invoice_id):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT reminder_date, method, notes FROM payment_reminders WHERE invoice_id=? ORDER BY reminder_date DESC",
            (invoice_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Stock Valuation ───────────────────────────────────────────────────────────

def get_stock_valuation(include_zero_stock=False):
    """
    Return per-product stock valuation using cost_price (or unit_price as fallback).
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, sku, unit, hsn_code, gst_rate, unit_price, cost_price, "
            "stock_quantity, low_stock_threshold FROM products ORDER BY name"
        ).fetchall()

    items = []
    total_cost_val = 0.0
    total_sale_val = 0.0
    low_stock_count = 0
    zero_stock_count = 0

    for r in rows:
        d = dict(r)
        qty = d["stock_quantity"]
        cost = d["cost_price"] if d["cost_price"] > 0 else d["unit_price"]
        sale = d["unit_price"]
        cost_val = round(qty * cost, 2)
        sale_val = round(qty * sale, 2)
        margin_pct = round((sale - cost) / sale * 100, 1) if sale > 0 else 0.0

        if qty == 0:
            zero_stock_count += 1
        if qty <= d["low_stock_threshold"]:
            low_stock_count += 1

        if not include_zero_stock and qty == 0:
            continue

        d["cost"]       = cost
        d["cost_value"] = cost_val
        d["sale_value"] = sale_val
        d["margin_pct"] = margin_pct
        items.append(d)

        total_cost_val += cost_val
        total_sale_val += sale_val

    return {
        "items": items,
        "total_cost_value": round(total_cost_val, 2),
        "total_sale_value": round(total_sale_val, 2),
        "total_margin": round(total_sale_val - total_cost_val, 2),
        "total_margin_pct": round((total_sale_val - total_cost_val) / total_sale_val * 100, 1)
                            if total_sale_val > 0 else 0.0,
        "low_stock_count":  low_stock_count,
        "zero_stock_count": zero_stock_count,
        "item_count":       len(items),
    }


# ── Recurring Invoices ───────────────────────────────────────────────────────

def get_recurring_invoices():
    with get_connection() as conn:
        return conn.execute("""
            SELECT r.*, c.name AS client_name
            FROM recurring_invoices r
            JOIN clients c ON r.client_id = c.id
            ORDER BY r.next_due, r.id
        """).fetchall()


def get_recurring_invoice(recurring_id):
    with get_connection() as conn:
        rec = conn.execute(
            "SELECT r.*, c.name AS client_name FROM recurring_invoices r "
            "JOIN clients c ON r.client_id = c.id WHERE r.id = ?",
            (recurring_id,)).fetchone()
        items = conn.execute(
            "SELECT * FROM recurring_invoice_items WHERE recurring_id = ? ORDER BY id",
            (recurring_id,)).fetchall()
        return dict(rec) if rec else None, [dict(i) for i in items]


def create_recurring_invoice(client_id, frequency, next_due, notes, items):
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO recurring_invoices (client_id, frequency, next_due, notes) VALUES (?,?,?,?)",
            (client_id, frequency, next_due, notes))
        rid = cur.lastrowid
        for it in items:
            conn.execute(
                "INSERT INTO recurring_invoice_items "
                "(recurring_id, description, hsn_code, quantity, unit_price, gst_rate) "
                "VALUES (?,?,?,?,?,?)",
                (rid, it["description"], it.get("hsn_code",""),
                 it["quantity"], it["unit_price"], it.get("gst_rate", 18.0)))
        conn.commit()
        return rid


def toggle_recurring_invoice(recurring_id, is_active):
    with get_connection() as conn:
        conn.execute("UPDATE recurring_invoices SET is_active=? WHERE id=?",
                     (1 if is_active else 0, recurring_id))
        conn.commit()


def delete_recurring_invoice(recurring_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM recurring_invoice_items WHERE recurring_id=?", (recurring_id,))
        conn.execute("DELETE FROM recurring_invoices WHERE id=?", (recurring_id,))
        conn.commit()


def _next_due_date(current_due, frequency):
    from datetime import datetime
    import calendar
    d = datetime.strptime(current_due, "%Y-%m-%d")
    if frequency == "weekly":
        from datetime import timedelta
        return (d + timedelta(weeks=1)).strftime("%Y-%m-%d")
    months_map = {"monthly": 1, "quarterly": 3, "yearly": 12}
    months = months_map.get(frequency, 1)
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return datetime(year, month, day).strftime("%Y-%m-%d")


def generate_due_recurring_invoices():
    """Generate invoices for all active recurring templates whose next_due <= today."""
    from datetime import date
    today = date.today().strftime("%Y-%m-%d")
    generated = []
    with get_connection() as conn:
        due = conn.execute(
            "SELECT * FROM recurring_invoices WHERE is_active=1 AND next_due <= ?",
            (today,)).fetchall()
        for rec in due:
            rec = dict(rec)
            items = conn.execute(
                "SELECT * FROM recurring_invoice_items WHERE recurring_id=?",
                (rec["id"],)).fetchall()

            # Build invoice number
            last = conn.execute(
                "SELECT invoice_number FROM invoices ORDER BY id DESC LIMIT 1").fetchone()
            prefix = "INV"
            num = 1
            if last:
                parts = last["invoice_number"].split("-")
                try:
                    num = int(parts[-1]) + 1
                except (ValueError, IndexError):
                    pass
            inv_no = f"{prefix}-{num:04d}"

            # Insert invoice
            cur2 = conn.execute(
                "INSERT INTO invoices (invoice_number, client_id, invoice_date, due_date, "
                "supply_type, notes, status) VALUES (?,?,?,?,?,?,?)",
                (inv_no, rec["client_id"], today, today, "intra", rec["notes"] or "", "Draft"))
            inv_id = cur2.lastrowid

            subtotal = 0.0
            cgst_total = igst_total = sgst_total = 0.0
            for it in items:
                it = dict(it)
                qty = it["quantity"]
                price = it["unit_price"]
                gst = it["gst_rate"]
                line = qty * price
                subtotal += line
                # intra: split CGST+SGST
                half = line * gst / 100 / 2
                cgst_total += half
                sgst_total += half
                half_rate = gst / 2
                half_amt = line * gst / 100 / 2
                conn.execute(
                    "INSERT INTO invoice_items (invoice_id, description, hsn_code, quantity, "
                    "unit_price, gst_rate, taxable_value, cgst_rate, cgst_amt, sgst_rate, sgst_amt, "
                    "igst_rate, igst_amt, total_amt) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (inv_id, it["description"], it.get("hsn_code",""),
                     qty, price, gst, line,
                     half_rate, half_amt, half_rate, half_amt, 0, 0,
                     line + half_amt * 2))

            grand = subtotal + cgst_total + sgst_total + igst_total
            conn.execute(
                "UPDATE invoices SET subtotal=?, cgst_total=?, sgst_total=?, igst_total=?, grand_total=? WHERE id=?",
                (subtotal, cgst_total, sgst_total, igst_total, grand, inv_id))

            # Advance next_due
            new_due = _next_due_date(rec["next_due"], rec["frequency"])
            conn.execute(
                "UPDATE recurring_invoices SET next_due=?, last_generated=? WHERE id=?",
                (new_due, today, rec["id"]))

            generated.append(inv_no)
        conn.commit()
    return generated


# ── Expense Entries ───────────────────────────────────────────────────────────

def get_expense_entries(from_date=None, to_date=None, search=None):
    """Returns expense journal entries optionally filtered by date range and search term."""
    clauses = ["la.account_type = 'Expense'", "jl.debit > 0"]
    params  = []
    if from_date:
        clauses.append("je.entry_date >= ?")
        params.append(from_date)
    if to_date:
        clauses.append("je.entry_date <= ?")
        params.append(to_date)
    where = " AND ".join(clauses)
    rows = []
    with get_connection() as conn:
        rows = conn.execute(f"""
            SELECT je.id, je.entry_date, je.narration, je.reference,
                   la.name  AS expense_account,
                   jl.debit AS amount,
                   COALESCE(pay_la.name, '—') AS paid_from
            FROM journal_entries je
            JOIN journal_entry_lines jl  ON je.id = jl.journal_id
            JOIN ledger_accounts la      ON jl.account_id = la.id
            LEFT JOIN journal_entry_lines jl2  ON je.id = jl2.journal_id AND jl2.credit > 0
            LEFT JOIN ledger_accounts pay_la   ON jl2.account_id = pay_la.id
            WHERE {where}
            ORDER BY je.entry_date DESC, je.id DESC
        """, params).fetchall()
    if search:
        q = search.strip().lower()
        rows = [r for r in rows
                if q in (r["narration"] or "").lower()
                or q in (r["expense_account"] or "").lower()
                or q in (r["reference"] or "").lower()]
    return rows


def delete_expense_entry(je_id):
    """Delete a journal entry and its lines (used for expenses)."""
    with get_connection() as conn:
        conn.execute("DELETE FROM journal_entry_lines WHERE journal_id=?", (je_id,))
        conn.execute("DELETE FROM journal_entries WHERE id=?", (je_id,))
        conn.commit()


def get_expense_summary(from_date, to_date):
    """Returns per-account expense totals for a date range."""
    with get_connection() as conn:
        return conn.execute("""
            SELECT la.name AS account_name,
                   COALESCE(SUM(jl.debit), 0) AS total
            FROM ledger_accounts la
            LEFT JOIN journal_entry_lines jl ON la.id = jl.account_id
            LEFT JOIN journal_entries je      ON jl.journal_id = je.id
                AND je.entry_date BETWEEN ? AND ?
            WHERE la.account_type = 'Expense'
            GROUP BY la.id
            HAVING total > 0
            ORDER BY total DESC
        """, (from_date, to_date)).fetchall()


# ── Dashboard Stats ───────────────────────────────────────────────────────────

def get_dashboard_stats():
    today = datetime.now()
    month_start = today.replace(day=1).strftime("%Y-%m-%d")
    today_s = today.strftime("%Y-%m-%d")
    with get_connection() as conn:
        total_clients = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
        total_products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        total_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        low_stock_count = conn.execute(
            "SELECT COUNT(*) FROM products WHERE stock_quantity <= low_stock_threshold"
        ).fetchone()[0]
        pending_orders = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE status='Pending'"
        ).fetchone()[0]
        total_stock_value = conn.execute(
            "SELECT SUM(unit_price * stock_quantity) FROM products"
        ).fetchone()[0] or 0.0
        total_invoiced = conn.execute(
            "SELECT SUM(grand_total) FROM invoices WHERE status != 'Cancelled'"
        ).fetchone()[0] or 0.0
        total_paid = conn.execute(
            "SELECT SUM(grand_total) FROM invoices WHERE status = 'Paid'"
        ).fetchone()[0] or 0.0
        revenue_this_month = conn.execute(
            "SELECT COALESCE(SUM(grand_total), 0) FROM invoices "
            "WHERE invoice_date >= ? AND status = 'Paid'",
            (month_start,),
        ).fetchone()[0]
        outstanding = conn.execute(
            "SELECT COALESCE(SUM(grand_total), 0) FROM invoices "
            "WHERE status IN ('Sent', 'Draft')"
        ).fetchone()[0]
        expenses_this_month = conn.execute(
            """SELECT COALESCE(SUM(jl.debit), 0)
               FROM journal_entry_lines jl
               JOIN journal_entries je ON jl.journal_id = je.id
               JOIN ledger_accounts la ON la.id = jl.account_id
               WHERE la.account_type = 'Expense' AND je.entry_date >= ?""",
            (month_start,),
        ).fetchone()[0]
        overdue_count = conn.execute(
            "SELECT COUNT(*) FROM invoices "
            "WHERE due_date < ? AND status NOT IN ('Paid', 'Cancelled')",
            (today_s,),
        ).fetchone()[0]
        net_this_month = revenue_this_month - expenses_this_month
        return {
            "total_clients": total_clients,
            "total_products": total_products,
            "total_orders": total_orders,
            "low_stock_count": low_stock_count,
            "pending_orders": pending_orders,
            "total_stock_value": total_stock_value,
            "total_invoiced": total_invoiced,
            "total_paid": total_paid,
            "revenue_this_month": revenue_this_month,
            "outstanding": outstanding,
            "expenses_this_month": expenses_this_month,
            "overdue_count": overdue_count,
            "net_this_month": net_this_month,
        }


def get_recent_invoices(limit=8, search="", status_filter="All"):
    with get_connection() as conn:
        clauses = []
        params  = []
        if search:
            clauses.append("(i.invoice_number LIKE ? OR c.name LIKE ?)")
            params += [f"%{search}%", f"%{search}%"]
        if status_filter and status_filter != "All":
            clauses.append("i.status = ?")
            params.append(status_filter)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(
            f"""SELECT i.id, i.invoice_number, c.name AS client_name,
                       i.invoice_date, i.grand_total, i.status, i.due_date
                FROM invoices i
                LEFT JOIN clients c ON i.client_id = c.id
                {where}
                ORDER BY i.id DESC LIMIT ?""",
            params + [limit],
        ).fetchall()
    return [dict(r) for r in rows]


def get_overdue_invoices():
    today_s = datetime.now().strftime("%Y-%m-%d")
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT i.id, i.invoice_number, c.name AS client_name,
                      i.invoice_date, i.grand_total, i.status, i.due_date
               FROM invoices i
               LEFT JOIN clients c ON i.client_id = c.id
               WHERE i.due_date < ? AND i.status NOT IN ('Paid', 'Cancelled')
               ORDER BY i.due_date ASC""",
            (today_s,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Seed Demo Data ────────────────────────────────────────────────────────────

def seed_demo_data():
    with get_connection() as conn:
        exists = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    if exists:
        return

    clients = [
        ("Apex Industries", "apex@example.com", "9876543210",
         "12 MG Road, Bangalore", "29AABCU9603R1ZP", "Karnataka"),
        ("BlueStar Corp", "blue@example.com", "9123456780",
         "45 Anna Salai, Chennai", "33AACFB1234Q1Z5", "Tamil Nadu"),
        ("CrestLine Ltd", "crest@example.com", "9345678901",
         "77 Park Street, Kolkata", "19AAACR5055K1Z5", "West Bengal"),
    ]
    for c in clients:
        add_client(*c)

    products = [
        ("Steel Rods (12mm)", "STL-ROD-12", "Mild steel rods 12mm", 350.00, 250, 50, "kg", "7213", 18.0),
        ("Cement Bags (OPC 53)", "CEM-OPC-53", "Portland Cement 50kg bags", 420.00, 8, 20, "bags", "2523", 28.0),
        ("Copper Wire (2.5mm)", "COP-WIR-25", "Electrical copper wire 2.5mm", 120.00, 500, 100, "mtrs", "7408", 18.0),
        ("PVC Pipes (3/4 inch)", "PVC-375", "PVC pressure pipe 3/4 inch", 85.00, 300, 60, "pcs", "3917", 18.0),
        ("MS Sheets (2mm)", "MS-SHT-2", "Mild steel sheets 2mm", 1200.00, 15, 25, "sheets", "7208", 18.0),
        ("Electrical Conduit", "ELC-CON-20", "20mm electrical conduit pipe", 45.00, 5, 30, "pcs", "3917", 18.0),
    ]
    for p in products:
        add_product(*p)

    with get_connection() as conn:
        clients_db = conn.execute("SELECT id FROM clients").fetchall()
        products_db = conn.execute("SELECT id, unit_price FROM products").fetchall()

    orders_data = [
        ("ORD-2024-001", clients_db[0]["id"], [
            {"product_id": products_db[0]["id"], "quantity": 50, "unit_price": products_db[0]["unit_price"]},
            {"product_id": products_db[2]["id"], "quantity": 100, "unit_price": products_db[2]["unit_price"]},
        ], "Delivered"),
        ("ORD-2024-002", clients_db[1]["id"], [
            {"product_id": products_db[1]["id"], "quantity": 3, "unit_price": products_db[1]["unit_price"]},
            {"product_id": products_db[3]["id"], "quantity": 20, "unit_price": products_db[3]["unit_price"]},
        ], "Pending"),
        ("ORD-2024-003", clients_db[2]["id"], [
            {"product_id": products_db[4]["id"], "quantity": 5, "unit_price": products_db[4]["unit_price"]},
        ], "Processing"),
    ]
    for order_code, client_id, items, status in orders_data:
        add_order(order_code, client_id, items, status)

    # Seed firm settings
    with get_connection() as conn:
        conn.execute(
            """UPDATE firm_settings SET
               firm_name='Your Firm Name Pvt. Ltd.',
               address='123 Business Park, Industrial Area',
               city='Bangalore',state='Karnataka',pincode='560001',
               gstin='29AAAAA0000A1Z5',phone='9876500000',
               email='accounts@yourfirm.com',
               bank_name='State Bank of India',bank_account='123456789012',
               bank_ifsc='SBIN0001234',bank_branch='MG Road Branch',
               terms='Payment due within 30 days of invoice date.\nLate payments attract 2% interest per month.',
               signature_name='Authorised Signatory'
               WHERE id=1"""
        )
        conn.commit()

    check_and_create_alerts()


# ── GST Reports ───────────────────────────────────────────────────────────────

def get_gstr1(from_date, to_date):
    """GSTR-1: Outward supply details for a period."""
    with get_connection() as conn:
        inv_rows = conn.execute("""
            SELECT i.invoice_number, i.invoice_date, i.supply_type,
                   i.subtotal, i.cgst_total, i.sgst_total, i.igst_total, i.grand_total,
                   c.name AS client_name, COALESCE(c.gstin,'') AS client_gstin,
                   COALESCE(c.state,'') AS client_state
            FROM invoices i
            JOIN clients c ON i.client_id = c.id
            WHERE i.invoice_date BETWEEN ? AND ?
              AND i.status NOT IN ('Cancelled')
            ORDER BY i.invoice_date, i.invoice_number
        """, (from_date, to_date)).fetchall()

        hsn_rows = conn.execute("""
            SELECT ii.hsn_code,
                   MAX(ii.description) AS description,
                   MAX(ii.unit)        AS unit,
                   SUM(ii.quantity)    AS total_qty,
                   SUM(ii.taxable_value)                            AS taxable_value,
                   SUM(ii.cgst_amt)                                 AS cgst,
                   SUM(ii.sgst_amt)                                 AS sgst,
                   SUM(ii.igst_amt)                                 AS igst,
                   SUM(ii.cgst_amt + ii.sgst_amt + ii.igst_amt)    AS total_tax
            FROM invoice_items ii
            JOIN invoices i ON ii.invoice_id = i.id
            WHERE i.invoice_date BETWEEN ? AND ?
              AND i.status NOT IN ('Cancelled')
            GROUP BY ii.hsn_code
            ORDER BY ii.hsn_code
        """, (from_date, to_date)).fetchall()

    b2b, b2c = [], []
    for r in inv_rows:
        d = dict(r)
        (b2b if d["client_gstin"] else b2c).append(d)

    def _tot(lst):
        return {
            "taxable": sum(r["subtotal"]    for r in lst),
            "cgst":    sum(r["cgst_total"]  for r in lst),
            "sgst":    sum(r["sgst_total"]  for r in lst),
            "igst":    sum(r["igst_total"]  for r in lst),
            "grand":   sum(r["grand_total"] for r in lst),
        }

    all_ = b2b + b2c
    return {
        "b2b": b2b, "b2b_total": _tot(b2b),
        "b2c": b2c, "b2c_total": _tot(b2c),
        "hsn": [dict(r) for r in hsn_rows],
        "grand": _tot(all_),
    }


def get_gstr3b(from_date, to_date):
    """GSTR-3B: Monthly summary return data (output tax only; ITC not tracked)."""
    with get_connection() as conn:
        row = conn.execute("""
            SELECT COALESCE(SUM(subtotal),    0) AS taxable_value,
                   COALESCE(SUM(cgst_total),  0) AS cgst,
                   COALESCE(SUM(sgst_total),  0) AS sgst,
                   COALESCE(SUM(igst_total),  0) AS igst,
                   COALESCE(SUM(grand_total), 0) AS grand_total
            FROM invoices
            WHERE invoice_date BETWEEN ? AND ?
              AND status NOT IN ('Cancelled')
        """, (from_date, to_date)).fetchone()
    d = dict(row)
    total_out = d["cgst"] + d["sgst"] + d["igst"]
    return {
        "taxable_value": d["taxable_value"],
        "cgst_out":  d["cgst"],
        "sgst_out":  d["sgst"],
        "igst_out":  d["igst"],
        "total_out": total_out,
        "cgst_itc":  0.0,
        "sgst_itc":  0.0,
        "igst_itc":  0.0,
        "total_itc": 0.0,
        "net_cgst":  d["cgst"],
        "net_sgst":  d["sgst"],
        "net_igst":  d["igst"],
        "net_total": total_out,
        "grand_total": d["grand_total"],
    }


# ── P&L Monthly Trend ────────────────────────────────────────────────────────

def get_pl_monthly(from_date, to_date):
    """Return month-by-month income and expense totals between two dates."""
    with get_connection() as conn:
        inc = conn.execute("""
            SELECT strftime('%Y-%m', je.entry_date) AS month,
                   COALESCE(SUM(jl.credit),0) - COALESCE(SUM(jl.debit),0) AS amount
            FROM journal_entry_lines jl
            JOIN journal_entries je ON jl.journal_id = je.id
            JOIN ledger_accounts la ON jl.account_id = la.id
            WHERE la.account_type = 'Income'
              AND je.entry_date BETWEEN ? AND ?
            GROUP BY month ORDER BY month
        """, (from_date, to_date)).fetchall()
        exp = conn.execute("""
            SELECT strftime('%Y-%m', je.entry_date) AS month,
                   COALESCE(SUM(jl.debit),0) - COALESCE(SUM(jl.credit),0) AS amount
            FROM journal_entry_lines jl
            JOIN journal_entries je ON jl.journal_id = je.id
            JOIN ledger_accounts la ON jl.account_id = la.id
            WHERE la.account_type = 'Expense'
              AND je.entry_date BETWEEN ? AND ?
            GROUP BY month ORDER BY month
        """, (from_date, to_date)).fetchall()
    months = sorted(set(r["month"] for r in inc) | set(r["month"] for r in exp))
    inc_map = {r["month"]: r["amount"] for r in inc}
    exp_map = {r["month"]: r["amount"] for r in exp}
    return [{"month": m, "income": inc_map.get(m, 0.0), "expense": exp_map.get(m, 0.0)}
            for m in months]


# ── GST Rate-wise Summary ─────────────────────────────────────────────────────

def get_gst_summary(from_date, to_date):
    """Return rate-wise GST breakdown and KPI totals."""
    with get_connection() as conn:
        totals = conn.execute("""
            SELECT COUNT(*) AS invoice_count,
                   COALESCE(SUM(subtotal),0)    AS taxable_value,
                   COALESCE(SUM(cgst_total),0)  AS cgst,
                   COALESCE(SUM(sgst_total),0)  AS sgst,
                   COALESCE(SUM(igst_total),0)  AS igst,
                   COALESCE(SUM(grand_total),0) AS grand_total
            FROM invoices
            WHERE invoice_date BETWEEN ? AND ?
              AND status NOT IN ('Cancelled')
        """, (from_date, to_date)).fetchone()

        rate_rows = conn.execute("""
            SELECT ii.gst_rate,
                   COUNT(DISTINCT i.id)         AS invoice_count,
                   SUM(ii.quantity)             AS total_qty,
                   SUM(ii.taxable_value)        AS taxable_value,
                   SUM(ii.cgst_amt)             AS cgst,
                   SUM(ii.sgst_amt)             AS sgst,
                   SUM(ii.igst_amt)             AS igst,
                   SUM(ii.cgst_amt + ii.sgst_amt + ii.igst_amt) AS total_tax
            FROM invoice_items ii
            JOIN invoices i ON ii.invoice_id = i.id
            WHERE i.invoice_date BETWEEN ? AND ?
              AND i.status NOT IN ('Cancelled')
            GROUP BY ii.gst_rate
            ORDER BY ii.gst_rate
        """, (from_date, to_date)).fetchall()

        monthly = conn.execute("""
            SELECT strftime('%Y-%m', invoice_date) AS month,
                   COUNT(*) AS invoice_count,
                   COALESCE(SUM(subtotal),0)   AS taxable_value,
                   COALESCE(SUM(cgst_total),0) AS cgst,
                   COALESCE(SUM(sgst_total),0) AS sgst,
                   COALESCE(SUM(igst_total),0) AS igst,
                   COALESCE(SUM(grand_total),0) AS grand_total
            FROM invoices
            WHERE invoice_date BETWEEN ? AND ?
              AND status NOT IN ('Cancelled')
            GROUP BY month ORDER BY month
        """, (from_date, to_date)).fetchall()

    d = dict(totals)
    return {
        "invoice_count":  d["invoice_count"],
        "taxable_value":  d["taxable_value"],
        "cgst":           d["cgst"],
        "sgst":           d["sgst"],
        "igst":           d["igst"],
        "grand_total":    d["grand_total"],
        "total_tax":      d["cgst"] + d["sgst"] + d["igst"],
        "rate_rows":      [dict(r) for r in rate_rows],
        "monthly":        [dict(r) for r in monthly],
    }


# ── Bank Reconciliation ──────────────────────────────────────────────────────

def get_bank_accounts():
    """Return ledger accounts suitable for bank reconciliation (Cash/Bank assets)."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT id, code, name FROM ledger_accounts
            WHERE account_type = 'Asset'
            ORDER BY code
        """).fetchall()
    return [dict(r) for r in rows]


def get_bank_statement_lines(account_id, from_date, to_date):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT id, txn_date, description, debit, credit, is_matched, matched_je_id
            FROM bank_statement_lines
            WHERE account_id = ? AND txn_date BETWEEN ? AND ?
            ORDER BY txn_date, id
        """, (account_id, from_date, to_date)).fetchall()
    return [dict(r) for r in rows]


def add_bank_statement_line(account_id, txn_date, description, debit, credit):
    with get_connection() as conn:
        cur = conn.execute("""
            INSERT INTO bank_statement_lines (account_id, txn_date, description, debit, credit)
            VALUES (?, ?, ?, ?, ?)
        """, (account_id, txn_date, description, float(debit), float(credit)))
        conn.commit()
        return cur.lastrowid


def delete_bank_statement_line(line_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM bank_statement_lines WHERE id = ?", (line_id,))
        conn.commit()


def get_ledger_entries_for_recon(account_id, from_date, to_date):
    """Journal entries that touch this account in the period, with matched status."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT je.id, je.entry_date, je.narration, je.reference,
                   SUM(jl.debit) - SUM(jl.credit) AS net_dr,
                   COALESCE((
                       SELECT 1 FROM bank_statement_lines bsl
                       WHERE bsl.matched_je_id = je.id AND bsl.is_matched = 1
                       LIMIT 1
                   ), 0) AS is_matched
            FROM journal_entries je
            JOIN journal_entry_lines jl ON jl.journal_id = je.id
            WHERE jl.account_id = ? AND je.entry_date BETWEEN ? AND ?
            GROUP BY je.id
            ORDER BY je.entry_date, je.id
        """, (account_id, from_date, to_date)).fetchall()
    return [dict(r) for r in rows]


def match_bank_line(bank_line_id, je_id):
    with get_connection() as conn:
        conn.execute("""
            UPDATE bank_statement_lines
            SET is_matched = 1, matched_je_id = ?
            WHERE id = ?
        """, (je_id, bank_line_id))
        conn.commit()


def unmatch_bank_line(bank_line_id):
    with get_connection() as conn:
        conn.execute("""
            UPDATE bank_statement_lines
            SET is_matched = 0, matched_je_id = NULL
            WHERE id = ?
        """, (bank_line_id,))
        conn.commit()


def get_reconciliation_summary(account_id, from_date, to_date):
    with get_connection() as conn:
        bs = dict(conn.execute("""
            SELECT
                COALESCE(SUM(credit), 0) - COALESCE(SUM(debit), 0)         AS bank_net,
                COALESCE(SUM(CASE WHEN is_matched=0 THEN credit-debit ELSE 0 END), 0)
                                                                             AS unmatched_bank_net,
                COUNT(*)                                                     AS total_lines,
                SUM(CASE WHEN is_matched=0 THEN 1 ELSE 0 END)               AS unmatched_lines,
                SUM(CASE WHEN is_matched=1 THEN 1 ELSE 0 END)               AS matched_lines
            FROM bank_statement_lines
            WHERE account_id = ? AND txn_date BETWEEN ? AND ?
        """, (account_id, from_date, to_date)).fetchone())

        lb = dict(conn.execute("""
            SELECT COALESCE(SUM(jl.debit), 0) - COALESCE(SUM(jl.credit), 0) AS ledger_net
            FROM journal_entry_lines jl
            JOIN journal_entries je ON jl.journal_id = je.id
            WHERE jl.account_id = ? AND je.entry_date BETWEEN ? AND ?
        """, (account_id, from_date, to_date)).fetchone())

        unmatched_je = conn.execute("""
            SELECT COUNT(DISTINCT je.id) AS cnt
            FROM journal_entries je
            JOIN journal_entry_lines jl ON jl.journal_id = je.id
            WHERE jl.account_id = ? AND je.entry_date BETWEEN ? AND ?
              AND NOT EXISTS (
                  SELECT 1 FROM bank_statement_lines bsl
                  WHERE bsl.matched_je_id = je.id AND bsl.is_matched = 1
              )
        """, (account_id, from_date, to_date)).fetchone()["cnt"]

    return {
        "bank_net":          bs["bank_net"],
        "ledger_net":        lb["ledger_net"],
        "difference":        bs["bank_net"] - lb["ledger_net"],
        "total_bank_lines":  bs["total_lines"],
        "matched_lines":     bs["matched_lines"],
        "unmatched_bank":    bs["unmatched_lines"],
        "unmatched_je":      unmatched_je,
    }


def import_bank_csv(account_id, filepath):
    """Parse a bank statement CSV and insert rows. Returns (count, errors)."""
    import csv
    DATE_KEYS    = {"date", "txn date", "value date", "posting date", "transaction date"}
    DESC_KEYS    = {"description", "narration", "particulars", "reference", "remarks", "details"}
    DEBIT_KEYS   = {"debit", "withdrawal", "withdrawal amt", "dr", "debit amount"}
    CREDIT_KEYS  = {"credit", "deposit", "deposit amt", "cr", "credit amount"}
    AMOUNT_KEYS  = {"amount", "net amount", "transaction amount"}

    errors = []
    count  = 0
    try:
        with open(filepath, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return 0, ["CSV has no headers"]
            norm = {h.strip().lower(): h for h in reader.fieldnames}
            date_col   = next((norm[k] for k in DATE_KEYS   if k in norm), None)
            desc_col   = next((norm[k] for k in DESC_KEYS   if k in norm), None)
            debit_col  = next((norm[k] for k in DEBIT_KEYS  if k in norm), None)
            credit_col = next((norm[k] for k in CREDIT_KEYS if k in norm), None)
            amt_col    = next((norm[k] for k in AMOUNT_KEYS if k in norm), None)
            if not date_col:
                return 0, ["Could not detect Date column. Expected: Date / Txn Date / Value Date"]
            if not desc_col:
                desc_col = reader.fieldnames[1] if len(reader.fieldnames) > 1 else None

            for i, row in enumerate(reader, start=2):
                try:
                    raw_date = (row.get(date_col) or "").strip()
                    if not raw_date:
                        continue
                    # Parse common date formats
                    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d-%b-%Y", "%d/%b/%Y"):
                        try:
                            txn_date = datetime.strptime(raw_date, fmt).strftime("%Y-%m-%d")
                            break
                        except ValueError:
                            continue
                    else:
                        errors.append(f"Row {i}: unrecognised date '{raw_date}'")
                        continue

                    desc = (row.get(desc_col) or "").strip() if desc_col else ""

                    if debit_col and credit_col:
                        raw_dr = (row.get(debit_col)  or "0").replace(",", "").strip()
                        raw_cr = (row.get(credit_col) or "0").replace(",", "").strip()
                        debit  = float(raw_dr or 0)
                        credit = float(raw_cr or 0)
                    elif amt_col:
                        raw_amt = (row.get(amt_col) or "0").replace(",", "").strip()
                        amt    = float(raw_amt or 0)
                        debit  = -amt if amt < 0 else 0
                        credit =  amt if amt > 0 else 0
                    else:
                        errors.append(f"Row {i}: cannot detect debit/credit columns")
                        continue

                    add_bank_statement_line(account_id, txn_date, desc, debit, credit)
                    count += 1
                except Exception as e:
                    errors.append(f"Row {i}: {e}")
    except Exception as e:
        return 0, [str(e)]
    return count, errors


# ── Backup ───────────────────────────────────────────────────────────────────

def get_backup_folder():
    folder = os.path.join(_app_dir, "Backups")
    os.makedirs(folder, exist_ok=True)
    return folder


def auto_backup(keep=7):
    """Save a timestamped backup to Backups/ and prune old ones. Returns dest path."""
    import shutil
    folder = get_backup_folder()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(folder, f"accounting_backup_{stamp}.db")
    shutil.copy2(DB_PATH, dest)
    # Prune: keep newest `keep` files
    backups = sorted(
        [f for f in os.listdir(folder) if f.startswith("accounting_backup_") and f.endswith(".db")],
        reverse=True,
    )
    for old in backups[keep:]:
        try:
            os.remove(os.path.join(folder, old))
        except OSError:
            pass
    return dest


def list_backups():
    """Return list of dicts {filename, path, size_kb, modified} newest first."""
    folder = get_backup_folder()
    files = sorted(
        [f for f in os.listdir(folder) if f.startswith("accounting_backup_") and f.endswith(".db")],
        reverse=True,
    )
    result = []
    for f in files:
        p = os.path.join(folder, f)
        try:
            stat = os.stat(p)
            result.append({
                "filename": f,
                "path": p,
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%d %b %Y  %H:%M"),
            })
        except OSError:
            pass
    return result


# ── Global Search ─────────────────────────────────────────────────────────────

def global_search(query):
    """Search clients, products, and invoices. Returns dict with lists."""
    q = f"%{query}%"
    with get_connection() as conn:
        clients = conn.execute(
            "SELECT id, name, phone, gstin FROM clients "
            "WHERE name LIKE ? OR phone LIKE ? OR gstin LIKE ? "
            "ORDER BY name LIMIT 5",
            (q, q, q)
        ).fetchall()
        products = conn.execute(
            "SELECT id, name, hsn_code, stock_quantity, unit FROM products "
            "WHERE name LIKE ? OR hsn_code LIKE ? "
            "ORDER BY name LIMIT 5",
            (q, q)
        ).fetchall()
        invoices = conn.execute(
            "SELECT i.id, i.invoice_number, c.name AS client_name, "
            "i.grand_total, i.status "
            "FROM invoices i LEFT JOIN clients c ON i.client_id = c.id "
            "WHERE i.invoice_number LIKE ? OR c.name LIKE ? "
            "ORDER BY i.invoice_date DESC LIMIT 5",
            (q, q)
        ).fetchall()
    return {
        "clients":  [dict(r) for r in clients],
        "products": [dict(r) for r in products],
        "invoices": [dict(r) for r in invoices],
    }


# ── Day Book / Cash Book ──────────────────────────────────────────────────────

def get_day_book(from_date: str, to_date: str):
    """Return all journal entry lines grouped logically for the Day Book."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT je.id AS journal_id,
                   je.entry_date,
                   je.narration,
                   je.reference,
                   la.name  AS account_name,
                   la.account_type,
                   jel.debit,
                   jel.credit
            FROM journal_entries je
            JOIN journal_entry_lines jel ON jel.journal_id = je.id
            JOIN ledger_accounts    la   ON la.id = jel.account_id
            WHERE je.entry_date BETWEEN ? AND ?
            ORDER BY je.entry_date, je.id, jel.id
        """, (from_date, to_date)).fetchall()

        totals = conn.execute("""
            SELECT COALESCE(SUM(jel.debit),0)  AS total_dr,
                   COALESCE(SUM(jel.credit),0) AS total_cr
            FROM journal_entries je
            JOIN journal_entry_lines jel ON jel.journal_id = je.id
            WHERE je.entry_date BETWEEN ? AND ?
        """, (from_date, to_date)).fetchone()

    return {
        "rows": [dict(r) for r in rows],
        "total_dr": totals["total_dr"],
        "total_cr": totals["total_cr"],
    }


def get_cash_book(from_date: str, to_date: str, account_code: str = "1002"):
    """Return cash/bank transactions with running balance for Cash Book.

    account_code: '1002' = Cash in Hand, '1003' = Bank Account
    """
    with get_connection() as conn:
        acct = conn.execute(
            "SELECT id, name FROM ledger_accounts WHERE code=?", (account_code,)
        ).fetchone()
        if not acct:
            return {"account": account_code, "rows": [],
                    "opening": 0.0, "total_dr": 0.0, "total_cr": 0.0, "closing": 0.0}

        acct_id = acct["id"]

        # Opening balance = sum of debits minus credits before from_date
        ob_row = conn.execute("""
            SELECT COALESCE(SUM(jel.debit),0) - COALESCE(SUM(jel.credit),0) AS bal
            FROM journal_entry_lines jel
            JOIN journal_entries je ON je.id = jel.journal_id
            WHERE jel.account_id = ? AND je.entry_date < ?
        """, (acct_id, from_date)).fetchone()
        opening = ob_row["bal"] if ob_row else 0.0

        rows = conn.execute("""
            SELECT je.entry_date,
                   je.narration,
                   je.reference,
                   jel.debit,
                   jel.credit
            FROM journal_entries je
            JOIN journal_entry_lines jel ON jel.journal_id = je.id
            WHERE jel.account_id = ? AND je.entry_date BETWEEN ? AND ?
            ORDER BY je.entry_date, je.id
        """, (acct_id, from_date, to_date)).fetchall()

    result_rows = []
    running = opening
    total_dr = 0.0
    total_cr = 0.0
    for r in rows:
        running  += r["debit"] - r["credit"]
        total_dr += r["debit"]
        total_cr += r["credit"]
        result_rows.append({
            "entry_date": r["entry_date"],
            "narration":  r["narration"],
            "reference":  r["reference"],
            "debit":      r["debit"],
            "credit":     r["credit"],
            "balance":    running,
        })

    return {
        "account":   dict(acct),
        "rows":      result_rows,
        "opening":   opening,
        "total_dr":  total_dr,
        "total_cr":  total_cr,
        "closing":   opening + total_dr - total_cr,
    }


# ── Credit / Debit Notes ─────────────────────────────────────────────────────

def _next_cdn_number(note_type: str, prefix: str = "") -> str:
    """Auto-generate next note number: CN-001 or DN-001."""
    with get_connection() as conn:
        prefix = prefix or ("CN" if note_type == "Credit" else "DN")
        rows = conn.execute(
            "SELECT note_number FROM credit_debit_notes WHERE note_type=? ORDER BY id DESC LIMIT 1",
            (note_type,)
        ).fetchall()
        if rows:
            last = rows[0]["note_number"]
            try:
                seq = int(last.rsplit("-", 1)[-1]) + 1
            except ValueError:
                seq = 1
        else:
            seq = 1
        return f"{prefix}-{seq:03d}"


def get_all_cdns(note_type: str = "All", status: str = "All",
                 from_date: str = "", to_date: str = ""):
    with get_connection() as conn:
        q = "SELECT * FROM credit_debit_notes WHERE 1=1"
        params = []
        if note_type != "All":
            q += " AND note_type=?"; params.append(note_type)
        if status != "All":
            q += " AND status=?"; params.append(status)
        if from_date:
            q += " AND note_date>=?"; params.append(from_date)
        if to_date:
            q += " AND note_date<=?"; params.append(to_date)
        q += " ORDER BY note_date DESC, id DESC"
        return conn.execute(q, params).fetchall()


def get_cdn(note_id: int):
    with get_connection() as conn:
        note  = conn.execute("SELECT * FROM credit_debit_notes WHERE id=?", (note_id,)).fetchone()
        items = conn.execute("SELECT * FROM cdn_items WHERE note_id=?", (note_id,)).fetchall()
        return note, items


def get_cdn_note(note_id: int):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM credit_debit_notes WHERE id=?", (note_id,)
        ).fetchone()


def get_cdn_items(note_id: int):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM cdn_items WHERE note_id=?", (note_id,)
        ).fetchall()


def next_cdn_number(note_type: str) -> str:
    return _next_cdn_number(note_type)


def save_cdn(note_type, note_number, note_date, client_id, client_name,
             original_invoice_id, original_invoice_no, reason, supply_type,
             subtotal, cgst_total, sgst_total, igst_total, discount_amt,
             grand_total, status, notes, items: list) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO credit_debit_notes
               (note_type,note_number,note_date,client_id,client_name,
                original_invoice_id,original_invoice_no,reason,supply_type,
                subtotal,cgst_total,sgst_total,igst_total,discount_amt,
                grand_total,status,notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (note_type, note_number, note_date, client_id or None, client_name,
             original_invoice_id or None, original_invoice_no, reason, supply_type,
             subtotal, cgst_total, sgst_total, igst_total, discount_amt,
             grand_total, status, notes),
        )
        note_id = cur.lastrowid
        for it in items:
            conn.execute(
                """INSERT INTO cdn_items
                   (note_id,description,hsn_code,quantity,unit,unit_price,gst_rate,
                    taxable_value,cgst_amt,sgst_amt,igst_amt,total_amt)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (note_id, it["description"], it.get("hsn_code",""),
                 it["quantity"], it.get("unit","NOS"), it["unit_price"],
                 it["gst_rate"], it["taxable_value"],
                 it["cgst_amt"], it["sgst_amt"], it["igst_amt"], it["total_amt"]),
            )
        conn.commit()
        return note_id


def update_cdn(note_id, note_type, note_number, note_date, client_id, client_name,
               original_invoice_id, original_invoice_no, reason, supply_type,
               subtotal, cgst_total, sgst_total, igst_total, discount_amt,
               grand_total, status, notes, items: list):
    with get_connection() as conn:
        conn.execute(
            """UPDATE credit_debit_notes SET note_type=?,note_number=?,note_date=?,
               client_id=?,client_name=?,original_invoice_id=?,original_invoice_no=?,
               reason=?,supply_type=?,subtotal=?,cgst_total=?,sgst_total=?,igst_total=?,
               discount_amt=?,grand_total=?,status=?,notes=? WHERE id=?""",
            (note_type, note_number, note_date, client_id or None, client_name,
             original_invoice_id or None, original_invoice_no, reason, supply_type,
             subtotal, cgst_total, sgst_total, igst_total, discount_amt,
             grand_total, status, notes, note_id),
        )
        conn.execute("DELETE FROM cdn_items WHERE note_id=?", (note_id,))
        for it in items:
            conn.execute(
                """INSERT INTO cdn_items
                   (note_id,description,hsn_code,quantity,unit,unit_price,gst_rate,
                    taxable_value,cgst_amt,sgst_amt,igst_amt,total_amt)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (note_id, it["description"], it.get("hsn_code",""),
                 it["quantity"], it.get("unit","NOS"), it["unit_price"],
                 it["gst_rate"], it["taxable_value"],
                 it["cgst_amt"], it["sgst_amt"], it["igst_amt"], it["total_amt"]),
            )
        conn.commit()


def delete_cdn(note_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM cdn_items WHERE note_id=?", (note_id,))
        conn.execute("DELETE FROM credit_debit_notes WHERE id=?", (note_id,))
        conn.commit()


def get_cdn_summary():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT note_type, SUM(grand_total) as total, COUNT(*) as cnt "
            "FROM credit_debit_notes GROUP BY note_type"
        ).fetchall()
        result = {"credit_total": 0.0, "credit_count": 0,
                  "debit_total": 0.0,  "debit_count": 0}
        for r in rows:
            if r["note_type"] == "Credit":
                result["credit_total"] = r["total"]
                result["credit_count"] = r["cnt"]
            else:
                result["debit_total"] = r["total"]
                result["debit_count"] = r["cnt"]
        return result


# ── TDS ───────────────────────────────────────────────────────────────────────

TDS_SECTIONS = {
    "194Q":  {"desc": "Purchase of Goods",              "rate": 0.1,  "threshold": 5000000},
    "194C":  {"desc": "Contractors / Sub-contractors",  "rate": 1.0,  "threshold": 30000},
    "194H":  {"desc": "Commission / Brokerage",         "rate": 5.0,  "threshold": 15000},
    "194I(a)":{"desc": "Rent – Plant & Machinery",      "rate": 2.0,  "threshold": 240000},
    "194I(b)":{"desc": "Rent – Land / Building",        "rate": 10.0, "threshold": 240000},
    "194J":  {"desc": "Professional / Technical Fees",  "rate": 10.0, "threshold": 30000},
    "194J(b)":{"desc": "Technical Services (reduced)",  "rate": 2.0,  "threshold": 30000},
    "194A":  {"desc": "Interest (other than securities)","rate": 10.0, "threshold": 40000},
    "194M":  {"desc": "Payments to Contractors (Indiv.)","rate": 5.0, "threshold": 5000000},
    "194O":  {"desc": "E-Commerce Payments",            "rate": 1.0,  "threshold": 0},
    "194LA": {"desc": "Compensation – Immovable Property","rate": 10.0,"threshold": 250000},
    "192":   {"desc": "Salary",                         "rate": 0.0,  "threshold": 0},
    "195":   {"desc": "Payments to Non-Residents",      "rate": 20.0, "threshold": 0},
    "206C":  {"desc": "TCS – Sale of Goods (collected)","rate": 0.1,  "threshold": 5000000},
}


def get_all_tds_entries(tds_type: str = "All", section: str = "All",
                        status: str = "All",
                        from_date: str = "", to_date: str = ""):
    with get_connection() as conn:
        q  = "SELECT * FROM tds_entries WHERE 1=1"
        params = []
        if tds_type != "All":
            q += " AND tds_type=?"; params.append(tds_type)
        if section != "All":
            q += " AND section=?"; params.append(section)
        if status != "All":
            q += " AND status=?"; params.append(status)
        if from_date:
            q += " AND entry_date>=?"; params.append(from_date)
        if to_date:
            q += " AND entry_date<=?"; params.append(to_date)
        q += " ORDER BY entry_date DESC"
        return conn.execute(q, params).fetchall()


def get_tds_summary():
    with get_connection() as conn:
        rows = conn.execute("SELECT tds_type, status, SUM(total_tds) as amt, COUNT(*) as cnt "
                            "FROM tds_entries GROUP BY tds_type, status").fetchall()
        result = {"payable_pending": 0.0, "payable_paid": 0.0,
                  "receivable_pending": 0.0, "receivable_credited": 0.0,
                  "total_entries": 0}
        for r in rows:
            result["total_entries"] += r["cnt"]
            if r["tds_type"] == "Payable":
                if r["status"] == "Paid":
                    result["payable_paid"] += r["amt"]
                else:
                    result["payable_pending"] += r["amt"]
            else:
                if r["status"] == "Credited":
                    result["receivable_credited"] += r["amt"]
                else:
                    result["receivable_pending"] += r["amt"]
        return result


def save_tds_entry(entry_date, tds_type, section, deductee_name, deductee_pan,
                   description, taxable_amount, tds_rate, tds_amount,
                   surcharge=0.0, cess=0.0, total_tds=None,
                   payment_date="", challan_no="", challan_date="",
                   bsr_code="", status="Pending",
                   reference_id=None, reference_type="", notes=""):
    if total_tds is None:
        total_tds = round(tds_amount + surcharge + cess, 2)
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO tds_entries
               (entry_date,tds_type,section,deductee_name,deductee_pan,description,
                taxable_amount,tds_rate,tds_amount,surcharge,cess,total_tds,
                payment_date,challan_no,challan_date,bsr_code,status,
                reference_id,reference_type,notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (entry_date, tds_type, section, deductee_name, deductee_pan, description,
             taxable_amount, tds_rate, tds_amount, surcharge, cess, total_tds,
             payment_date or None, challan_no, challan_date or None, bsr_code, status,
             reference_id, reference_type, notes),
        )
        conn.commit()


def update_tds_entry(entry_id, entry_date, tds_type, section, deductee_name,
                     deductee_pan, description, taxable_amount, tds_rate,
                     tds_amount, surcharge=0.0, cess=0.0, total_tds=None,
                     payment_date="", challan_no="", challan_date="",
                     bsr_code="", status="Pending", notes=""):
    if total_tds is None:
        total_tds = round(tds_amount + surcharge + cess, 2)
    with get_connection() as conn:
        conn.execute(
            """UPDATE tds_entries SET entry_date=?,tds_type=?,section=?,deductee_name=?,
               deductee_pan=?,description=?,taxable_amount=?,tds_rate=?,tds_amount=?,
               surcharge=?,cess=?,total_tds=?,payment_date=?,challan_no=?,
               challan_date=?,bsr_code=?,status=?,notes=? WHERE id=?""",
            (entry_date, tds_type, section, deductee_name, deductee_pan, description,
             taxable_amount, tds_rate, tds_amount, surcharge, cess, total_tds,
             payment_date or None, challan_no, challan_date or None, bsr_code, status,
             notes, entry_id),
        )
        conn.commit()


def mark_tds_paid(entry_id, payment_date, challan_no, challan_date, bsr_code=""):
    with get_connection() as conn:
        conn.execute(
            """UPDATE tds_entries SET status='Paid', payment_date=?,
               challan_no=?, challan_date=?, bsr_code=? WHERE id=?""",
            (payment_date, challan_no, challan_date or None, bsr_code, entry_id),
        )
        conn.commit()


def delete_tds_entry(entry_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM tds_entries WHERE id=?", (entry_id,))
        conn.commit()


# ── Fixed Assets ──────────────────────────────────────────────────────────────

ASSET_CATEGORIES = [
    "Land & Building", "Plant & Machinery", "Furniture & Fixtures",
    "Vehicles", "Computer & IT Equipment", "Office Equipment",
    "Electrical Installations", "Other",
]


def get_all_assets(status=None, category=None):
    with get_connection() as conn:
        q = "SELECT * FROM fixed_assets WHERE 1=1"
        params = []
        if status:
            q += " AND status=?"; params.append(status)
        if category:
            q += " AND category=?"; params.append(category)
        q += " ORDER BY asset_code"
        return conn.execute(q, params).fetchall()


def get_asset(asset_id: int):
    with get_connection() as conn:
        return conn.execute("SELECT * FROM fixed_assets WHERE id=?", (asset_id,)).fetchone()


def add_asset(asset_code, name, category, description, purchase_date, purchase_cost,
              salvage_value, useful_life_years, depreciation_method, depreciation_rate,
              location, vendor, invoice_no, notes) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO fixed_assets
               (asset_code,name,category,description,purchase_date,purchase_cost,
                salvage_value,useful_life_years,depreciation_method,depreciation_rate,
                location,vendor,invoice_no,notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (asset_code.strip(), name.strip(), category, description.strip(),
             purchase_date, float(purchase_cost), float(salvage_value),
             float(useful_life_years), depreciation_method, float(depreciation_rate),
             location.strip(), vendor.strip(), invoice_no.strip(), notes.strip()),
        )
        conn.commit()
        return cur.lastrowid


def update_asset(asset_id, asset_code, name, category, description, purchase_date,
                 purchase_cost, salvage_value, useful_life_years, depreciation_method,
                 depreciation_rate, location, vendor, invoice_no, notes):
    with get_connection() as conn:
        conn.execute(
            """UPDATE fixed_assets SET asset_code=?,name=?,category=?,description=?,
               purchase_date=?,purchase_cost=?,salvage_value=?,useful_life_years=?,
               depreciation_method=?,depreciation_rate=?,location=?,vendor=?,
               invoice_no=?,notes=? WHERE id=?""",
            (asset_code.strip(), name.strip(), category, description.strip(),
             purchase_date, float(purchase_cost), float(salvage_value),
             float(useful_life_years), depreciation_method, float(depreciation_rate),
             location.strip(), vendor.strip(), invoice_no.strip(), notes.strip(), asset_id),
        )
        conn.commit()


def delete_asset(asset_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM fixed_assets WHERE id=?", (asset_id,))
        conn.commit()


def dispose_asset(asset_id: int, disposal_date: str, disposal_value: float, notes: str = ""):
    with get_connection() as conn:
        conn.execute(
            """UPDATE fixed_assets SET status='Disposed', disposal_date=?,
               disposal_value=?, notes=CASE WHEN notes='' THEN ? ELSE notes||' | '||? END
               WHERE id=?""",
            (disposal_date, float(disposal_value), notes, notes, asset_id),
        )
        conn.commit()


def record_depreciation(asset_id: int, financial_year: str, opening_nbv: float,
                        depreciation_amount: float, accumulated_depreciation: float,
                        closing_nbv: float, entry_date: str, notes: str = ""):
    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO asset_depreciation
               (asset_id,financial_year,opening_nbv,depreciation_amount,
                accumulated_depreciation,closing_nbv,entry_date,notes)
               VALUES (?,?,?,?,?,?,?,?)""",
            (asset_id, financial_year, float(opening_nbv), float(depreciation_amount),
             float(accumulated_depreciation), float(closing_nbv), entry_date, notes.strip()),
        )
        conn.commit()


def get_asset_depreciation(asset_id: int):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM asset_depreciation WHERE asset_id=? ORDER BY financial_year",
            (asset_id,)
        ).fetchall()


def get_asset_summary():
    with get_connection() as conn:
        row = conn.execute("""
            SELECT
                COUNT(*) AS total_assets,
                COALESCE(SUM(CASE WHEN status='Active' THEN 1 ELSE 0 END), 0) AS active_count,
                COALESCE(SUM(CASE WHEN status='Active' THEN purchase_cost ELSE 0 END), 0) AS total_cost,
                COALESCE(SUM(CASE WHEN status='Disposed' THEN 1 ELSE 0 END), 0) AS disposed_count
            FROM fixed_assets
        """).fetchone()
        return dict(row) if row else {}


def get_assets_with_nbv():
    with get_connection() as conn:
        return conn.execute("""
            SELECT fa.*,
                   COALESCE(ad.closing_nbv, fa.purchase_cost) AS current_nbv,
                   COALESCE(ad.accumulated_depreciation, 0) AS accumulated_depreciation,
                   ad.financial_year AS last_dep_year
            FROM fixed_assets fa
            LEFT JOIN asset_depreciation ad ON ad.asset_id = fa.id
                AND ad.financial_year = (
                    SELECT MAX(financial_year) FROM asset_depreciation WHERE asset_id=fa.id
                )
            ORDER BY fa.asset_code
        """).fetchall()


def next_asset_code() -> str:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT asset_code FROM fixed_assets ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return "FA-0001"
        code = row["asset_code"]
        try:
            num = int(code.split("-")[-1]) + 1
            return f"FA-{num:04d}"
        except Exception:
            return "FA-0001"


def calculate_depreciation_amount(purchase_cost: float, salvage_value: float,
                                   useful_life_years: float, method: str,
                                   rate: float, opening_nbv: float) -> float:
    if method == "SLM":
        annual = (purchase_cost - salvage_value) / max(useful_life_years, 1)
        remaining = max(opening_nbv - salvage_value, 0)
        return round(min(annual, remaining), 2)
    else:
        return round(max(opening_nbv * (rate / 100), 0), 2)


# ── Payroll ───────────────────────────────────────────────────────────────────

def next_emp_code() -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT emp_code FROM employees ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return "EMP-001"
        code = row["emp_code"]
        try:
            num = int(code.split("-")[-1]) + 1
            return f"EMP-{num:03d}"
        except Exception:
            return "EMP-001"


def get_all_employees(status=None):
    with get_connection() as conn:
        q = "SELECT * FROM employees"
        if status:
            q += " WHERE status=?"
            return conn.execute(q, (status,)).fetchall()
        q += " ORDER BY emp_code"
        return conn.execute(q).fetchall()


def get_employee(emp_id: int):
    with get_connection() as conn:
        return conn.execute("SELECT * FROM employees WHERE id=?", (emp_id,)).fetchone()


def add_employee(emp_code, name, designation, department, joining_date, dob, pan, uan,
                 bank_account, bank_name, ifsc, basic, hra, da, special_allowance,
                 other_allowance, pf_applicable, esi_applicable, pt_applicable,
                 tds_monthly, notes) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO employees
               (emp_code,name,designation,department,joining_date,dob,pan,uan,
                bank_account,bank_name,ifsc,basic,hra,da,special_allowance,
                other_allowance,pf_applicable,esi_applicable,pt_applicable,tds_monthly,notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (emp_code.strip(), name.strip(), designation.strip(), department.strip(),
             joining_date, dob, pan.strip().upper(), uan.strip(),
             bank_account.strip(), bank_name.strip(), ifsc.strip().upper(),
             float(basic), float(hra), float(da), float(special_allowance),
             float(other_allowance), int(pf_applicable), int(esi_applicable),
             int(pt_applicable), float(tds_monthly), notes.strip()),
        )
        conn.commit()
        return cur.lastrowid


def update_employee(emp_id, emp_code, name, designation, department, joining_date, dob,
                    pan, uan, bank_account, bank_name, ifsc, basic, hra, da,
                    special_allowance, other_allowance, pf_applicable, esi_applicable,
                    pt_applicable, tds_monthly, status, notes):
    with get_connection() as conn:
        conn.execute(
            """UPDATE employees SET emp_code=?,name=?,designation=?,department=?,
               joining_date=?,dob=?,pan=?,uan=?,bank_account=?,bank_name=?,ifsc=?,
               basic=?,hra=?,da=?,special_allowance=?,other_allowance=?,
               pf_applicable=?,esi_applicable=?,pt_applicable=?,tds_monthly=?,
               status=?,notes=? WHERE id=?""",
            (emp_code.strip(), name.strip(), designation.strip(), department.strip(),
             joining_date, dob, pan.strip().upper(), uan.strip(),
             bank_account.strip(), bank_name.strip(), ifsc.strip().upper(),
             float(basic), float(hra), float(da), float(special_allowance),
             float(other_allowance), int(pf_applicable), int(esi_applicable),
             int(pt_applicable), float(tds_monthly), status, notes.strip(), emp_id),
        )
        conn.commit()


def delete_employee(emp_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM employees WHERE id=?", (emp_id,))
        conn.commit()


def get_employee_summary():
    with get_connection() as conn:
        row = conn.execute("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status='Active' THEN 1 ELSE 0 END) AS active,
                   SUM(CASE WHEN status='Active' THEN basic+hra+da+special_allowance+other_allowance ELSE 0 END) AS monthly_ctc
            FROM employees
        """).fetchone()
        return dict(row) if row else {}


def calculate_payroll(emp: dict, working_days: float, present_days: float,
                      advance: float = 0.0, other_ded: float = 0.0) -> dict:
    lop_days = max(working_days - present_days, 0)
    ratio = present_days / working_days if working_days > 0 else 0

    basic_e = round(emp["basic"] * ratio, 2)
    hra_e   = round(emp["hra"] * ratio, 2)
    da_e    = round(emp["da"] * ratio, 2)
    sa_e    = round(emp["special_allowance"] * ratio, 2)
    oa_e    = round(emp["other_allowance"] * ratio, 2)
    gross   = round(basic_e + hra_e + da_e + sa_e + oa_e, 2)

    pf_emp  = round(basic_e * 0.12, 2) if emp.get("pf_applicable") else 0.0
    esi_emp = round(gross * 0.0075, 2) if emp.get("esi_applicable") and gross <= 21000 else 0.0
    pt = _get_pt(gross) if emp.get("pt_applicable") else 0.0
    tds = round(emp.get("tds_monthly", 0) * ratio, 2)

    total_ded = round(pf_emp + esi_emp + pt + tds + advance + other_ded, 2)
    net_pay   = round(gross - total_ded, 2)

    return {
        "lop_days": lop_days, "basic_earned": basic_e, "hra_earned": hra_e,
        "da_earned": da_e, "special_allowance_earned": sa_e,
        "other_allowance_earned": oa_e, "gross_earnings": gross,
        "pf_employee": pf_emp, "esi_employee": esi_emp,
        "pt_deduction": pt, "tds_deduction": tds,
        "advance_deduction": advance, "other_deductions": other_ded,
        "total_deductions": total_ded, "net_pay": net_pay,
    }


def _get_pt(gross: float) -> float:
    if gross <= 7500:
        return 0.0
    elif gross <= 10000:
        return 175.0
    else:
        return 200.0


def save_payroll(employee_id, month, year, working_days, present_days, calc: dict,
                 status="Draft", payment_date="", payment_ref="", notes=""):
    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO payroll_months
               (employee_id,month,year,working_days,present_days,lop_days,
                basic_earned,hra_earned,da_earned,special_allowance_earned,other_allowance_earned,
                gross_earnings,pf_employee,esi_employee,pt_deduction,tds_deduction,
                advance_deduction,other_deductions,total_deductions,net_pay,
                status,payment_date,payment_ref,notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (employee_id, month, year, float(working_days), float(present_days),
             calc["lop_days"], calc["basic_earned"], calc["hra_earned"],
             calc["da_earned"], calc["special_allowance_earned"], calc["other_allowance_earned"],
             calc["gross_earnings"], calc["pf_employee"], calc["esi_employee"],
             calc["pt_deduction"], calc["tds_deduction"], calc["advance_deduction"],
             calc["other_deductions"], calc["total_deductions"], calc["net_pay"],
             status, payment_date, payment_ref, notes),
        )
        conn.commit()


def get_payroll_month(month: int, year: int):
    with get_connection() as conn:
        return conn.execute("""
            SELECT pm.*, e.emp_code, e.name, e.designation, e.department,
                   e.bank_account, e.bank_name, e.ifsc, e.pan
            FROM payroll_months pm
            JOIN employees e ON e.id = pm.employee_id
            WHERE pm.month=? AND pm.year=?
            ORDER BY e.emp_code
        """, (month, year)).fetchall()


def get_employee_payroll_history(emp_id: int):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM payroll_months WHERE employee_id=? ORDER BY year DESC, month DESC",
            (emp_id,)
        ).fetchall()


def mark_payroll_paid(payroll_id: int, payment_date: str, payment_ref: str = ""):
    with get_connection() as conn:
        conn.execute(
            "UPDATE payroll_months SET status='Paid', payment_date=?, payment_ref=? WHERE id=?",
            (payment_date, payment_ref, payroll_id),
        )
        conn.commit()


def delete_payroll(payroll_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM payroll_months WHERE id=?", (payroll_id,))
        conn.commit()


# ── Advance Payments ──────────────────────────────────────────────────────────

def next_advance_no(payment_type: str) -> str:
    prefix = "ADV-R" if payment_type == "Received" else "ADV-P"
    with get_connection() as conn:
        row = conn.execute(
            "SELECT advance_no FROM advance_payments WHERE payment_type=? ORDER BY id DESC LIMIT 1",
            (payment_type,)
        ).fetchone()
        if not row:
            return f"{prefix}-001"
        try:
            num = int(row["advance_no"].rsplit("-", 1)[-1]) + 1
            return f"{prefix}-{num:03d}"
        except Exception:
            return f"{prefix}-001"


def get_all_advances(payment_type=None, status=None):
    with get_connection() as conn:
        q = "SELECT * FROM advance_payments WHERE 1=1"
        params = []
        if payment_type:
            q += " AND payment_type=?"; params.append(payment_type)
        if status:
            q += " AND status=?"; params.append(status)
        q += " ORDER BY advance_date DESC"
        return conn.execute(q, params).fetchall()


def get_advance(adv_id: int):
    with get_connection() as conn:
        return conn.execute("SELECT * FROM advance_payments WHERE id=?", (adv_id,)).fetchone()


def add_advance(payment_type, party_type, party_name, advance_no, advance_date,
                amount, payment_mode, bank_ref, linked_ref, narration, notes) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO advance_payments
               (payment_type,party_type,party_name,advance_no,advance_date,
                amount,payment_mode,bank_ref,linked_ref,narration,notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (payment_type, party_type, party_name.strip(), advance_no.strip(),
             advance_date, float(amount), payment_mode, bank_ref.strip(),
             linked_ref.strip(), narration.strip(), notes.strip()),
        )
        conn.commit()
        return cur.lastrowid


def update_advance(adv_id, payment_type, party_type, party_name, advance_no, advance_date,
                   amount, payment_mode, bank_ref, linked_ref, narration, notes):
    with get_connection() as conn:
        conn.execute(
            """UPDATE advance_payments SET payment_type=?,party_type=?,party_name=?,
               advance_no=?,advance_date=?,amount=?,payment_mode=?,bank_ref=?,
               linked_ref=?,narration=?,notes=? WHERE id=?""",
            (payment_type, party_type, party_name.strip(), advance_no.strip(),
             advance_date, float(amount), payment_mode, bank_ref.strip(),
             linked_ref.strip(), narration.strip(), notes.strip(), adv_id),
        )
        conn.commit()


def adjust_advance(adv_id: int, adjust_amount: float):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT amount, adjusted_amount FROM advance_payments WHERE id=?", (adv_id,)
        ).fetchone()
        if not row:
            return
        new_adj = round(row["adjusted_amount"] + adjust_amount, 2)
        balance  = round(row["amount"] - new_adj, 2)
        status   = "Fully Adjusted" if balance <= 0 else "Partially Adjusted"
        conn.execute(
            "UPDATE advance_payments SET adjusted_amount=?, status=? WHERE id=?",
            (new_adj, status, adv_id),
        )
        conn.commit()


def delete_advance(adv_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM advance_payments WHERE id=?", (adv_id,))
        conn.commit()


def get_advance_summary():
    with get_connection() as conn:
        row = conn.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN payment_type='Received' THEN amount ELSE 0 END),0) AS total_received,
                COALESCE(SUM(CASE WHEN payment_type='Received' AND status='Open'
                              THEN amount-adjusted_amount ELSE 0 END),0) AS open_received,
                COALESCE(SUM(CASE WHEN payment_type='Paid' THEN amount ELSE 0 END),0) AS total_paid,
                COALESCE(SUM(CASE WHEN payment_type='Paid' AND status='Open'
                              THEN amount-adjusted_amount ELSE 0 END),0) AS open_paid
            FROM advance_payments
        """).fetchone()
        return dict(row) if row else {}


# ── Cheques / PDC ─────────────────────────────────────────────────────────────

def get_all_cheques(cheque_type=None, status=None):
    with get_connection() as conn:
        q = "SELECT * FROM cheques WHERE 1=1"
        params = []
        if cheque_type:
            q += " AND cheque_type=?"; params.append(cheque_type)
        if status:
            q += " AND status=?"; params.append(status)
        q += " ORDER BY cheque_date DESC"
        return conn.execute(q, params).fetchall()


def get_cheque(cheque_id: int):
    with get_connection() as conn:
        return conn.execute("SELECT * FROM cheques WHERE id=?", (cheque_id,)).fetchone()


def add_cheque(cheque_type, cheque_no, bank_name, branch, amount, cheque_date,
               party_name, party_type, received_date, linked_ref, narration, notes) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO cheques
               (cheque_type,cheque_no,bank_name,branch,amount,cheque_date,
                party_name,party_type,received_date,linked_ref,narration,notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (cheque_type, cheque_no.strip(), bank_name.strip(), branch.strip(),
             float(amount), cheque_date, party_name.strip(), party_type,
             received_date, linked_ref.strip(), narration.strip(), notes.strip()),
        )
        conn.commit()
        return cur.lastrowid


def update_cheque(cheque_id, cheque_type, cheque_no, bank_name, branch, amount,
                  cheque_date, party_name, party_type, received_date, linked_ref,
                  narration, notes):
    with get_connection() as conn:
        conn.execute(
            """UPDATE cheques SET cheque_type=?,cheque_no=?,bank_name=?,branch=?,
               amount=?,cheque_date=?,party_name=?,party_type=?,received_date=?,
               linked_ref=?,narration=?,notes=? WHERE id=?""",
            (cheque_type, cheque_no.strip(), bank_name.strip(), branch.strip(),
             float(amount), cheque_date, party_name.strip(), party_type,
             received_date, linked_ref.strip(), narration.strip(), notes.strip(), cheque_id),
        )
        conn.commit()


def present_cheque(cheque_id: int, presented_date: str):
    with get_connection() as conn:
        conn.execute(
            "UPDATE cheques SET status='Presented', presented_date=? WHERE id=?",
            (presented_date, cheque_id),
        )
        conn.commit()


def clear_cheque(cheque_id: int, cleared_date: str):
    with get_connection() as conn:
        conn.execute(
            "UPDATE cheques SET status='Cleared', cleared_date=? WHERE id=?",
            (cleared_date, cheque_id),
        )
        conn.commit()


def bounce_cheque(cheque_id: int, bounce_date: str, bounce_reason: str):
    with get_connection() as conn:
        conn.execute(
            "UPDATE cheques SET status='Bounced', bounce_date=?, bounce_reason=? WHERE id=?",
            (bounce_date, bounce_reason.strip(), cheque_id),
        )
        conn.commit()


def cancel_cheque(cheque_id: int, notes: str = ""):
    with get_connection() as conn:
        conn.execute(
            "UPDATE cheques SET status='Cancelled', notes=CASE WHEN notes='' THEN ? ELSE notes||' | '||? END WHERE id=?",
            (notes, notes, cheque_id),
        )
        conn.commit()


def delete_cheque(cheque_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM cheques WHERE id=?", (cheque_id,))
        conn.commit()


def get_cheque_summary():
    with get_connection() as conn:
        row = conn.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN cheque_type='Inward' AND status='Pending'  THEN amount ELSE 0 END),0) AS inward_pending,
                COALESCE(SUM(CASE WHEN cheque_type='Inward' AND status='Presented' THEN amount ELSE 0 END),0) AS inward_presented,
                COALESCE(SUM(CASE WHEN cheque_type='Inward' AND status='Cleared'   THEN amount ELSE 0 END),0) AS inward_cleared,
                COALESCE(SUM(CASE WHEN cheque_type='Outward' AND status='Pending'  THEN amount ELSE 0 END),0) AS outward_pending,
                COALESCE(SUM(CASE WHEN cheque_type='Outward' AND status='Presented' THEN amount ELSE 0 END),0) AS outward_presented,
                COUNT(CASE WHEN status='Bounced' THEN 1 END) AS bounced_count
            FROM cheques
        """).fetchone()
        return dict(row) if row else {}


def get_upcoming_cheques(days: int = 30):
    from datetime import date, timedelta
    today = date.today().isoformat()
    future = (date.today() + timedelta(days=days)).isoformat()
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM cheques WHERE cheque_date BETWEEN ? AND ? AND status='Pending' ORDER BY cheque_date",
            (today, future),
        ).fetchall()
