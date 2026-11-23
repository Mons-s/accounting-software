-- =============================================================================
-- Phase 1: Accounting App — PostgreSQL schema
-- Applied to: hcm-saas Supabase project (fxrkulyjyutzsuwdwwsf)
-- Schema: "accounting" (isolated from license-server tables in "public")
-- shop_id: nullable now; will be used for multi-tenancy in a later phase
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS accounting;

-- ---------------------------------------------------------------------------
-- Shop registry — one row per licensed installation
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounting.shops (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT        NOT NULL DEFAULT '',
    license_key TEXT        UNIQUE,
    plan        TEXT        DEFAULT 'monthly',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Clients / customers
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounting.clients (
    id           BIGSERIAL   PRIMARY KEY,
    shop_id      UUID        REFERENCES accounting.shops(id),
    name         TEXT        NOT NULL,
    email        TEXT,
    phone        TEXT,
    address      TEXT,
    gstin        TEXT        DEFAULT '',
    state        TEXT        DEFAULT '',
    credit_limit NUMERIC(14,2) DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_clients_shop ON accounting.clients(shop_id);

-- ---------------------------------------------------------------------------
-- Products / inventory
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounting.products (
    id                 BIGSERIAL   PRIMARY KEY,
    shop_id            UUID        REFERENCES accounting.shops(id),
    name               TEXT        NOT NULL,
    sku                TEXT        NOT NULL,
    description        TEXT,
    unit_price         NUMERIC(14,4) NOT NULL DEFAULT 0,
    cost_price         NUMERIC(14,4) DEFAULT 0,
    stock_quantity     INTEGER     NOT NULL DEFAULT 0,
    low_stock_threshold INTEGER    NOT NULL DEFAULT 10,
    unit               TEXT        DEFAULT 'pcs',
    hsn_code           TEXT        DEFAULT '',
    gst_rate           NUMERIC(6,2) DEFAULT 18.0,
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(shop_id, sku)
);
CREATE INDEX IF NOT EXISTS idx_products_shop ON accounting.products(shop_id);

-- ---------------------------------------------------------------------------
-- Orders (sales orders, pre-invoice)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounting.orders (
    id         BIGSERIAL   PRIMARY KEY,
    shop_id    UUID        REFERENCES accounting.shops(id),
    order_code TEXT        NOT NULL,
    client_id  BIGINT      NOT NULL REFERENCES accounting.clients(id),
    status     TEXT        DEFAULT 'Pending',
    notes      TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(shop_id, order_code)
);

CREATE TABLE IF NOT EXISTS accounting.order_items (
    id         BIGSERIAL   PRIMARY KEY,
    shop_id    UUID        REFERENCES accounting.shops(id),
    order_id   BIGINT      NOT NULL REFERENCES accounting.orders(id),
    product_id BIGINT      NOT NULL REFERENCES accounting.products(id),
    quantity   INTEGER     NOT NULL DEFAULT 1,
    unit_price NUMERIC(14,4) NOT NULL
);

-- ---------------------------------------------------------------------------
-- Stock alerts
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounting.stock_alerts (
    id         BIGSERIAL   PRIMARY KEY,
    shop_id    UUID        REFERENCES accounting.shops(id),
    product_id BIGINT      NOT NULL REFERENCES accounting.products(id),
    alert_type TEXT        NOT NULL,
    message    TEXT        NOT NULL,
    is_read    SMALLINT    DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_stock_alerts_shop ON accounting.stock_alerts(shop_id, is_read);

-- ---------------------------------------------------------------------------
-- Firm / shop settings (singleton per shop)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounting.firm_settings (
    id                BIGINT      PRIMARY KEY DEFAULT 1,
    shop_id           UUID        REFERENCES accounting.shops(id),
    firm_name         TEXT        DEFAULT '',
    address           TEXT        DEFAULT '',
    city              TEXT        DEFAULT '',
    state             TEXT        DEFAULT '',
    pincode           TEXT        DEFAULT '',
    gstin             TEXT        DEFAULT '',
    phone             TEXT        DEFAULT '',
    email             TEXT        DEFAULT '',
    bank_name         TEXT        DEFAULT '',
    bank_account      TEXT        DEFAULT '',
    bank_ifsc         TEXT        DEFAULT '',
    bank_branch       TEXT        DEFAULT '',
    terms             TEXT        DEFAULT 'Payment due within 30 days of invoice date.',
    signature_name    TEXT        DEFAULT '',
    invoice_prefix    TEXT        DEFAULT 'INV',
    default_due_days  INTEGER     DEFAULT 30,
    default_gst_rate  NUMERIC(6,2) DEFAULT 18.0,
    fiscal_year_start INTEGER     DEFAULT 4,
    upi_id            TEXT        DEFAULT '',
    -- E-Invoice
    irp_client_id     TEXT        DEFAULT '',
    irp_client_secret TEXT        DEFAULT '',
    irp_username      TEXT        DEFAULT '',
    irp_password      TEXT        DEFAULT '',
    einvoice_sandbox  SMALLINT    DEFAULT 1,
    -- E-Way Bill
    ewb_username      TEXT        DEFAULT '',
    ewb_password      TEXT        DEFAULT '',
    ewb_sandbox       SMALLINT    DEFAULT 1,
    -- SMTP
    smtp_host         TEXT        DEFAULT 'smtp.gmail.com',
    smtp_port         INTEGER     DEFAULT 587,
    smtp_user         TEXT        DEFAULT '',
    smtp_password     TEXT        DEFAULT '',
    smtp_tls          SMALLINT    DEFAULT 1,
    smtp_from_name    TEXT        DEFAULT ''
);

-- ---------------------------------------------------------------------------
-- Invoices (sales)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounting.invoices (
    id               BIGSERIAL   PRIMARY KEY,
    shop_id          UUID        REFERENCES accounting.shops(id),
    invoice_number   TEXT        NOT NULL,
    client_id        BIGINT      NOT NULL REFERENCES accounting.clients(id),
    invoice_date     DATE        NOT NULL,
    due_date         DATE,
    supply_type      TEXT        DEFAULT 'intra',
    subtotal         NUMERIC(14,2) NOT NULL DEFAULT 0,
    cgst_total       NUMERIC(14,2) NOT NULL DEFAULT 0,
    sgst_total       NUMERIC(14,2) NOT NULL DEFAULT 0,
    igst_total       NUMERIC(14,2) NOT NULL DEFAULT 0,
    discount_pct     NUMERIC(6,2) DEFAULT 0,
    discount_amt     NUMERIC(14,2) DEFAULT 0,
    grand_total      NUMERIC(14,2) NOT NULL DEFAULT 0,
    status           TEXT        DEFAULT 'Draft',
    notes            TEXT        DEFAULT '',
    -- E-Invoice
    irn              TEXT,
    ack_number       TEXT,
    ack_date         TEXT,
    einvoice_status  TEXT        DEFAULT 'Not Generated',
    signed_qr        TEXT,
    -- E-Way Bill
    ewb_number       TEXT,
    ewb_date         TEXT,
    ewb_valid_until  TEXT,
    ewb_status       TEXT        DEFAULT 'Not Generated',
    ewb_vehicle_no   TEXT,
    ewb_transporter_id TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(shop_id, invoice_number)
);
CREATE INDEX IF NOT EXISTS idx_invoices_shop ON accounting.invoices(shop_id, status);
CREATE INDEX IF NOT EXISTS idx_invoices_client ON accounting.invoices(client_id);

CREATE TABLE IF NOT EXISTS accounting.invoice_items (
    id            BIGSERIAL   PRIMARY KEY,
    shop_id       UUID        REFERENCES accounting.shops(id),
    invoice_id    BIGINT      NOT NULL REFERENCES accounting.invoices(id),
    product_id    BIGINT      REFERENCES accounting.products(id),
    description   TEXT        NOT NULL,
    hsn_code      TEXT        DEFAULT '',
    quantity      NUMERIC(10,3) NOT NULL DEFAULT 1,
    unit          TEXT        DEFAULT 'pcs',
    unit_price    NUMERIC(14,4) NOT NULL DEFAULT 0,
    gst_rate      NUMERIC(6,2) NOT NULL DEFAULT 18,
    taxable_value NUMERIC(14,2) NOT NULL DEFAULT 0,
    cgst_rate     NUMERIC(6,2) DEFAULT 0,
    cgst_amt      NUMERIC(14,2) DEFAULT 0,
    sgst_rate     NUMERIC(6,2) DEFAULT 0,
    sgst_amt      NUMERIC(14,2) DEFAULT 0,
    igst_rate     NUMERIC(6,2) DEFAULT 0,
    igst_amt      NUMERIC(14,2) DEFAULT 0,
    total_amt     NUMERIC(14,2) NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- Ledger / accounting
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounting.ledger_accounts (
    id           BIGSERIAL   PRIMARY KEY,
    shop_id      UUID        REFERENCES accounting.shops(id),
    code         TEXT        NOT NULL,
    name         TEXT        NOT NULL,
    account_type TEXT        NOT NULL,
    is_system    SMALLINT    DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(shop_id, code)
);

CREATE TABLE IF NOT EXISTS accounting.journal_entries (
    id         BIGSERIAL   PRIMARY KEY,
    shop_id    UUID        REFERENCES accounting.shops(id),
    entry_date DATE        NOT NULL,
    narration  TEXT        NOT NULL,
    reference  TEXT        DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS accounting.journal_entry_lines (
    id         BIGSERIAL   PRIMARY KEY,
    shop_id    UUID        REFERENCES accounting.shops(id),
    journal_id BIGINT      NOT NULL REFERENCES accounting.journal_entries(id),
    account_id BIGINT      NOT NULL REFERENCES accounting.ledger_accounts(id),
    debit      NUMERIC(14,2) NOT NULL DEFAULT 0,
    credit     NUMERIC(14,2) NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- Bank reconciliation
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounting.bank_statement_lines (
    id            BIGSERIAL   PRIMARY KEY,
    shop_id       UUID        REFERENCES accounting.shops(id),
    account_id    BIGINT      NOT NULL REFERENCES accounting.ledger_accounts(id),
    txn_date      DATE        NOT NULL,
    description   TEXT        NOT NULL DEFAULT '',
    debit         NUMERIC(14,2) NOT NULL DEFAULT 0,
    credit        NUMERIC(14,2) NOT NULL DEFAULT 0,
    is_matched    SMALLINT    NOT NULL DEFAULT 0,
    matched_je_id BIGINT      DEFAULT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Recurring invoices
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounting.recurring_invoices (
    id             BIGSERIAL   PRIMARY KEY,
    shop_id        UUID        REFERENCES accounting.shops(id),
    client_id      BIGINT      NOT NULL REFERENCES accounting.clients(id),
    frequency      TEXT        NOT NULL DEFAULT 'monthly',
    next_due       DATE        NOT NULL,
    last_generated DATE,
    notes          TEXT        DEFAULT '',
    is_active      SMALLINT    NOT NULL DEFAULT 1,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS accounting.recurring_invoice_items (
    id           BIGSERIAL   PRIMARY KEY,
    shop_id      UUID        REFERENCES accounting.shops(id),
    recurring_id BIGINT      NOT NULL REFERENCES accounting.recurring_invoices(id),
    description  TEXT        NOT NULL DEFAULT '',
    hsn_code     TEXT        DEFAULT '',
    quantity     NUMERIC(10,3) NOT NULL DEFAULT 1,
    unit_price   NUMERIC(14,4) NOT NULL DEFAULT 0,
    gst_rate     NUMERIC(6,2) NOT NULL DEFAULT 18.0
);

-- ---------------------------------------------------------------------------
-- Users / staff
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounting.users (
    id            BIGSERIAL   PRIMARY KEY,
    shop_id       UUID        REFERENCES accounting.shops(id),
    username      TEXT        NOT NULL,
    full_name     TEXT        NOT NULL DEFAULT '',
    password_hash TEXT        NOT NULL,
    role          TEXT        NOT NULL DEFAULT 'staff',
    is_active     SMALLINT    NOT NULL DEFAULT 1,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(shop_id, username)
);

-- ---------------------------------------------------------------------------
-- Credit / Debit notes
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounting.credit_debit_notes (
    id                  BIGSERIAL   PRIMARY KEY,
    shop_id             UUID        REFERENCES accounting.shops(id),
    note_type           TEXT        NOT NULL DEFAULT 'Credit',
    note_number         TEXT        NOT NULL DEFAULT '',
    note_date           DATE        NOT NULL,
    original_invoice_id BIGINT,
    original_invoice_no TEXT        DEFAULT '',
    client_id           BIGINT,
    client_name         TEXT        DEFAULT '',
    reason              TEXT        DEFAULT '',
    supply_type         TEXT        DEFAULT 'intra',
    subtotal            NUMERIC(14,2) DEFAULT 0,
    cgst_total          NUMERIC(14,2) DEFAULT 0,
    sgst_total          NUMERIC(14,2) DEFAULT 0,
    igst_total          NUMERIC(14,2) DEFAULT 0,
    discount_amt        NUMERIC(14,2) DEFAULT 0,
    grand_total         NUMERIC(14,2) DEFAULT 0,
    status              TEXT        DEFAULT 'Draft',
    notes               TEXT        DEFAULT '',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS accounting.cdn_items (
    id            BIGSERIAL   PRIMARY KEY,
    shop_id       UUID        REFERENCES accounting.shops(id),
    note_id       BIGINT      NOT NULL REFERENCES accounting.credit_debit_notes(id),
    description   TEXT        DEFAULT '',
    hsn_code      TEXT        DEFAULT '',
    quantity      NUMERIC(10,3) DEFAULT 1,
    unit          TEXT        DEFAULT 'NOS',
    unit_price    NUMERIC(14,4) DEFAULT 0,
    gst_rate      NUMERIC(6,2) DEFAULT 18,
    taxable_value NUMERIC(14,2) DEFAULT 0,
    cgst_amt      NUMERIC(14,2) DEFAULT 0,
    sgst_amt      NUMERIC(14,2) DEFAULT 0,
    igst_amt      NUMERIC(14,2) DEFAULT 0,
    total_amt     NUMERIC(14,2) DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- Godowns / warehouses
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounting.godowns (
    id         BIGSERIAL   PRIMARY KEY,
    shop_id    UUID        REFERENCES accounting.shops(id),
    name       TEXT        NOT NULL,
    location   TEXT        DEFAULT '',
    address    TEXT        DEFAULT '',
    is_active  SMALLINT    DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(shop_id, name)
);

CREATE TABLE IF NOT EXISTS accounting.godown_stock (
    id         BIGSERIAL   PRIMARY KEY,
    shop_id    UUID        REFERENCES accounting.shops(id),
    product_id BIGINT      NOT NULL REFERENCES accounting.products(id),
    godown_id  BIGINT      NOT NULL REFERENCES accounting.godowns(id),
    quantity   NUMERIC(10,3) NOT NULL DEFAULT 0,
    UNIQUE(product_id, godown_id)
);

CREATE TABLE IF NOT EXISTS accounting.stock_transfers (
    id             BIGSERIAL   PRIMARY KEY,
    shop_id        UUID        REFERENCES accounting.shops(id),
    product_id     BIGINT      NOT NULL REFERENCES accounting.products(id),
    from_godown_id BIGINT      NOT NULL REFERENCES accounting.godowns(id),
    to_godown_id   BIGINT      NOT NULL REFERENCES accounting.godowns(id),
    quantity       NUMERIC(10,3) NOT NULL DEFAULT 0,
    transfer_date  DATE        NOT NULL,
    notes          TEXT        DEFAULT '',
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- TDS entries
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounting.tds_entries (
    id              BIGSERIAL   PRIMARY KEY,
    shop_id         UUID        REFERENCES accounting.shops(id),
    entry_date      DATE        NOT NULL,
    tds_type        TEXT        NOT NULL DEFAULT 'Payable',
    section         TEXT        NOT NULL DEFAULT '194Q',
    deductee_name   TEXT        NOT NULL DEFAULT '',
    deductee_pan    TEXT        DEFAULT '',
    description     TEXT        DEFAULT '',
    taxable_amount  NUMERIC(14,2) NOT NULL DEFAULT 0,
    tds_rate        NUMERIC(6,2) NOT NULL DEFAULT 0,
    tds_amount      NUMERIC(14,2) NOT NULL DEFAULT 0,
    surcharge       NUMERIC(14,2) DEFAULT 0,
    cess            NUMERIC(14,2) DEFAULT 0,
    total_tds       NUMERIC(14,2) NOT NULL DEFAULT 0,
    payment_date    DATE,
    challan_no      TEXT        DEFAULT '',
    challan_date    DATE,
    bsr_code        TEXT        DEFAULT '',
    status          TEXT        NOT NULL DEFAULT 'Pending',
    reference_id    BIGINT,
    reference_type  TEXT        DEFAULT '',
    notes           TEXT        DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Payment reminders
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounting.payment_reminders (
    id            BIGSERIAL   PRIMARY KEY,
    shop_id       UUID        REFERENCES accounting.shops(id),
    invoice_id    BIGINT      NOT NULL REFERENCES accounting.invoices(id),
    reminder_date DATE        NOT NULL,
    method        TEXT        NOT NULL DEFAULT 'WhatsApp',
    notes         TEXT        DEFAULT '',
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Vendors / suppliers
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounting.vendors (
    id         BIGSERIAL   PRIMARY KEY,
    shop_id    UUID        REFERENCES accounting.shops(id),
    name       TEXT        NOT NULL,
    gstin      TEXT        DEFAULT '',
    phone      TEXT        DEFAULT '',
    email      TEXT        DEFAULT '',
    address    TEXT        DEFAULT '',
    state      TEXT        DEFAULT '',
    created_at DATE        DEFAULT CURRENT_DATE
);
CREATE INDEX IF NOT EXISTS idx_vendors_shop ON accounting.vendors(shop_id);

-- ---------------------------------------------------------------------------
-- Purchase bills
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounting.purchases (
    id          BIGSERIAL   PRIMARY KEY,
    shop_id     UUID        REFERENCES accounting.shops(id),
    vendor_id   BIGINT      REFERENCES accounting.vendors(id),
    bill_number TEXT        DEFAULT '',
    bill_date   DATE        NOT NULL,
    due_date    DATE,
    subtotal    NUMERIC(14,2) DEFAULT 0,
    cgst_total  NUMERIC(14,2) DEFAULT 0,
    sgst_total  NUMERIC(14,2) DEFAULT 0,
    igst_total  NUMERIC(14,2) DEFAULT 0,
    grand_total NUMERIC(14,2) NOT NULL DEFAULT 0,
    status      TEXT        DEFAULT 'Unpaid',
    supply_type TEXT        DEFAULT 'intra',
    notes       TEXT        DEFAULT '',
    je_id       BIGINT,
    created_at  DATE        DEFAULT CURRENT_DATE
);
CREATE INDEX IF NOT EXISTS idx_purchases_shop ON accounting.purchases(shop_id);

CREATE TABLE IF NOT EXISTS accounting.purchase_items (
    id            BIGSERIAL   PRIMARY KEY,
    shop_id       UUID        REFERENCES accounting.shops(id),
    purchase_id   BIGINT      NOT NULL REFERENCES accounting.purchases(id),
    product_id    BIGINT      REFERENCES accounting.products(id),
    description   TEXT        DEFAULT '',
    hsn_code      TEXT        DEFAULT '',
    quantity      NUMERIC(10,3) DEFAULT 1,
    unit          TEXT        DEFAULT 'pcs',
    unit_price    NUMERIC(14,4) DEFAULT 0,
    gst_rate      NUMERIC(6,2) DEFAULT 18,
    taxable_value NUMERIC(14,2) DEFAULT 0,
    cgst_amt      NUMERIC(14,2) DEFAULT 0,
    sgst_amt      NUMERIC(14,2) DEFAULT 0,
    igst_amt      NUMERIC(14,2) DEFAULT 0,
    total_amt     NUMERIC(14,2) DEFAULT 0
);
