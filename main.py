"""
Accounting & Stock Management Desktop Application
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import customtkinter as ctk
from datetime import datetime, timedelta
import threading
import time
import os
import subprocess
import sys

import re
import json
import database as db
import report_export as rex

INDIAN_STATES = [
    "Andaman & Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam",
    "Bihar", "Chandigarh", "Chhattisgarh", "Dadra & Nagar Haveli and Daman & Diu",
    "Delhi", "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jammu & Kashmir",
    "Jharkhand", "Karnataka", "Kerala", "Ladakh", "Lakshadweep", "Madhya Pradesh",
    "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha",
    "Puducherry", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana",
    "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
]
GST_RATES = ["0", "5", "12", "18", "28"]

# ── Theme ─────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

COLORS = {
    "bg":           "#0a0f1e",
    "sidebar":      "#0d1424",
    "sidebar_hover":"#132033",
    "accent":       "#0d9488",
    "accent_light": "#2dd4bf",
    "card_bg":      "#0d1424",
    "success":      "#0d9488",
    "warning":      "#d97706",
    "danger":       "#dc2626",
    "info":         "#0891b2",
    "text":         "#e2e8f0",
    "text_dim":     "#94a3b8",
    "text_muted":   "#4a6080",
    "border":       "#1a2235",
}


def _icon_bg(hex_color: str) -> str:
    """Return a dark-tinted background colour for icon badges."""
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        br, bgg, bb = 13, 20, 36          # #0d1424 dark card bg
        nr = int(br + (r - br) * 0.18)
        ng = int(bgg + (g - bgg) * 0.18)
        nb = int(bb + (b - bb) * 0.18)
        return f"#{nr:02x}{ng:02x}{nb:02x}"
    except Exception:
        return "#1a2235"


class App(ctk.CTk):
    def __init__(self, current_user: dict):
        super().__init__()
        self.current_user = current_user
        self.title("StockAccounts Pro")
        self.geometry("1280x800")
        self.minsize(1100, 700)

        db.initialize_db()
        db.seed_demo_data()

        self._build_layout()
        self._show_page("dashboard")
        self._start_alert_checker()
        self._auto_generate_recurring()
        self.after(2000, self._auto_backup_silent)
        self.bind_all("<Control-b>", lambda _e: BarcodeScanDialog(self, self))

    # ── Layout ────────────────────────────────────────────────────────────────

    def _auto_backup_silent(self):
        try:
            db.auto_backup()
        except Exception:
            pass

    def _auto_generate_recurring(self):
        try:
            generated = db.generate_due_recurring_invoices()
            if generated:
                self.after(1500, lambda: self._notify_recurring(generated))
        except Exception:
            pass

    def _notify_recurring(self, invoice_numbers):
        msg = f"Auto-generated {len(invoice_numbers)} recurring invoice(s):\n" + \
              ", ".join(invoice_numbers)
        import tkinter.messagebox as mb
        mb.showinfo("Recurring Invoices Generated", msg)
        if self.current_page:
            self.current_page.refresh()

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        self.sidebar = Sidebar(self, self._show_page)
        self.sidebar.grid(row=0, column=0, sticky="nsw")

        # Main content area
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self.content_frame.grid_rowconfigure(0, weight=1)
        self.content_frame.grid_columnconfigure(0, weight=1)

        self.pages = {}
        self.current_page = None

    _STAFF_PAGES = frozenset({"dashboard", "orders", "stock", "clients",
                              "invoices", "payments", "alerts"})

    def _show_page(self, name):
        # Role gate — staff cannot navigate to admin-only pages
        if self.current_user.get("role") != "admin" and name not in self._STAFF_PAGES:
            return

        if self.current_page:
            self.current_page.grid_remove()

        if name not in self.pages:
            page_map = {
                "dashboard": DashboardPage,
                "orders": OrdersPage,
                "stock": StockPage,
                "stock_valuation": StockValuationPage,
                "clients": ClientsPage,
                "invoices": InvoicesPage,
                "payments": PaymentsPage,
                "purchases": PurchasesPage,
                "tds": TDSPage,
                "cdn": CreditDebitNotesPage,
                "godowns": GodownsPage,
                "fixed_assets": FixedAssetsPage,
                "payroll": PayrollPage,
                "advances": AdvancePaymentsPage,
                "cheques": ChequePDCPage,
                "alerts": AlertsPage,
                "expenses": ExpensesPage,
                "ledger": LedgerPage,
                "reports": PLReportPage,
                "sales_summary": SalesSummaryPage,
                "balance_sheet": BalanceSheetPage,
                "trial_balance": TrialBalancePage,
                "cash_flow": CashFlowPage,
                "client_ledger": ClientLedgerPage,
                "aging": DebtorsAgingPage,
                "reminders": PaymentRemindersPage,
                "gst_reports": GSTReportsPage,
                "bank_recon": BankReconciliationPage,
                "day_book":  DayBookPage,
                "shifts":    ShiftsPage,
                "settings": SettingsPage,
            }
            self.pages[name] = page_map[name](self.content_frame, self)

        self.current_page = self.pages[name]
        self.current_page.grid(row=0, column=0, sticky="nsew")
        self.current_page.refresh()
        self.sidebar.set_active(name)

    def refresh_current(self):
        if self.current_page:
            self.current_page.refresh()

    def logout(self):
        self.destroy()
        win = LoginWindow()
        win.mainloop()

    def open_search_result(self, category, row):
        if category == "clients":
            self._show_page("clients")
            self.after(100, lambda: ClientStatementDialog(self, self, row["id"], row["name"]))
        elif category == "invoices":
            self._show_page("invoices")
            self.after(100, lambda: InvoiceViewDialog(self, self, row["id"]))
        elif category == "products":
            self._show_page("stock")

    # ── Background alert checker ──────────────────────────────────────────────

    def _start_alert_checker(self):
        def checker():
            while True:
                time.sleep(60)
                db.check_and_create_alerts()
                alerts = db.get_unread_alerts()
                if alerts:
                    self.after(0, lambda a=alerts: self._notify_alerts(a))

        t = threading.Thread(target=checker, daemon=True)
        t.start()

    def _notify_alerts(self, alerts):
        self.sidebar.update_alert_badge(len(alerts))
        try:
            from plyer import notification
            notification.notify(
                title="⚠ Low Stock Alert",
                message=f"{len(alerts)} product(s) are running low on stock!",
                app_name="StockAccounts Pro",
                timeout=8,
            )
        except Exception:
            pass  # plyer not available or platform issue


# ── Global Search Popup ───────────────────────────────────────────────────────

class GlobalSearchPopup(ctk.CTkToplevel):
    def __init__(self, parent, results, on_select, x, y, width):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(fg_color=COLORS["card_bg"])

        total = sum(len(v) for v in results.values())
        height = min(400, max(60, total * 46 + len([k for k, v in results.items() if v]) * 28 + 12))
        self.geometry(f"{width}x{height}+{x}+{y}")

        if total == 0:
            ctk.CTkLabel(self, text="No results found", text_color="#95a5a6",
                         font=ctk.CTkFont(size=12)).pack(pady=16)
            return

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=4, pady=4)

        icons = {"clients": "👥", "invoices": "🧾", "products": "📦"}
        labels = {"clients": "Clients", "invoices": "Invoices", "products": "Products"}

        for category in ("clients", "invoices", "products"):
            rows = results.get(category, [])
            if not rows:
                continue
            ctk.CTkLabel(scroll, text=f"{icons[category]}  {labels[category]}",
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#95a5a6").pack(anchor="w", padx=8, pady=(8, 2))
            for row in rows:
                self._result_row(scroll, category, row, on_select)

    def _result_row(self, parent, category, row, on_select):
        if category == "clients":
            line1 = row["name"]
            line2 = row.get("phone") or row.get("gstin") or ""
        elif category == "invoices":
            line1 = row["invoice_number"]
            line2 = f"{row.get('client_name') or ''}  ₹{row.get('grand_total', 0):,.0f}  [{row.get('status', '')}]"
        else:
            line1 = row["name"]
            line2 = f"Stock: {row.get('stock_quantity', 0)} {row.get('unit', '')}  HSN: {row.get('hsn_code') or '—'}"

        frame = ctk.CTkFrame(parent, fg_color="#1a2035", corner_radius=6, height=38)
        frame.pack(fill="x", pady=2, padx=2)
        frame.pack_propagate(False)

        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=8, pady=4)

        ctk.CTkLabel(inner, text=line1, font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#ecf0f1", anchor="w").pack(anchor="w")
        if line2:
            ctk.CTkLabel(inner, text=line2, font=ctk.CTkFont(size=10),
                         text_color="#95a5a6", anchor="w").pack(anchor="w")

        def _click(e=None, c=category, r=row):
            self.destroy()
            on_select(c, r)

        for w in (frame, inner) + tuple(inner.winfo_children()):
            w.bind("<Button-1>", _click)
            w.configure(cursor="hand2")

        def _hover_in(e, f=frame):
            f.configure(fg_color="#0f3460")
        def _hover_out(e, f=frame):
            f.configure(fg_color="#1a2035")
        frame.bind("<Enter>", _hover_in)
        frame.bind("<Leave>", _hover_out)


# ── Sidebar ───────────────────────────────────────────────────────────────────

# ── Login Window ─────────────────────────────────────────────────────────────

class LoginWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        db.initialize_db()
        db.seed_demo_data()
        self.title("StockAccounts Pro — Login")
        self.geometry("420x480")
        self.resizable(False, False)
        self._build()

    def _build(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        card = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=16)
        card.grid(row=0, column=0, padx=40, pady=40, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text="📊 StockAccounts Pro",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#e94560",
        ).grid(row=0, column=0, pady=(32, 4))

        ctk.CTkLabel(
            card, text="Sign in to continue",
            font=ctk.CTkFont(size=13),
            text_color="#95a5a6",
        ).grid(row=1, column=0, pady=(0, 24))

        ctk.CTkLabel(card, text="Username", anchor="w",
                     text_color="#ecf0f1").grid(row=2, column=0, sticky="w", padx=32)
        self._user_var = ctk.StringVar()
        self._user_entry = ctk.CTkEntry(
            card, textvariable=self._user_var,
            placeholder_text="Enter username",
            width=300, height=38,
        )
        self._user_entry.grid(row=3, column=0, padx=32, pady=(2, 12))

        ctk.CTkLabel(card, text="Password", anchor="w",
                     text_color="#ecf0f1").grid(row=4, column=0, sticky="w", padx=32)
        self._pass_var = ctk.StringVar()
        self._pass_entry = ctk.CTkEntry(
            card, textvariable=self._pass_var,
            placeholder_text="Enter password",
            show="•", width=300, height=38,
        )
        self._pass_entry.grid(row=5, column=0, padx=32, pady=(2, 8))

        self._err_label = ctk.CTkLabel(
            card, text="", text_color="#e74c3c",
            font=ctk.CTkFont(size=12),
        )
        self._err_label.grid(row=6, column=0, pady=(0, 8))

        ctk.CTkButton(
            card, text="Sign In",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=42, width=300,
            fg_color="#e94560", hover_color="#c0392b",
            command=self._login,
        ).grid(row=7, column=0, padx=32, pady=(0, 24))

        self._pass_entry.bind("<Return>", lambda e: self._login())
        self._user_entry.bind("<Return>", lambda e: self._pass_entry.focus())
        self.after(100, self._user_entry.focus)

        ctk.CTkLabel(
            card, text="Default: admin / admin123",
            font=ctk.CTkFont(size=10),
            text_color="#555",
        ).grid(row=8, column=0, pady=(0, 16))

    def _login(self):
        username = self._user_var.get().strip()
        password = self._pass_var.get()
        if not username or not password:
            self._err_label.configure(text="Please enter username and password.")
            return
        user = db.authenticate_user(username, password)
        if user:
            self.destroy()
            if user.get("role") == "cashier":
                app = CashierApp(user)
            else:
                app = App(user)
            app.mainloop()
        else:
            self._err_label.configure(text="Invalid username or password.")
            self._pass_var.set("")


# ── Change Password Dialog ────────────────────────────────────────────────────

class ChangePasswordDialog(ctk.CTkToplevel):
    def __init__(self, parent, user_id: int, on_done=None):
        super().__init__(parent)
        self.user_id = user_id
        self.on_done = on_done
        self.title("Change Password")
        self.geometry("360x280")
        self.resizable(False, False)
        self.grab_set()
        self._build()

    def _build(self):
        def lbl(text, row):
            ctk.CTkLabel(self, text=text, anchor="w").grid(
                row=row, column=0, sticky="w", padx=24, pady=(8, 0))

        def ent(row, show=None):
            v = ctk.StringVar()
            e = ctk.CTkEntry(self, textvariable=v, width=280, height=36, show=show or "")
            e.grid(row=row + 1, column=0, padx=24, pady=(2, 0))
            return v

        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text="Change Password",
                     font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, pady=(20, 4))

        lbl("Current Password", 1)
        self._cur = ent(1, show="•")
        lbl("New Password", 3)
        self._new = ent(3, show="•")
        lbl("Confirm New Password", 5)
        self._cnf = ent(5, show="•")

        self._err = ctk.CTkLabel(self, text="", text_color="#e74c3c",
                                 font=ctk.CTkFont(size=11))
        self._err.grid(row=7, column=0, pady=(4, 0))

        ctk.CTkButton(self, text="Update Password", height=38,
                      fg_color="#e94560", hover_color="#c0392b",
                      command=self._save).grid(row=8, column=0, padx=24, pady=12, sticky="ew")

    def _save(self):
        cur = self._cur.get()
        new = self._new.get()
        cnf = self._cnf.get()
        if not cur or not new or not cnf:
            self._err.configure(text="All fields are required.")
            return
        if new != cnf:
            self._err.configure(text="New passwords do not match.")
            return
        if len(new) < 6:
            self._err.configure(text="Password must be at least 6 characters.")
            return
        # Verify current password against stored hash
        with db.get_connection() as conn:
            row = conn.execute("SELECT password_hash FROM users WHERE id=?",
                               (self.user_id,)).fetchone()
        if not row or not db._verify_password(cur, row["password_hash"]):
            self._err.configure(text="Current password is incorrect.")
            return
        db.change_password(self.user_id, new)
        if self.on_done:
            self.on_done()
        self.destroy()


# ── Add / Edit User Dialog ────────────────────────────────────────────────────

class AddEditUserDialog(ctk.CTkToplevel):
    def __init__(self, parent, on_done, user=None):
        super().__init__(parent)
        self.on_done = on_done
        self.user = user  # None = add, dict = edit
        self.title("Edit User" if user else "Add User")
        self.geometry("380x420")
        self.resizable(False, False)
        self.grab_set()
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self,
                     text="Edit User" if self.user else "Add New User",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     ).grid(row=0, column=0, pady=(20, 12))

        def row_entry(label, row, show=None):
            ctk.CTkLabel(self, text=label, anchor="w").grid(
                row=row, column=0, sticky="w", padx=24, pady=(6, 0))
            v = ctk.StringVar()
            e = ctk.CTkEntry(self, textvariable=v, width=320, height=36, show=show or "")
            e.grid(row=row + 1, column=0, padx=24, pady=(2, 0))
            return v

        self._username = row_entry("Username", 1)
        self._fullname = row_entry("Full Name", 3)

        ctk.CTkLabel(self, text="Role", anchor="w").grid(
            row=5, column=0, sticky="w", padx=24, pady=(6, 0))
        self._role_var = ctk.StringVar(value="staff")
        ctk.CTkSegmentedButton(
            self, values=["admin", "staff", "cashier"],
            variable=self._role_var,
            font=ctk.CTkFont(size=13),
        ).grid(row=6, column=0, padx=24, pady=(2, 0), sticky="ew")

        if self.user:
            ctk.CTkLabel(self, text="New Password (leave blank to keep)",
                         anchor="w").grid(row=7, column=0, sticky="w", padx=24, pady=(6, 0))
            self._password = ctk.StringVar()
            ctk.CTkEntry(self, textvariable=self._password, width=320, height=36,
                         show="•").grid(row=8, column=0, padx=24, pady=(2, 0))

            self._active_var = ctk.BooleanVar(value=bool(self.user.get("is_active", 1)))
            ctk.CTkCheckBox(self, text="Active", variable=self._active_var,
                            ).grid(row=9, column=0, padx=24, pady=(10, 0), sticky="w")
        else:
            self._password = row_entry("Password", 7, show="•")

        self._err = ctk.CTkLabel(self, text="", text_color="#e74c3c",
                                 font=ctk.CTkFont(size=11))
        self._err.grid(row=10, column=0, pady=(6, 0))

        ctk.CTkButton(
            self,
            text="Save Changes" if self.user else "Create User",
            height=40, fg_color="#e94560", hover_color="#c0392b",
            command=self._save,
        ).grid(row=11, column=0, padx=24, pady=14, sticky="ew")

        if self.user:
            self._username.set(self.user["username"])
            self._fullname.set(self.user.get("full_name", ""))
            self._role_var.set(self.user.get("role", "staff"))

    def _save(self):
        username = self._username.get().strip()
        fullname = self._fullname.get().strip()
        role = self._role_var.get()
        password = self._password.get()

        if not username:
            self._err.configure(text="Username is required.")
            return
        if not self.user and not password:
            self._err.configure(text="Password is required.")
            return
        if not self.user and len(password) < 6:
            self._err.configure(text="Password must be at least 6 characters.")
            return

        if self.user:
            is_active = self._active_var.get()
            db.update_user(self.user["id"], username, fullname, role, is_active)
            if password:
                if len(password) < 6:
                    self._err.configure(text="New password must be at least 6 characters.")
                    return
                db.change_password(self.user["id"], password)
        else:
            ok = db.create_user(username, fullname, password, role)
            if not ok:
                self._err.configure(text="Username already exists.")
                return

        self.on_done()
        self.destroy()


class Sidebar(ctk.CTkFrame):
    NAV_ITEMS = [
        ("dashboard",      "⊞  Dashboard"),
        ("orders",         "≡  Orders"),
        ("stock",          "▦  Stock"),
        ("stock_valuation","◈  Stock Valuation"),
        ("clients",        "◉  Clients"),
        ("invoices",       "◧  Invoices"),
        ("payments",       "◈  Payments Received"),
        ("purchases",      "⊠  Purchases"),
        ("tds",            "◧  TDS Tracker"),
        ("cdn",            "◩  Credit/Debit Notes"),
        ("godowns",        "⊟  Godowns"),
        ("fixed_assets",   "⊞  Fixed Assets"),
        ("payroll",        "◉  Payroll"),
        ("advances",       "◈  Advance Payments"),
        ("cheques",        "▦  Cheque / PDC"),
        ("alerts",         "◎  Alerts"),
        ("expenses",       "◈  Expenses"),
        ("ledger",         "≡  Ledger"),
        ("reports",        "◈  Reports"),
        ("sales_summary",  "◈  Sales Summary"),
        ("balance_sheet",  "▦  Balance Sheet"),
        ("trial_balance",  "⊟  Trial Balance"),
        ("cash_flow",      "◈  Cash Flow"),
        ("client_ledger",  "◧  Client Ledger"),
        ("aging",          "◎  Debtors Aging"),
        ("reminders",      "◉  Payment Reminders"),
        ("gst_reports",    "◧  GST Reports"),
        ("bank_recon",     "▦  Bank Recon"),
        ("day_book",       "≡  Day Book"),
        ("shifts",         "⇌  Shift Management"),
        ("settings",       "⚙  Settings"),
    ]

    NAV_SECTIONS = [
        ("MAIN",    ["dashboard", "orders", "stock", "stock_valuation", "clients"]),
        ("SALES",   ["invoices", "payments", "purchases", "cdn", "tds"]),
        ("FINANCE", ["advances", "cheques", "expenses", "ledger"]),
        ("ASSETS",  ["godowns", "fixed_assets", "payroll"]),
        ("REPORTS", ["reports", "sales_summary", "balance_sheet", "trial_balance",
                     "cash_flow", "client_ledger", "aging", "gst_reports",
                     "bank_recon", "day_book"]),
        ("OTHER",   ["reminders", "alerts", "shifts", "settings"]),
    ]

    def __init__(self, parent, on_navigate):
        super().__init__(parent, width=230, corner_radius=0,
                         fg_color=COLORS["sidebar"])
        self.app = parent
        self.on_navigate = on_navigate
        self.buttons = {}
        self.strips  = {}
        self.grid_propagate(False)
        self._search_popup = None
        self._search_after = None
        self._build()

    def _build(self):
        # ── Bottom: user row + logout ─────────────────────────────────────────
        bottom = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        bottom.pack(side="bottom", fill="x")

        ctk.CTkFrame(bottom, fg_color=COLORS["border"], height=1,
                     corner_radius=0).pack(fill="x")

        ctk.CTkLabel(bottom, text="v2.0.0", text_color=COLORS["text_muted"],
                     font=ctk.CTkFont(size=9)).pack(pady=(2, 4))

        ctk.CTkButton(
            bottom, text="⎋  Sign Out",
            font=ctk.CTkFont(size=11),
            fg_color="transparent", hover_color="#2a1515",
            text_color=COLORS["text_muted"], height=30, corner_radius=6,
            border_width=1, border_color=COLORS["border"],
            command=self.app.logout,
        ).pack(padx=12, pady=(0, 8), fill="x")

        # User row
        user   = self.app.current_user
        name   = user.get("full_name") or user.get("username", "User")
        role_l = "Admin" if user.get("role") == "admin" else "Staff"
        inits  = "".join(w[0].upper() for w in name.split()[:2]) or "U"

        user_row = ctk.CTkFrame(bottom, fg_color="transparent")
        user_row.pack(fill="x", padx=12, pady=(8, 0))

        av = ctk.CTkFrame(user_row, width=32, height=32, corner_radius=16,
                          fg_color=COLORS["accent"])
        av.pack(side="left")
        av.pack_propagate(False)
        ctk.CTkLabel(av, text=inits, font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#fff").pack(expand=True)

        info = ctk.CTkFrame(user_row, fg_color="transparent")
        info.pack(side="left", padx=(8, 0))
        ctk.CTkLabel(info, text=name[:20], font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=COLORS["text"]).pack(anchor="w")
        ctk.CTkLabel(info, text=role_l, font=ctk.CTkFont(size=9),
                     text_color=COLORS["text_muted"]).pack(anchor="w")

        self.alert_badge = ctk.CTkLabel(bottom, text="", font=ctk.CTkFont(size=10),
                                        text_color=COLORS["warning"],
                                        fg_color="transparent")
        self.alert_badge.pack(pady=(4, 0))

        # ── Top: logo ────────────────────────────────────────────────────────
        logo_frame = ctk.CTkFrame(self, fg_color="transparent")
        logo_frame.pack(fill="x", padx=16, pady=(18, 12))

        mark = ctk.CTkFrame(logo_frame, width=38, height=38, corner_radius=10,
                            fg_color=COLORS["accent"])
        mark.pack(side="left")
        mark.pack_propagate(False)
        ctk.CTkLabel(mark, text="SA", font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#fff").pack(expand=True)

        nm = ctk.CTkFrame(logo_frame, fg_color="transparent")
        nm.pack(side="left", padx=(10, 0))
        ctk.CTkLabel(nm, text="StockAccounts Pro",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=COLORS["text"]).pack(anchor="w")
        ctk.CTkLabel(nm, text=f"v2.0  ·  {role_l}",
                     font=ctk.CTkFont(size=9),
                     text_color=COLORS["text_muted"]).pack(anchor="w")

        ctk.CTkFrame(self, fg_color=COLORS["border"], height=1,
                     corner_radius=0).pack(fill="x")

        # ── Search ───────────────────────────────────────────────────────────
        self._search_var = ctk.StringVar()
        self._search_entry = ctk.CTkEntry(
            self, textvariable=self._search_var,
            placeholder_text="  Search…",
            width=200, height=32,
            font=ctk.CTkFont(size=11),
            fg_color=COLORS["bg"], border_color=COLORS["border"],
            text_color=COLORS["text_dim"],
        )
        self._search_entry.pack(padx=12, pady=10)
        self._search_var.trace_add("write", self._on_search_change)
        self._search_entry.bind("<Escape>", self._close_popup)
        self._search_entry.bind("<FocusOut>",
                                lambda e: self.after(200, self._close_popup))

        ctk.CTkFrame(self, fg_color=COLORS["border"], height=1,
                     corner_radius=0).pack(fill="x")

        # ── Scrollable nav ───────────────────────────────────────────────────
        nav_scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent"],
        )
        nav_scroll.pack(fill="both", expand=True)

        role      = self.app.current_user.get("role", "staff")
        staff_pgs = {"dashboard","orders","stock","clients","invoices","payments","alerts"}
        nav_dict  = dict(self.NAV_ITEMS)

        for section_name, keys in self.NAV_SECTIONS:
            visible = [k for k in keys
                       if role == "admin" or k in staff_pgs]
            if not visible:
                continue

            ctk.CTkLabel(nav_scroll, text=section_name,
                         font=ctk.CTkFont(size=9, weight="bold"),
                         text_color=COLORS["text_muted"],
                         anchor="w").pack(fill="x", padx=16, pady=(10, 2))

            for key in visible:
                label = nav_dict.get(key, key)
                row = ctk.CTkFrame(nav_scroll, fg_color="transparent",
                                   corner_radius=0, height=38)
                row.pack(fill="x", pady=1)
                row.pack_propagate(False)

                strip = ctk.CTkFrame(row, width=3,
                                     fg_color="transparent", corner_radius=0)
                strip.pack(side="left", fill="y", pady=3)

                btn = ctk.CTkButton(
                    row, text=label, anchor="w",
                    font=ctk.CTkFont(size=12),
                    fg_color="transparent",
                    hover_color=COLORS["sidebar_hover"],
                    text_color=COLORS["text_muted"], height=36,
                    corner_radius=6,
                    command=lambda k=key: self.on_navigate(k),
                )
                btn.pack(side="left", fill="x", expand=True, padx=(2, 10))

                self.buttons[key] = btn
                self.strips[key]  = strip

    def _on_search_change(self, *_):
        if self._search_after:
            self.after_cancel(self._search_after)
        query = self._search_var.get().strip()
        if len(query) < 2:
            self._close_popup()
            return
        self._search_after = self.after(250, lambda q=query: self._run_search(q))

    def _run_search(self, query):
        self._close_popup()
        try:
            results = db.global_search(query)
        except Exception:
            return
        entry = self._search_entry
        entry.update_idletasks()
        x = entry.winfo_rootx()
        y = entry.winfo_rooty() + entry.winfo_height() + 2
        self._search_popup = GlobalSearchPopup(
            self, results, self._on_result_select, x, y, 260
        )

    def _on_result_select(self, category, row):
        self._search_var.set("")
        self.app.open_search_result(category, row)

    def _close_popup(self, *_):
        if self._search_popup and self._search_popup.winfo_exists():
            self._search_popup.destroy()
        self._search_popup = None

    def set_active(self, key):
        for k, btn in self.buttons.items():
            is_act = k == key
            btn.configure(
                fg_color=COLORS["sidebar_hover"] if is_act else "transparent",
                text_color=COLORS["accent_light"] if is_act else COLORS["text_muted"],
            )
        for k, strip in self.strips.items():
            strip.configure(
                fg_color=COLORS["accent"] if k == key else "transparent"
            )

    def update_alert_badge(self, count):
        if count:
            self.alert_badge.configure(text=f"  ⚠ {count} unread alert(s)")
        else:
            self.alert_badge.configure(text="")


# ── Export helper ─────────────────────────────────────────────────────────────

def _run_export(export_fn, default_name, *args):
    ext = default_name.rsplit(".", 1)[-1].lower()
    filetypes = {
        "pdf":  [("PDF files", "*.pdf")],
        "xlsx": [("Excel files", "*.xlsx")],
        "csv":  [("CSV files", "*.csv")],
    }.get(ext, [])
    path = filedialog.asksaveasfilename(
        defaultextension=f".{ext}",
        filetypes=filetypes + [("All files", "*.*")],
        initialfile=default_name,
    )
    if not path:
        return
    try:
        export_fn(*args, path)
        messagebox.showinfo("Exported", f"File saved:\n{path}")
        try:
            os.startfile(path)
        except Exception:
            pass
    except Exception as e:
        messagebox.showerror("Export Error", str(e))

def _export_btns(parent, pdf_cmd, xl_cmd, csv_cmd):
    ctk.CTkFrame(parent, fg_color=COLORS["border"], width=1, height=28
                 ).pack(side="left", padx=10, pady=4, fill="y")
    ctk.CTkLabel(parent, text="Export:", text_color=COLORS["text_muted"],
                 font=ctk.CTkFont(size=10)).pack(side="left", padx=(0, 3))
    for label, cmd, fg, hov in [
        ("PDF",   pdf_cmd, "#062530", "#0891b2"),
        ("Excel", xl_cmd,  "#062530", "#0d9488"),
        ("CSV",   csv_cmd, COLORS["border"], "#1a2235"),
    ]:
        ctk.CTkButton(parent, text=label, width=72 if "Excel" in label else 60,
                      height=34, fg_color=fg, hover_color=hov,
                      font=ctk.CTkFont(size=11),
                      command=cmd).pack(side="left", padx=2)


# ── AI Insights Dialog ────────────────────────────────────────────────────────

class AIInsightsDialog(ctk.CTkToplevel):
    """Streams financial analysis from Claude into a readable dialog."""

    def __init__(self, parent, report_title, prompt):
        super().__init__(parent)
        self.title(f"AI Insights — {report_title}")
        self.geometry("680x540")
        self.resizable(True, True)
        self.grab_set()

        # Header bar
        hdr = ctk.CTkFrame(self, fg_color="#1a0a2e", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text=f"✨  AI Insights: {report_title}",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="#c39bd3").pack(side="left", padx=16, pady=12)

        self._prompt = prompt
        cfg = db.get_config()
        api_key = cfg.get("anthropic_api_key", "").strip()

        if not api_key:
            self._show_key_setup()
        else:
            self._api_key = api_key
            self._build_content_area()
            threading.Thread(target=self._fetch, daemon=True).start()

    # ── key setup ─────────────────────────────────────────────────────────────
    def _show_key_setup(self):
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=24, pady=20)
        ctk.CTkLabel(f, text="Enter your Anthropic API Key to enable AI Insights",
                     text_color="#ecf0f1", font=ctk.CTkFont(size=13, weight="bold")
                     ).pack(pady=(8, 4))
        ctk.CTkLabel(f, text="Get your free key at: console.anthropic.com",
                     text_color="#3498db", font=ctk.CTkFont(size=11)).pack(pady=(0, 20))
        self._key_entry = ctk.CTkEntry(f, width=460, placeholder_text="sk-ant-...")
        self._key_entry.pack(pady=(0, 14))
        ctk.CTkButton(f, text="Save Key & Analyze", width=200, height=38,
                      fg_color="#6c3483", hover_color="#8e44ad",
                      command=self._save_and_go).pack()

    def _save_and_go(self):
        key = self._key_entry.get().strip()
        if not key:
            messagebox.showerror("Error", "Please enter an API key.", parent=self)
            return
        cfg = db.get_config()
        cfg["anthropic_api_key"] = key
        db.save_config(cfg)
        self._api_key = key
        # Remove setup frame
        for w in list(self.winfo_children())[1:]:
            w.destroy()
        self._build_content_area()
        threading.Thread(target=self._fetch, daemon=True).start()

    # ── content area ──────────────────────────────────────────────────────────
    def _build_content_area(self):
        self._textbox = ctk.CTkTextbox(self, wrap="word",
                                       fg_color="#0d1117", text_color="#ecf0f1",
                                       font=ctk.CTkFont(size=12))
        self._textbox.pack(fill="both", expand=True, padx=16, pady=(12, 0))
        self._textbox.insert("end", "⏳  Analyzing your financial data…\n\nThis may take a few seconds.")
        self._textbox.configure(state="disabled")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=10)
        ctk.CTkButton(btn_row, text="Close", width=90, height=32,
                      fg_color="#2c3e50", hover_color="#34495e",
                      command=self.destroy).pack(side="right")
        ctk.CTkButton(btn_row, text="📋 Copy", width=90, height=32,
                      fg_color="#1e3a5f", hover_color="#2a4a7f",
                      command=self._copy).pack(side="right", padx=(0, 8))

    def _fetch(self):
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self._api_key)
            msg = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=1024,
                messages=[{"role": "user", "content": self._prompt}],
            )
            self.after(0, self._set_text, msg.content[0].text)
        except ImportError:
            self.after(0, self._set_text,
                       "The 'anthropic' package is not installed.\n\nRun:  pip install anthropic")
        except Exception as e:
            self.after(0, self._set_text, f"Error: {e}")

    def _set_text(self, text):
        try:
            self._textbox.configure(state="normal")
            self._textbox.delete("1.0", "end")
            self._textbox.insert("end", text)
            self._textbox.configure(state="disabled")
        except Exception:
            pass

    def _copy(self):
        try:
            self._textbox.configure(state="normal")
            txt = self._textbox.get("1.0", "end").strip()
            self._textbox.configure(state="disabled")
            self.clipboard_clear()
            self.clipboard_append(txt)
        except Exception:
            pass


# ── Base Page ─────────────────────────────────────────────────────────────────

class BasePage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=COLORS["bg"], corner_radius=0)
        self.app = app

    def refresh(self):
        pass

    def _header(self, title, subtitle=""):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="x", padx=24, pady=(22, 10))
        ctk.CTkLabel(frame, text=title,
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=COLORS["text"]).pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(frame, text=subtitle,
                         font=ctk.CTkFont(size=11),
                         text_color=COLORS["text_muted"]).pack(anchor="w", pady=(2, 0))
        ctk.CTkFrame(self, fg_color=COLORS["border"], height=1,
                     corner_radius=0).pack(fill="x", padx=0)

    def _card(self, parent, title, value, color=None, icon="", sub=""):
        if color is None:
            color = COLORS["accent"]
        f = ctk.CTkFrame(parent, fg_color=COLORS["card_bg"], corner_radius=10,
                         border_width=1, border_color=COLORS["border"])
        # Icon badge
        top = ctk.CTkFrame(f, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(14, 0))
        if icon:
            ic = ctk.CTkFrame(top, width=34, height=34, corner_radius=8,
                              fg_color=_icon_bg(color))
            ic.pack(side="left")
            ic.pack_propagate(False)
            ctk.CTkLabel(ic, text=icon,
                         font=ctk.CTkFont(size=15)).pack(expand=True)
        # Labels
        ctk.CTkLabel(f, text=title,
                     font=ctk.CTkFont(size=10),
                     text_color=COLORS["text_muted"]).pack(padx=14, pady=(8, 2), anchor="w")
        ctk.CTkLabel(f, text=str(value),
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=COLORS["text"]).pack(padx=14, pady=(0, 2), anchor="w")
        if sub:
            ctk.CTkLabel(f, text=sub, font=ctk.CTkFont(size=10),
                         text_color=color).pack(padx=14, pady=(0, 12), anchor="w")
        else:
            ctk.CTkFrame(f, fg_color="transparent", height=12).pack()
        return f


# ── Dashboard Page ────────────────────────────────────────────────────────────

class DashboardPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._inv_search = ""
        self._inv_filter = "All"

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()

        self._header("Dashboard", f"Welcome back · {datetime.now().strftime('%d %b %Y, %I:%M %p')}")

        stats = db.get_dashboard_stats()

        # ── Row 1: Financial KPI cards ────────────────────────────────────────
        fin_outer = ctk.CTkFrame(self, fg_color="transparent")
        fin_outer.pack(fill="x", padx=24, pady=(0, 10))
        for i in range(4):
            fin_outer.columnconfigure(i, weight=1)

        net_color = COLORS["success"] if stats["net_this_month"] >= 0 else COLORS["danger"]
        fin_cards = [
            ("Revenue This Month",  f"₹ {stats['revenue_this_month']:,.0f}", COLORS["accent"],  "💰"),
            ("Outstanding",         f"₹ {stats['outstanding']:,.0f}",        COLORS["warning"], "📤"),
            ("Expenses This Month", f"₹ {stats['expenses_this_month']:,.0f}",COLORS["danger"],  "💸"),
            ("Net This Month",      f"₹ {stats['net_this_month']:,.0f}",     net_color,         "📈"),
        ]
        for i, (title, val, color, icon) in enumerate(fin_cards):
            c = self._card(fin_outer, title, val, color, icon)
            c.grid(row=0, column=i, padx=6, pady=4, sticky="ew")

        # ── Row 2: Operational KPI cards ─────────────────────────────────────
        ops_outer = ctk.CTkFrame(self, fg_color="transparent")
        ops_outer.pack(fill="x", padx=24, pady=(0, 10))
        for i in range(4):
            ops_outer.columnconfigure(i, weight=1)

        overdue_color = COLORS["danger"] if stats["overdue_count"] > 0 else COLORS["success"]
        ops_cards = [
            ("Clients",         stats["total_clients"],  COLORS["info"],    "👥"),
            ("Products",        stats["total_products"], COLORS["accent"],   "📦"),
            ("Pending Orders",  stats["pending_orders"], COLORS["warning"],  "⏳"),
            ("Overdue Invoices",stats["overdue_count"],  overdue_color,      "🔔"),
        ]
        for i, (title, val, color, icon) in enumerate(ops_cards):
            c = self._card(ops_outer, title, val, color, icon)
            c.grid(row=0, column=i, padx=6, pady=4, sticky="ew")

        # ── Quick Actions bar ─────────────────────────────────────────────────
        qa_frame = ctk.CTkFrame(self, fg_color=COLORS["card_bg"], corner_radius=10,
                               border_width=1, border_color=COLORS["border"])
        qa_frame.pack(fill="x", padx=24, pady=(0, 10))
        ctk.CTkLabel(qa_frame, text="Quick Actions",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=COLORS["text_muted"]).pack(side="left", padx=16, pady=12)
        for label, page in [
            ("+ New Invoice",    "invoices"),
            ("+ Record Expense", "expenses"),
            ("  Reports",        "reports"),
            ("  Add Client",     "clients"),
        ]:
            ctk.CTkButton(
                qa_frame, text=label, width=130, height=30,
                fg_color=COLORS["accent"], hover_color="#0a7c72",
                text_color="#fff",
                font=ctk.CTkFont(size=11),
                corner_radius=6,
                command=lambda p=page: self.app._show_page(p),
            ).pack(side="left", padx=6, pady=10)

        ctk.CTkButton(
            qa_frame, text="📱 Owner Dashboard", width=148, height=30,
            fg_color="#1e3a5f", hover_color="#2a4f80",
            text_color="#7dd3fc",
            font=ctk.CTkFont(size=11),
            corner_radius=6,
            command=self._open_owner_dashboard,
        ).pack(side="left", padx=6, pady=10)

        # ── Lower panels ─────────────────────────────────────────────────────
        lower = ctk.CTkFrame(self, fg_color="transparent")
        lower.pack(fill="both", expand=True, padx=24, pady=(0, 24))
        lower.columnconfigure(0, weight=1)
        lower.columnconfigure(1, weight=1)
        lower.rowconfigure(0, weight=1)

        self._recent_invoices_panel(lower).grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        self._overdue_panel(lower).grid(row=0, column=1, padx=(8, 0), sticky="nsew")

    def _open_owner_dashboard(self):
        import web_dashboard, webbrowser
        port, token = web_dashboard.start()
        ip   = web_dashboard.get_local_ip()
        url  = f"http://{ip}:{port}/?t={token}"

        win = ctk.CTkToplevel(self)
        win.title("Owner Dashboard")
        win.geometry("360x220")
        win.resizable(False, False)
        win.grab_set()

        ctk.CTkLabel(win, text="📱 Owner Dashboard",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#2dd4bf").pack(pady=(22, 6))
        ctk.CTkLabel(win, text="Open on any browser on the same Wi-Fi:",
                     font=ctk.CTkFont(size=11), text_color="#94a3b8").pack()
        ctk.CTkLabel(win, text=url,
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#7dd3fc").pack(pady=(10, 4))
        ctk.CTkLabel(win, text="Auto-refreshes every 30 seconds",
                     font=ctk.CTkFont(size=10), text_color="#64748b").pack()

        def _copy():
            win.clipboard_clear(); win.clipboard_append(url)
        def _open():
            webbrowser.open(url)

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(pady=16)
        ctk.CTkButton(btn_row, text="📋 Copy URL", width=120, height=32,
                      fg_color="#1e3a5f", hover_color="#2a4f80",
                      text_color="#7dd3fc", command=_copy).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="🌐 Open Browser", width=130, height=32,
                      fg_color="#0d9488", hover_color="#0a7a70",
                      command=_open).pack(side="left", padx=6)

    def _recent_invoices_panel(self, parent):
        f = ctk.CTkFrame(parent, fg_color="#16213e", corner_radius=12)

        # ── title + search bar ───────────────────────────────────────
        top = ctk.CTkFrame(f, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(12, 4))
        ctk.CTkLabel(top, text="🧾  Recent Invoices",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#3498db").pack(side="left")

        self._inv_search_var = ctk.StringVar(value=self._inv_search)
        srch = ctk.CTkEntry(top, textvariable=self._inv_search_var,
                            placeholder_text="🔍 invoice # or client",
                            width=160, height=26,
                            font=ctk.CTkFont(size=11))
        srch.pack(side="right", padx=(4, 0))

        def _on_search(*_):
            self._inv_search = self._inv_search_var.get()
            self.refresh()
        srch.bind("<KeyRelease>", _on_search)

        # ── status filter chips ──────────────────────────────────────
        chips = ctk.CTkFrame(f, fg_color="transparent")
        chips.pack(fill="x", padx=12, pady=(0, 6))
        for label in ("All", "Draft", "Sent", "Partially Paid", "Paid", "Cancelled"):
            active = label == self._inv_filter
            ctk.CTkButton(
                chips, text=label, height=22,
                width=len(label) * 7 + 14,
                font=ctk.CTkFont(size=10),
                fg_color="#0f3460" if active else "#1a2035",
                hover_color="#1a4a8a",
                border_width=1,
                border_color="#3498db" if active else "#2c3e50",
                command=lambda l=label: self._set_inv_filter(l),
            ).pack(side="left", padx=2)

        # ── invoice list ─────────────────────────────────────────────
        invoices = db.get_recent_invoices(20, self._inv_search, self._inv_filter)
        if not invoices:
            msg = "No invoices match." if (self._inv_search or self._inv_filter != "All") else "No invoices yet."
            ctk.CTkLabel(f, text=msg, text_color="#95a5a6").pack(pady=20)
        else:
            # column header
            hdr = ctk.CTkFrame(f, fg_color="transparent")
            hdr.pack(fill="x", padx=16, pady=(0, 2))
            for col, weight, text in [
                (0, 3, "Invoice #"), (1, 4, "Client"),
                (2, 2, "Amount"),    (3, 2, "Status"),
            ]:
                hdr.columnconfigure(col, weight=weight)
                ctk.CTkLabel(hdr, text=text, font=ctk.CTkFont(size=10),
                             text_color="#7f8c8d").grid(row=0, column=col, sticky="w")

            scroll = ctk.CTkScrollableFrame(f, fg_color="transparent")
            scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))
            status_colors = {
                "Paid": "#2ecc71", "Sent": "#3498db",
                "Draft": "#95a5a6", "Cancelled": "#e74c3c",
                "Partially Paid": "#9b59b6",
            }
            for inv in invoices:
                row = ctk.CTkFrame(scroll, fg_color="#0f3460", corner_radius=8,
                                   cursor="hand2")
                row.pack(fill="x", pady=3)
                sc = status_colors.get(inv["status"], "#95a5a6")
                ctk.CTkLabel(row, text=inv["invoice_number"],
                             font=ctk.CTkFont(size=11, weight="bold"),
                             text_color="#3498db", cursor="hand2").pack(side="left", padx=10, pady=7)
                ctk.CTkLabel(row, text=inv["client_name"] or "—",
                             text_color="#bdc3c7", cursor="hand2",
                             font=ctk.CTkFont(size=11)).pack(side="left", padx=4)
                ctk.CTkLabel(row, text=inv["status"],
                             text_color=sc, cursor="hand2",
                             font=ctk.CTkFont(size=11, weight="bold")).pack(side="right", padx=10)
                ctk.CTkLabel(row, text=f"₹{inv['grand_total']:,.0f}",
                             text_color="#ecf0f1", cursor="hand2",
                             font=ctk.CTkFont(size=11)).pack(side="right", padx=6)
                def _go(e=None, iid=inv["id"]): InvoiceViewDialog(self, self.app, iid)
                row.bind("<Button-1>", _go)
                for child in row.winfo_children():
                    child.bind("<Button-1>", _go)
                row.bind("<Enter>", lambda e, r=row: r.configure(fg_color="#1a4a8a"))
                row.bind("<Leave>", lambda e, r=row: r.configure(fg_color="#0f3460"))
        return f

    def _set_inv_filter(self, status):
        self._inv_filter = status
        self.refresh()

    def _overdue_panel(self, parent):
        f = ctk.CTkFrame(parent, fg_color="#16213e", corner_radius=12)
        ctk.CTkLabel(f, text="🔔  Overdue Invoices",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#e74c3c").pack(padx=16, pady=(14, 4), anchor="w")

        overdue = db.get_overdue_invoices()
        if not overdue:
            ctk.CTkLabel(f, text="✅  No overdue invoices",
                         text_color="#2ecc71").pack(padx=16, pady=20)
            # Show low stock as bonus panel content
            ctk.CTkLabel(f, text="⚠  Low Stock Alert",
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color="#f39c12").pack(padx=16, pady=(8, 4), anchor="w")
            low = db.get_low_stock_products()
            if not low:
                ctk.CTkLabel(f, text="✅  All stock levels healthy",
                             text_color="#2ecc71").pack(padx=16, pady=8)
            else:
                scroll = ctk.CTkScrollableFrame(f, fg_color="transparent")
                scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))
                for p in low:
                    row = ctk.CTkFrame(scroll, fg_color="#0f3460", corner_radius=8)
                    row.pack(fill="x", pady=3)
                    ctk.CTkLabel(row, text=p["name"],
                                 font=ctk.CTkFont(size=12, weight="bold"),
                                 text_color="#ecf0f1").pack(side="left", padx=12, pady=8)
                    ctk.CTkLabel(
                        row,
                        text=f"{p['stock_quantity']} / {p['low_stock_threshold']} {p['unit']}",
                        text_color="#f39c12",
                        font=ctk.CTkFont(size=11),
                    ).pack(side="right", padx=12)
                    def _go_stock(e=None, pid=p["id"]):
                        self.app._show_page("stock")
                    row.bind("<Button-1>", _go_stock)
                    row.configure(cursor="hand2")
                    for child in row.winfo_children():
                        child.bind("<Button-1>", _go_stock)
                        child.configure(cursor="hand2")
        else:
            scroll = ctk.CTkScrollableFrame(f, fg_color="transparent")
            scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))
            for inv in overdue:
                row = ctk.CTkFrame(scroll, fg_color="#2c0f0f", corner_radius=8)
                row.pack(fill="x", pady=3)
                days_over = (datetime.now().date() -
                             datetime.strptime(inv["due_date"], "%Y-%m-%d").date()).days
                ctk.CTkLabel(row, text=inv["invoice_number"],
                             font=ctk.CTkFont(size=11, weight="bold"),
                             text_color="#ecf0f1").pack(side="left", padx=10, pady=7)
                ctk.CTkLabel(row, text=inv["client_name"] or "—",
                             text_color="#bdc3c7",
                             font=ctk.CTkFont(size=11)).pack(side="left", padx=4)
                ctk.CTkLabel(row, text=f"{days_over}d overdue",
                             text_color="#e74c3c",
                             font=ctk.CTkFont(size=11, weight="bold")).pack(side="right", padx=10)
                ctk.CTkLabel(row, text=f"₹{inv['grand_total']:,.0f}",
                             text_color="#ecf0f1",
                             font=ctk.CTkFont(size=11)).pack(side="right", padx=6)
                # make entire row clickable
                def _go(e=None, iid=inv["id"]):
                    InvoiceViewDialog(self, self.app, iid)
                row.bind("<Button-1>", _go)
                row.configure(cursor="hand2")
                for child in row.winfo_children():
                    child.bind("<Button-1>", _go)
                    child.configure(cursor="hand2")
        return f


# ── Orders Page ───────────────────────────────────────────────────────────────

class OrdersPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()

        self._header("Orders", "Search by order code or browse all orders")

        # Search bar
        search_frame = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=10)
        search_frame.pack(fill="x", padx=24, pady=(0, 12))

        self.search_var = ctk.StringVar()
        entry = ctk.CTkEntry(
            search_frame, placeholder_text="🔍  Enter Order Code (e.g. ORD-2024-001)",
            textvariable=self.search_var,
            font=ctk.CTkFont(size=13), height=42, width=350,
        )
        entry.pack(side="left", padx=12, pady=10)
        entry.bind("<Return>", lambda e: self._search_order())

        ctk.CTkButton(search_frame, text="Search", width=100, height=36,
                      command=self._search_order).pack(side="left", padx=4)

        ctk.CTkButton(search_frame, text="+ New Order", width=120, height=36,
                      fg_color="#2ecc71", hover_color="#27ae60", text_color="#000",
                      command=self._new_order_dialog).pack(side="right", padx=12)

        # Result area
        self.result_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.result_frame.pack(fill="both", expand=True, padx=24, pady=(0, 24))
        self._show_all_orders()

    def _search_order(self):
        for w in self.result_frame.winfo_children():
            w.destroy()

        code = self.search_var.get().strip()
        if not code:
            self._show_all_orders()
            return

        order, items = db.get_order_by_code(code)
        if not order:
            ctk.CTkLabel(self.result_frame,
                         text=f'❌  No order found with code "{code}"',
                         text_color="#e74c3c",
                         font=ctk.CTkFont(size=14)).pack(pady=40)
            return

        self._render_order_detail(order, items)

    def _render_order_detail(self, order, items):
        status_color = {
            "Pending": "#f39c12", "Processing": "#3498db",
            "Delivered": "#2ecc71", "Cancelled": "#e74c3c",
        }.get(order["status"], "#95a5a6")

        # Header card
        hdr = ctk.CTkFrame(self.result_frame, fg_color="#16213e", corner_radius=12)
        hdr.pack(fill="x", pady=(0, 10))

        col1 = ctk.CTkFrame(hdr, fg_color="transparent")
        col1.pack(side="left", padx=20, pady=16)
        ctk.CTkLabel(col1, text=order["order_code"],
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color="#3498db").pack(anchor="w")
        ctk.CTkLabel(col1, text=f"Client: {order['client_name']}",
                     text_color="#ecf0f1", font=ctk.CTkFont(size=13)).pack(anchor="w")
        ctk.CTkLabel(col1, text=f"📧 {order['client_email'] or '—'}   📞 {order['client_phone'] or '—'}",
                     text_color="#95a5a6", font=ctk.CTkFont(size=11)).pack(anchor="w")

        col2 = ctk.CTkFrame(hdr, fg_color="transparent")
        col2.pack(side="right", padx=20)
        ctk.CTkLabel(col2, text=order["status"],
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=status_color).pack(anchor="e")
        ctk.CTkLabel(col2, text=order["created_at"][:10],
                     text_color="#95a5a6", font=ctk.CTkFont(size=11)).pack(anchor="e")

        if order["notes"]:
            ctk.CTkLabel(col1, text=f"📝 {order['notes']}",
                         text_color="#95a5a6", font=ctk.CTkFont(size=11)).pack(anchor="w")

        # Items table
        tbl_frame = ctk.CTkFrame(self.result_frame, fg_color="#16213e", corner_radius=12)
        tbl_frame.pack(fill="both", expand=True)

        ctk.CTkLabel(tbl_frame, text="Order Items",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#ecf0f1").pack(padx=16, pady=(14, 4), anchor="w")

        # Column headers
        headers = ctk.CTkFrame(tbl_frame, fg_color="#0f3460", corner_radius=6)
        headers.pack(fill="x", padx=12, pady=2)
        for col, w in [("SKU", 100), ("Product", 280), ("Qty", 80), ("Unit Price", 120), ("Subtotal", 120)]:
            ctk.CTkLabel(headers, text=col, width=w,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#95a5a6").pack(side="left", padx=8, pady=6)

        total = 0
        scroll = ctk.CTkScrollableFrame(tbl_frame, fg_color="transparent", height=200)
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 4))
        for item in items:
            subtotal = item["quantity"] * item["unit_price"]
            total += subtotal
            row = ctk.CTkFrame(scroll, fg_color="#16213e", corner_radius=6)
            row.pack(fill="x", pady=2)
            for val, w in [
                (item["sku"], 100), (item["product_name"], 280),
                (f"{item['quantity']} {item['unit']}", 80),
                (f"₹{item['unit_price']:,.2f}", 120),
                (f"₹{subtotal:,.2f}", 120),
            ]:
                ctk.CTkLabel(row, text=str(val), width=w,
                             font=ctk.CTkFont(size=12),
                             text_color="#ecf0f1").pack(side="left", padx=8, pady=6)

        # Total
        tot = ctk.CTkFrame(tbl_frame, fg_color="#0f3460", corner_radius=6)
        tot.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkLabel(tot, text="TOTAL", font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#95a5a6").pack(side="left", padx=16, pady=8)
        ctk.CTkLabel(tot, text=f"₹{total:,.2f}",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#2ecc71").pack(side="right", padx=16)

    def _show_all_orders(self):
        for w in self.result_frame.winfo_children():
            w.destroy()

        orders = db.get_all_orders()
        if not orders:
            ctk.CTkLabel(self.result_frame, text="No orders yet.",
                         text_color="#95a5a6").pack(pady=40)
            return

        tbl = ctk.CTkFrame(self.result_frame, fg_color="#16213e", corner_radius=12)
        tbl.pack(fill="both", expand=True)

        ctk.CTkLabel(tbl, text="All Orders",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#ecf0f1").pack(padx=16, pady=(14, 4), anchor="w")

        hdr = ctk.CTkFrame(tbl, fg_color="#0f3460", corner_radius=6)
        hdr.pack(fill="x", padx=12, pady=2)
        for col, w in [("Order Code", 160), ("Client", 220), ("Status", 110), ("Date", 120), ("Actions", 100)]:
            ctk.CTkLabel(hdr, text=col, width=w,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#95a5a6").pack(side="left", padx=8, pady=6)

        scroll = ctk.CTkScrollableFrame(tbl, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        for o in orders:
            status_color = {
                "Pending": "#f39c12", "Processing": "#3498db",
                "Delivered": "#2ecc71", "Cancelled": "#e74c3c",
            }.get(o["status"], "#95a5a6")
            row = ctk.CTkFrame(scroll, fg_color="#16213e", corner_radius=6)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=o["order_code"], width=160,
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#3498db").pack(side="left", padx=8, pady=6)
            ctk.CTkLabel(row, text=o["client_name"], width=220,
                         text_color="#ecf0f1", font=ctk.CTkFont(size=12)).pack(side="left")
            ctk.CTkLabel(row, text=o["status"], width=110,
                         text_color=status_color,
                         font=ctk.CTkFont(size=11, weight="bold")).pack(side="left")
            ctk.CTkLabel(row, text=o["created_at"][:10], width=120,
                         text_color="#95a5a6", font=ctk.CTkFont(size=11)).pack(side="left")
            ctk.CTkButton(row, text="View", width=70, height=28,
                          fg_color="#0f3460", hover_color="#1a4a8a",
                          font=ctk.CTkFont(size=11),
                          command=lambda code=o["order_code"]: self._view_order(code)
                          ).pack(side="left", padx=4)

    def _view_order(self, order_code):
        self.search_var.set(order_code)
        self._search_order()

    def _new_order_dialog(self):
        NewOrderDialog(self, self.app)


# ── Barcode / QR Dialogs ─────────────────────────────────────────────────────

class BarcodeScanDialog(ctk.CTkToplevel):
    """
    Universal scan-to-search dialog.
    Works with USB HID barcode scanners (they emulate keyboard + Enter)
    and with manual typing.  Searches products by SKU and invoices by number.
    """
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("🔍  Barcode / QR Scan")
        self.geometry("520x480")
        self.resizable(False, False)
        self.grab_set()
        self._build()
        # Focus the entry after window draws
        self.after(100, self._entry.focus_set)

    def _build(self):
        ctk.CTkLabel(self, text="🔍  Scan or Type a Barcode",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(20, 4))
        ctk.CTkLabel(self,
                     text="Point a USB scanner at this window and scan,\n"
                          "or type a SKU / invoice number and press Enter.",
                     text_color="#95a5a6", font=ctk.CTkFont(size=11)).pack(pady=(0, 12))

        ef = ctk.CTkFrame(self, fg_color="transparent")
        ef.pack(fill="x", padx=24)
        self._entry = ctk.CTkEntry(ef, placeholder_text="Scan or type here…",
                                   font=ctk.CTkFont(size=14), height=42)
        self._entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(ef, text="Search", width=90, height=42,
                      fg_color="#0f3460", hover_color="#1a4a8a",
                      command=self._search).pack(side="left")

        self._entry.bind("<Return>", lambda _e: self._search())
        self._entry.bind("<KP_Enter>", lambda _e: self._search())

        self._result_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._result_frame.pack(fill="both", expand=True, padx=24, pady=12)

        ctk.CTkLabel(self._result_frame,
                     text="Result will appear here.",
                     text_color="#444", font=ctk.CTkFont(size=12)).pack(pady=30)

        ctk.CTkButton(self, text="Close", width=100,
                      fg_color="#2c3e50", hover_color="#3d5166",
                      command=self.destroy).pack(pady=(0, 16))

    def _search(self):
        for w in self._result_frame.winfo_children():
            w.destroy()
        query = self._entry.get().strip()
        if not query:
            return

        # Try product SKU first (exact, then partial)
        products = db.get_all_products()
        prod = next((p for p in products if p["sku"].upper() == query.upper()), None)
        if not prod:
            prod = next((p for p in products
                         if query.upper() in p["sku"].upper() or query.upper() in p["name"].upper()), None)

        if prod:
            self._show_product_result(dict(prod))
            return

        # Try invoice number
        try:
            inv = db.get_invoice_by_number(query)
        except Exception:
            inv = None
        if inv:
            self._show_invoice_result(dict(inv))
            return

        ctk.CTkLabel(self._result_frame,
                     text=f"No product or invoice found for: '{query}'",
                     text_color="#e74c3c", font=ctk.CTkFont(size=12)).pack(pady=20)

    def _show_product_result(self, p):
        card = ctk.CTkFrame(self._result_frame, fg_color="#16213e", corner_radius=10)
        card.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(card, text="📦  Product Found",
                     text_color="#2ecc71", font=ctk.CTkFont(size=12, weight="bold")).pack(pady=(10, 2))
        for label, val in [("SKU", p["sku"]), ("Name", p["name"]),
                           ("Sale Price", f"₹{p['unit_price']:,.2f}"),
                           ("In Stock", f"{p['stock_quantity']} {p['unit']}")]:
            r = ctk.CTkFrame(card, fg_color="transparent")
            r.pack(fill="x", padx=16, pady=1)
            ctk.CTkLabel(r, text=f"{label}:", text_color="#95a5a6",
                         font=ctk.CTkFont(size=11), width=90, anchor="w").pack(side="left")
            ctk.CTkLabel(r, text=str(val), font=ctk.CTkFont(size=11, weight="bold"),
                         anchor="w").pack(side="left")
        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(pady=(6, 10))
        ctk.CTkButton(btns, text="✏ Edit Product", width=120,
                      fg_color="#0f3460", hover_color="#1a4a8a",
                      command=lambda: self._edit_product(p)).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="🏷 View Label", width=110,
                      fg_color="#4a235a", hover_color="#6c3483",
                      command=lambda: ProductLabelDialog(self, p)).pack(side="left", padx=4)

    def _show_invoice_result(self, inv):
        card = ctk.CTkFrame(self._result_frame, fg_color="#16213e", corner_radius=10)
        card.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(card, text="🧾  Invoice Found",
                     text_color="#3498db", font=ctk.CTkFont(size=12, weight="bold")).pack(pady=(10, 2))
        for label, val in [("Invoice #", inv.get("invoice_number", "")),
                           ("Client", inv.get("client_name", inv.get("client_id", ""))),
                           ("Date", inv.get("invoice_date", "")),
                           ("Amount", f"₹{inv.get('grand_total', 0):,.2f}"),
                           ("Status", inv.get("status", ""))]:
            r = ctk.CTkFrame(card, fg_color="transparent")
            r.pack(fill="x", padx=16, pady=1)
            ctk.CTkLabel(r, text=f"{label}:", text_color="#95a5a6",
                         font=ctk.CTkFont(size=11), width=90, anchor="w").pack(side="left")
            ctk.CTkLabel(r, text=str(val), font=ctk.CTkFont(size=11, weight="bold"),
                         anchor="w").pack(side="left")
        ctk.CTkButton(card, text="📂 Open Invoices Page", width=160,
                      fg_color="#0f3460", hover_color="#1a4a8a",
                      command=lambda: (self.app._show_page("invoices"), self.destroy())
                      ).pack(pady=(6, 10))

    def _edit_product(self, p):
        self.destroy()
        self.app._show_page("stock")
        products = {prod["id"]: prod for prod in db.get_all_products()}
        ProductDialog(self.app, self.app, products.get(p["id"]))


class ProductLabelDialog(ctk.CTkToplevel):
    """Shows a QR code label for a product that can be saved as PNG."""

    def __init__(self, parent, product):
        super().__init__(parent)
        self.product = product
        self.title(f"Label — {product['sku']}")
        self.geometry("360x460")
        self.resizable(False, False)
        self.grab_set()
        self._qr_img = None
        self._build()

    def _build(self):
        p = self.product
        ctk.CTkLabel(self, text="🏷  Product Label / QR Code",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(16, 4))

        try:
            import qrcode
            qr = qrcode.QRCode(version=1, box_size=6, border=3)
            qr.add_data(p["sku"])
            qr.make(fit=True)
            pil_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
            # Resize to 220×220 for display
            pil_img_disp = pil_img.resize((220, 220))
            from PIL import ImageDraw, ImageFont as _IF
            self._qr_pil = pil_img  # full-res for saving
            ctk_img = ctk.CTkImage(light_image=pil_img_disp, size=(220, 220))
            ctk.CTkLabel(self, image=ctk_img, text="").pack(pady=(0, 4))
        except ImportError:
            ctk.CTkLabel(self, text="[qrcode library not installed]\nRun: pip install qrcode[pil]",
                         text_color="#e74c3c", font=ctk.CTkFont(size=11)).pack(pady=20)
            self._qr_pil = None

        # Product info below the QR
        info = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=8)
        info.pack(fill="x", padx=24, pady=(0, 8))
        ctk.CTkLabel(info, text=p["name"][:35],
                     font=ctk.CTkFont(size=12, weight="bold")).pack(pady=(6, 0))
        ctk.CTkLabel(info, text=f"SKU: {p['sku']}   |   ₹{p['unit_price']:,.2f}",
                     text_color="#95a5a6", font=ctk.CTkFont(size=11)).pack(pady=(0, 6))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=(0, 12))
        if self._qr_pil:
            ctk.CTkButton(btns, text="💾 Save PNG", width=110,
                          fg_color="#1a6a3a", hover_color="#238a4f",
                          command=self._save_png).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="Close", width=90,
                      fg_color="#2c3e50", hover_color="#3d5166",
                      command=self.destroy).pack(side="left", padx=4)

    def _save_png(self):
        import tkinter.filedialog as fd
        fp = fd.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png")],
            initialfile=f"label_{self.product['sku']}.png",
        )
        if not fp:
            return
        # Save with product info printed below QR (using Pillow)
        try:
            from PIL import Image, ImageDraw
            qr_img = self._qr_pil.resize((300, 300))
            canvas = Image.new("RGB", (300, 380), "white")
            canvas.paste(qr_img, (0, 0))
            draw = ImageDraw.Draw(canvas)
            draw.text((10, 310), self.product["name"][:40], fill="black")
            draw.text((10, 330), f"SKU: {self.product['sku']}", fill="#333333")
            draw.text((10, 350), f"Price: Rs.{self.product['unit_price']:,.2f}", fill="#333333")
            canvas.save(fp)
            messagebox.showinfo("Saved", f"Label saved:\n{fp}")
        except Exception as e:
            messagebox.showerror("Error", str(e))


# ── Stock Page ────────────────────────────────────────────────────────────────

class StockPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._header("Stock Management", "Track product inventory and pricing")

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=24, pady=(0, 8))
        ctk.CTkButton(toolbar, text="+ Add Product", fg_color="#2ecc71",
                      hover_color="#27ae60", text_color="#000",
                      command=self._add_product_dialog).pack(side="left")
        ctk.CTkButton(toolbar, text="📦 Adjust Stock", fg_color="#3498db",
                      command=self._adjust_stock_dialog).pack(side="left", padx=8)
        ctk.CTkButton(toolbar, text="🔍 Scan Barcode", fg_color="#6c3483",
                      hover_color="#8e44ad",
                      command=lambda: BarcodeScanDialog(self, self.app)).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="🏭 Godowns", fg_color="#1a5276",
                      hover_color="#2980b9",
                      command=lambda: self.app.show_page("godowns")).pack(side="left", padx=4)

        # Table
        tbl = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=12)
        tbl.pack(fill="both", expand=True, padx=24, pady=(0, 24))

        hdr = ctk.CTkFrame(tbl, fg_color="#0f3460", corner_radius=6)
        hdr.pack(fill="x", padx=12, pady=(12, 2))
        cols = [("SKU", 110), ("Name", 220), ("Unit Price", 110), ("Stock", 90),
                ("Threshold", 90), ("Unit", 70), ("Status", 90), ("Actions", 140)]
        for col, w in cols:
            ctk.CTkLabel(hdr, text=col, width=w,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#95a5a6").pack(side="left", padx=6, pady=6)

        scroll = ctk.CTkScrollableFrame(tbl, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        products = db.get_all_products()
        for p in products:
            is_low = p["stock_quantity"] <= p["low_stock_threshold"]
            status = "⚠ Low" if is_low else "✅ OK"
            status_color = "#e74c3c" if is_low else "#2ecc71"
            row = ctk.CTkFrame(scroll,
                               fg_color="#1a1a2e" if is_low else "#16213e",
                               corner_radius=6)
            row.pack(fill="x", pady=2)
            vals = [
                (p["sku"], 110, "#95a5a6"),
                (p["name"], 220, "#ecf0f1"),
                (f"₹{p['unit_price']:,.2f}", 110, "#2ecc71"),
                (str(p["stock_quantity"]), 90, "#e74c3c" if is_low else "#ecf0f1"),
                (str(p["low_stock_threshold"]), 90, "#95a5a6"),
                (p["unit"], 70, "#95a5a6"),
            ]
            for val, w, color in vals:
                ctk.CTkLabel(row, text=val, width=w,
                             font=ctk.CTkFont(size=11),
                             text_color=color).pack(side="left", padx=6, pady=6)
            ctk.CTkLabel(row, text=status, width=90,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=status_color).pack(side="left", padx=6)
            ctk.CTkButton(row, text="Edit", width=56, height=26,
                          fg_color="#0f3460", hover_color="#1a4a8a",
                          font=ctk.CTkFont(size=11),
                          command=lambda pid=p["id"]: self._edit_product_dialog(pid)
                          ).pack(side="left", padx=2)
            ctk.CTkButton(row, text="🏷", width=36, height=26,
                          fg_color="#4a235a", hover_color="#6c3483",
                          font=ctk.CTkFont(size=11),
                          command=lambda pp=dict(p): ProductLabelDialog(self, pp)
                          ).pack(side="left", padx=2)
            ctk.CTkButton(row, text="Del", width=46, height=26,
                          fg_color="#7f1f1f", hover_color="#c0392b",
                          font=ctk.CTkFont(size=11),
                          command=lambda pid=p["id"], pn=p["name"]: self._delete_product(pid, pn)
                          ).pack(side="left", padx=2)

    def _add_product_dialog(self):
        ProductDialog(self, self.app, None)

    def _edit_product_dialog(self, product_id):
        products = {p["id"]: p for p in db.get_all_products()}
        ProductDialog(self, self.app, products.get(product_id))

    def _delete_product(self, product_id, name):
        if messagebox.askyesno("Confirm Delete", f"Delete product '{name}'?"):
            db.delete_product(product_id)
            self.refresh()

    def _adjust_stock_dialog(self):
        AdjustStockDialog(self, self.app)


# ── Clients Page ──────────────────────────────────────────────────────────────

class ClientsPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._header("Clients", "Manage your client accounts")

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=24, pady=(0, 8))
        ctk.CTkButton(toolbar, text="+ Add Client", fg_color="#2ecc71",
                      hover_color="#27ae60", text_color="#000",
                      command=self._add_client_dialog).pack(side="left")

        tbl = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=12)
        tbl.pack(fill="both", expand=True, padx=24, pady=(0, 24))

        hdr = ctk.CTkFrame(tbl, fg_color="#0f3460", corner_radius=6)
        hdr.pack(fill="x", padx=12, pady=(12, 2))
        for col, w in [("Name", 180), ("Phone", 110), ("GSTIN", 160),
                       ("Credit Limit", 110), ("Outstanding", 110), ("Used %", 120),
                       ("Actions", 190)]:
            ctk.CTkLabel(hdr, text=col, width=w,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#95a5a6").pack(side="left", padx=6, pady=6)

        scroll = ctk.CTkScrollableFrame(tbl, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        clients = db.get_all_clients()
        for c in clients:
            c = dict(c)
            outstanding = db.get_client_outstanding(c["id"])
            limit = c.get("credit_limit") or 0
            over_limit = limit > 0 and outstanding > limit

            row = ctk.CTkFrame(scroll,
                               fg_color="#2c1010" if over_limit else "#16213e",
                               corner_radius=6)
            row.pack(fill="x", pady=2)

            ctk.CTkLabel(row, text=c["name"], width=180,
                         font=ctk.CTkFont(size=11, weight="bold" if over_limit else "normal"),
                         text_color="#e74c3c" if over_limit else "#ecf0f1",
                         anchor="w").pack(side="left", padx=6, pady=6)
            ctk.CTkLabel(row, text=c["phone"] or "—", width=110,
                         font=ctk.CTkFont(size=11), text_color="#95a5a6",
                         anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=c.get("gstin") or "—", width=160,
                         font=ctk.CTkFont(size=11), text_color="#95a5a6",
                         anchor="w").pack(side="left", padx=4)

            # Credit limit
            if limit > 0:
                lim_txt = f"₹{limit:,.0f}"
                lim_col = "#f39c12"
            else:
                lim_txt = "No limit"
                lim_col = "#555"
            ctk.CTkLabel(row, text=lim_txt, width=110, anchor="e",
                         font=ctk.CTkFont(size=11), text_color=lim_col
                         ).pack(side="left", padx=4)

            # Outstanding
            out_col = "#e74c3c" if over_limit else ("#f39c12" if outstanding > 0 else "#2ecc71")
            ctk.CTkLabel(row, text=f"₹{outstanding:,.0f}", width=110, anchor="e",
                         font=ctk.CTkFont(size=11, weight="bold" if over_limit else "normal"),
                         text_color=out_col).pack(side="left", padx=4)

            # Utilization bar cell
            bar_cell = ctk.CTkFrame(row, fg_color="transparent", width=120)
            bar_cell.pack(side="left", padx=4, pady=4)
            bar_cell.pack_propagate(False)
            if limit > 0:
                pct = min(outstanding / limit, 1.0)
                bar_col = "#e74c3c" if pct >= 1.0 else ("#f39c12" if pct >= 0.75 else "#2ecc71")
                bg_bar = ctk.CTkFrame(bar_cell, fg_color="#2c3e50",
                                      height=8, corner_radius=4)
                bg_bar.pack(fill="x", padx=2, pady=(10, 0))
                fill_w = max(int(116 * pct), 4 if outstanding > 0 else 0)
                if fill_w > 0:
                    fill_bar = ctk.CTkFrame(bg_bar, fg_color=bar_col,
                                            height=8, width=fill_w, corner_radius=4)
                    fill_bar.place(x=0, y=0)
                ctk.CTkLabel(bar_cell, text=f"{pct*100:.0f}%",
                             font=ctk.CTkFont(size=10),
                             text_color=bar_col).pack()
            else:
                ctk.CTkLabel(bar_cell, text="—", font=ctk.CTkFont(size=11),
                             text_color="#555").pack(pady=6)

            ctk.CTkButton(row, text="📄 Statement", width=90, height=26,
                          fg_color="#1a3a5c", hover_color="#2355c2",
                          font=ctk.CTkFont(size=10),
                          command=lambda cid=c["id"], cn=c["name"]: ClientStatementDialog(self, self.app, cid, cn)
                          ).pack(side="left", padx=2)
            ctk.CTkButton(row, text="Edit", width=48, height=26,
                          fg_color="#0f3460", hover_color="#1a4a8a",
                          font=ctk.CTkFont(size=11),
                          command=lambda cid=c["id"]: self._edit_client_dialog(cid)
                          ).pack(side="left", padx=2)
            ctk.CTkButton(row, text="Del", width=38, height=26,
                          fg_color="#7f1f1f", hover_color="#c0392b",
                          font=ctk.CTkFont(size=11),
                          command=lambda cid=c["id"], cn=c["name"]: self._delete_client(cid, cn)
                          ).pack(side="left", padx=2)

    def _add_client_dialog(self):
        ClientDialog(self, self.app, None)

    def _edit_client_dialog(self, client_id):
        clients = {c["id"]: c for c in db.get_all_clients()}
        ClientDialog(self, self.app, clients.get(client_id))

    def _delete_client(self, client_id, name):
        if messagebox.askyesno("Confirm Delete", f"Delete client '{name}'?"):
            db.delete_client(client_id)
            self.refresh()


# ── Alerts Page ───────────────────────────────────────────────────────────────

class AlertsPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        db.check_and_create_alerts()
        self._header("Stock Alerts", "Products that need restocking")

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=24, pady=(0, 8))
        ctk.CTkButton(toolbar, text="✓ Mark All Read", fg_color="#0f3460",
                      command=self._mark_all_read).pack(side="left")

        alerts = db.get_unread_alerts()
        self.app.sidebar.update_alert_badge(len(alerts))

        if not alerts:
            info = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=12)
            info.pack(fill="x", padx=24, pady=16)
            ctk.CTkLabel(info, text="✅  No unread alerts — all stock levels are healthy!",
                         font=ctk.CTkFont(size=14),
                         text_color="#2ecc71").pack(pady=24)
        else:
            scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
            scroll.pack(fill="both", expand=True, padx=24, pady=(0, 24))
            for a in alerts:
                card = ctk.CTkFrame(scroll, fg_color="#2c1010", corner_radius=10)
                card.pack(fill="x", pady=4)

                top = ctk.CTkFrame(card, fg_color="transparent")
                top.pack(fill="x", padx=16, pady=(12, 2))
                ctk.CTkLabel(top, text=f"⚠  {a['product_name']}",
                             font=ctk.CTkFont(size=13, weight="bold"),
                             text_color="#e74c3c").pack(side="left")
                ctk.CTkLabel(top, text=a["created_at"][:16],
                             text_color="#95a5a6",
                             font=ctk.CTkFont(size=11)).pack(side="right")

                ctk.CTkLabel(card, text=a["message"],
                             text_color="#ecf0f1",
                             font=ctk.CTkFont(size=11),
                             wraplength=800, justify="left").pack(padx=16, pady=(0, 4), anchor="w")

                btn_row = ctk.CTkFrame(card, fg_color="transparent")
                btn_row.pack(fill="x", padx=16, pady=(0, 10))
                ctk.CTkButton(btn_row, text="Mark Read", width=100, height=28,
                              fg_color="#0f3460", hover_color="#1a4a8a",
                              font=ctk.CTkFont(size=11),
                              command=lambda aid=a["id"]: self._mark_read(aid)
                              ).pack(side="left")
                ctk.CTkButton(btn_row, text="Go to Stock →", width=120, height=28,
                              fg_color="transparent", hover_color="#16213e",
                              border_width=1, border_color="#0f3460",
                              font=ctk.CTkFont(size=11),
                              command=lambda: self.app._show_page("stock")
                              ).pack(side="left", padx=8)

    def _mark_read(self, alert_id):
        db.mark_alert_read(alert_id)
        self.refresh()

    def _mark_all_read(self):
        db.mark_all_alerts_read()
        self.refresh()


# ── Dialogs ───────────────────────────────────────────────────────────────────

class BaseDialog(ctk.CTkToplevel):
    def __init__(self, parent, app, title):
        super().__init__(parent)
        self.app = app
        self.title(title)
        self.grab_set()
        self.resizable(False, False)
        ctk.CTkLabel(self, text=title,
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(16, 8), padx=24, anchor="w")

    def _field(self, parent, label, default="", width=360):
        ctk.CTkLabel(parent, text=label, text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=24, pady=(8, 0))
        var = ctk.StringVar(value=str(default))
        entry = ctk.CTkEntry(parent, textvariable=var, width=width)
        entry.pack(padx=24, pady=(2, 0))
        return var

    def _buttons(self, on_save):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(pady=16, padx=24, fill="x")
        ctk.CTkButton(frame, text="Save", fg_color="#2ecc71",
                      hover_color="#27ae60", text_color="#000",
                      command=on_save).pack(side="right")
        ctk.CTkButton(frame, text="Cancel", fg_color="#7f1f1f",
                      hover_color="#c0392b",
                      command=self.destroy).pack(side="right", padx=8)


class ClientDialog(BaseDialog):
    def __init__(self, parent, app, client=None):
        super().__init__(parent, app, "Edit Client" if client else "Add Client")
        self.client = client
        self.geometry("460x580")
        self._build()

    def _build(self):
        c = dict(self.client) if self.client else {}
        self.name    = self._field(self, "Name *",           c.get("name", ""))
        self.email   = self._field(self, "Email",            c.get("email", ""))
        self.phone   = self._field(self, "Phone",            c.get("phone", ""))
        self.address = self._field(self, "Address",          c.get("address", ""))
        self.gstin   = self._field(self, "GSTIN (15-digit)", c.get("gstin", ""))

        ctk.CTkLabel(self, text="State", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=24, pady=(8, 0))
        self.state_var = ctk.StringVar(value=c.get("state", ""))
        ctk.CTkComboBox(self, values=INDIAN_STATES, variable=self.state_var,
                        width=390).pack(padx=24, pady=(2, 0), anchor="w")

        # Credit limit
        lim_row = ctk.CTkFrame(self, fg_color="transparent")
        lim_row.pack(fill="x", padx=24, pady=(12, 0))
        ctk.CTkLabel(lim_row, text="Credit Limit (₹)", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left")
        ctk.CTkLabel(lim_row, text="  (0 = no limit)",
                     text_color="#555", font=ctk.CTkFont(size=10)).pack(side="left")
        self.credit_limit = ctk.CTkEntry(self, width=390)
        self.credit_limit.insert(0, str(int(c.get("credit_limit", 0) or 0)))
        self.credit_limit.pack(padx=24, pady=(2, 0), anchor="w")

        self._buttons(self._save)

    def _save(self):
        name = self.name.get().strip()
        if not name:
            messagebox.showerror("Error", "Name is required.")
            return
        try:
            credit_limit = float(self.credit_limit.get().strip() or "0")
        except ValueError:
            messagebox.showerror("Error", "Credit limit must be a number.")
            return
        if self.client:
            db.update_client(self.client["id"], name, self.email.get(),
                             self.phone.get(), self.address.get(),
                             self.gstin.get(), self.state_var.get(), credit_limit)
        else:
            db.add_client(name, self.email.get(), self.phone.get(),
                          self.address.get(), self.gstin.get(), self.state_var.get(),
                          credit_limit)
        self.app.refresh_current()
        self.destroy()


class ProductDialog(BaseDialog):
    def __init__(self, parent, app, product=None):
        super().__init__(parent, app, "Edit Product" if product else "Add Product")
        self.product = product
        self.geometry("460x650")
        self._build()

    def _build(self):
        p = dict(self.product) if self.product else {}
        self.geometry("460x740")
        self.name      = self._field(self, "Name *",               p.get("name", ""))
        self.sku       = self._field(self, "SKU *",                 p.get("sku", ""))
        self.desc      = self._field(self, "Description",           p.get("description", ""))
        self.price     = self._field(self, "Sale Price (₹) *",      p.get("unit_price", "0"))
        self.cost      = self._field(self, "Cost Price (₹)",        p.get("cost_price", "0"))
        self.stock     = self._field(self, "Stock Quantity *",      p.get("stock_quantity", "0"))
        self.threshold = self._field(self, "Low Stock Threshold *", p.get("low_stock_threshold", "10"))
        self.unit      = self._field(self, "Unit (pcs/kg/mtrs...)", p.get("unit", "pcs"))
        self.hsn       = self._field(self, "HSN Code",              p.get("hsn_code", ""))
        self.category  = self._field(self, "Category",              p.get("category", ""))

        ctk.CTkLabel(self, text="GST Rate (%)", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=24, pady=(8, 0))
        self.gst_rate_var = ctk.StringVar(value=str(int(p.get("gst_rate", 18))))
        ctk.CTkComboBox(self, values=GST_RATES, variable=self.gst_rate_var,
                        width=200).pack(padx=24, anchor="w", pady=(2, 0))
        self._buttons(self._save)

    def _save(self):
        try:
            name = self.name.get().strip()
            sku  = self.sku.get().strip()
            if not name or not sku:
                raise ValueError("Name and SKU are required.")
            price      = float(self.price.get())
            cost_price = float(self.cost.get())
            stock      = int(self.stock.get())
            threshold  = int(self.threshold.get())
            gst_rate   = float(self.gst_rate_var.get())
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return
        if self.product:
            db.update_product(self.product["id"], name, sku, self.desc.get(),
                              price, stock, threshold, self.unit.get(),
                              self.hsn.get(), gst_rate, cost_price,
                              self.category.get())
        else:
            db.add_product(name, sku, self.desc.get(), price, stock, threshold,
                           self.unit.get(), self.hsn.get(), gst_rate, cost_price,
                           self.category.get())
        db.check_and_create_alerts()
        self.app.refresh_current()
        self.destroy()


class AdjustStockDialog(BaseDialog):
    def __init__(self, parent, app):
        super().__init__(parent, app, "Adjust Stock")
        self.geometry("440x280")
        self._build()

    def _build(self):
        products = db.get_all_products()
        self.product_map = {f"{p['name']} ({p['sku']})": p["id"] for p in products}
        names = list(self.product_map.keys())

        ctk.CTkLabel(self, text="Product", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=24, pady=(8, 0))
        self.product_var = ctk.StringVar(value=names[0] if names else "")
        ctk.CTkComboBox(self, values=names, variable=self.product_var, width=390).pack(padx=24)

        self.delta = self._field(self, "Change (+add / -deduct)", "0")
        self._buttons(self._save)

    def _save(self):
        try:
            delta = int(self.delta.get())
        except ValueError:
            messagebox.showerror("Error", "Enter a valid integer.")
            return
        product_id = self.product_map[self.product_var.get()]
        db.adjust_stock(product_id, delta)
        db.check_and_create_alerts()
        self.app.refresh_current()
        self.destroy()


class NewOrderDialog(BaseDialog):
    def __init__(self, parent, app):
        super().__init__(parent, app, "New Order")
        self.geometry("600x580")
        self.items = []
        self._build()

    def _build(self):
        clients = db.get_all_clients()
        self.client_map = {c["name"]: c["id"] for c in clients}
        products = db.get_all_products()
        self.product_map = {f"{p['name']} ({p['sku']})": dict(p) for p in products}

        self.order_code = self._field(self, "Order Code *", f"ORD-{datetime.now().strftime('%Y-%m%d-%H%M')}", 540)
        self.client_var = ctk.StringVar()
        ctk.CTkLabel(self, text="Client *", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=24, pady=(8, 0))
        ctk.CTkComboBox(self, values=list(self.client_map.keys()),
                        variable=self.client_var, width=540).pack(padx=24)

        self.status_var = ctk.StringVar(value="Pending")
        ctk.CTkLabel(self, text="Status", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=24, pady=(8, 0))
        ctk.CTkComboBox(self, values=["Pending", "Processing", "Delivered", "Cancelled"],
                        variable=self.status_var, width=200).pack(padx=24, anchor="w")

        # Items adder
        ctk.CTkLabel(self, text="Add Items",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#95a5a6").pack(padx=24, pady=(12, 0), anchor="w")

        item_row = ctk.CTkFrame(self, fg_color="transparent")
        item_row.pack(fill="x", padx=24)
        self.item_product = ctk.StringVar()
        ctk.CTkComboBox(item_row, values=list(self.product_map.keys()),
                        variable=self.item_product, width=320).pack(side="left")
        self.item_qty = ctk.CTkEntry(item_row, placeholder_text="Qty", width=70)
        self.item_qty.pack(side="left", padx=4)
        ctk.CTkButton(item_row, text="Add →", width=80, height=32,
                      fg_color="#0f3460", command=self._add_item).pack(side="left")

        self.items_frame = ctk.CTkScrollableFrame(self, fg_color="#16213e",
                                                   corner_radius=8, height=100)
        self.items_frame.pack(fill="x", padx=24, pady=4)

        self.notes = self._field(self, "Notes", "", 540)
        self._buttons(self._save)

    def _add_item(self):
        p_key = self.item_product.get()
        try:
            qty = int(self.item_qty.get())
        except ValueError:
            messagebox.showerror("Error", "Enter a valid quantity.")
            return
        if not p_key or p_key not in self.product_map:
            messagebox.showerror("Error", "Select a product.")
            return
        p = self.product_map[p_key]
        self.items.append({
            "product_id": p["id"], "quantity": qty, "unit_price": p["unit_price"]
        })
        self._refresh_items()

    def _refresh_items(self):
        for w in self.items_frame.winfo_children():
            w.destroy()
        products = {p["id"]: p for p in db.get_all_products()}
        for item in self.items:
            p = products[item["product_id"]]
            ctk.CTkLabel(self.items_frame,
                         text=f"{p['name']}  ×{item['quantity']}  @ ₹{item['unit_price']:,.2f}",
                         font=ctk.CTkFont(size=11)).pack(anchor="w", padx=8, pady=2)

    def _save(self):
        code = self.order_code.get().strip()
        client_name = self.client_var.get()
        if not code or not client_name or not self.items:
            messagebox.showerror("Error", "Order code, client, and at least one item are required.")
            return
        client_id = self.client_map.get(client_name)
        if not client_id:
            messagebox.showerror("Error", "Invalid client selected.")
            return
        try:
            db.add_order(code, client_id, self.items, self.status_var.get(), self.notes.get())
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return
        self.app.refresh_current()
        self.destroy()


# ── Payments Received Page ────────────────────────────────────────────────────

class PaymentsPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._from = ""
        self._to   = ""

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._header("Payments Received", "All payments collected from clients")

        # ── KPI tiles ────────────────────────────────────────────────────────
        from datetime import date as _date
        today = _date.today()
        all_pmts   = db.get_all_payments()
        t_total    = sum(p["amount"] for p in all_pmts)
        t_month    = sum(p["amount"] for p in all_pmts if p["payment_date"] >= today.replace(day=1).isoformat())
        t_today    = sum(p["amount"] for p in all_pmts if p["payment_date"] == today.isoformat())

        sc = ctk.CTkFrame(self, fg_color="transparent")
        sc.pack(fill="x", padx=24, pady=(0, 10))
        for i in range(4):
            sc.columnconfigure(i, weight=1)
        for i, (title, val, color) in enumerate([
            ("Total Collected",  f"₹ {t_total:,.0f}",  "#2ecc71"),
            ("This Month",       f"₹ {t_month:,.0f}",  "#3498db"),
            ("Today",            f"₹ {t_today:,.0f}",  "#f39c12"),
            ("Transactions",     str(len(all_pmts)),    "#9b59b6"),
        ]):
            self._card(sc, title, val, color).grid(row=0, column=i, padx=6, sticky="ew")

        # ── Toolbar ───────────────────────────────────────────────────────────
        tb = ctk.CTkFrame(self, fg_color="transparent")
        tb.pack(fill="x", padx=24, pady=(0, 8))

        ctk.CTkLabel(tb, text="From:", text_color="#aaa",
                     font=ctk.CTkFont(size=11)).pack(side="left")
        self._from_var = ctk.StringVar(value=self._from)
        ctk.CTkEntry(tb, textvariable=self._from_var, width=112,
                     placeholder_text="YYYY-MM-DD").pack(side="left", padx=(4, 8))
        ctk.CTkLabel(tb, text="To:", text_color="#aaa",
                     font=ctk.CTkFont(size=11)).pack(side="left")
        self._to_var = ctk.StringVar(value=self._to)
        ctk.CTkEntry(tb, textvariable=self._to_var, width=112,
                     placeholder_text="YYYY-MM-DD").pack(side="left", padx=(4, 8))
        ctk.CTkButton(tb, text="🔍 Filter", width=80, height=30,
                      fg_color="#0f3460", hover_color="#16213e",
                      command=self._apply_filter).pack(side="left", padx=(0, 6))
        ctk.CTkButton(tb, text="✕ Clear", width=70, height=30,
                      fg_color="transparent", hover_color="#16213e",
                      border_width=1, border_color="#555",
                      command=self._clear_filter).pack(side="left")

        ctk.CTkButton(tb, text="📊 Excel", width=80, height=30,
                      fg_color="#16213e", hover_color="#0f3460",
                      command=self._export_excel).pack(side="right", padx=3)
        ctk.CTkButton(tb, text="📄 PDF", width=70, height=30,
                      fg_color="#16213e", hover_color="#0f3460",
                      command=self._export_pdf).pack(side="right", padx=3)
        ctk.CTkButton(tb, text="📋 CSV", width=70, height=30,
                      fg_color="#16213e", hover_color="#0f3460",
                      command=self._export_csv).pack(side="right", padx=3)

        # ── Table ─────────────────────────────────────────────────────────────
        pmts = db.get_all_payments(self._from or None, self._to or None)

        tbl = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=12)
        tbl.pack(fill="both", expand=True, padx=24, pady=(0, 24))

        COLS = [("Date", 110), ("Invoice #", 110), ("Client", 185),
                ("Amount (₹)", 110), ("Mode", 110), ("Reference", 170), ("", 100)]
        hdr = ctk.CTkFrame(tbl, fg_color="#0f3460", corner_radius=0)
        hdr.pack(fill="x")
        for col, w in COLS:
            ctk.CTkLabel(hdr, text=col, font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#bdc3c7", width=w, anchor="w"
                         ).pack(side="left", padx=10, pady=8)

        body = ctk.CTkScrollableFrame(tbl, fg_color="transparent")
        body.pack(fill="both", expand=True)

        if not pmts:
            ctk.CTkLabel(body, text="No payments found.",
                         text_color="#7f8c8d",
                         font=ctk.CTkFont(size=13)).pack(pady=40)
            return

        for i, p in enumerate(pmts):
            row_bg = "#1a1a2e" if i % 2 == 0 else "#0f1626"
            row = ctk.CTkFrame(body, fg_color=row_bg, corner_radius=0, height=40)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            narr = p.get("narration", "")
            ref_display = narr.split("– Ref: ", 1)[1] if "– Ref: " in narr else "—"

            for val, w in [
                (p.get("payment_date", ""), 110),
                (p.get("invoice_number", "—"), 110),
                (p.get("client_name", "—"), 185),
                (f"₹ {p['amount']:,.2f}", 110),
                (p.get("payment_mode", "—"), 110),
                (ref_display, 170),
            ]:
                ctk.CTkLabel(row, text=str(val), font=ctk.CTkFont(size=11),
                             text_color="#ecf0f1", width=w, anchor="w"
                             ).pack(side="left", padx=10)

            ctk.CTkButton(
                row, text="🧾 Receipt", width=90, height=28,
                fg_color="#1a3a5c", hover_color="#2355c2",
                font=ctk.CTkFont(size=11),
                command=lambda pp=dict(p): self._print_receipt(pp),
            ).pack(side="left", padx=4)

    # ── actions ───────────────────────────────────────────────────────────────

    def _apply_filter(self):
        self._from = self._from_var.get().strip()
        self._to   = self._to_var.get().strip()
        self.refresh()

    def _clear_filter(self):
        self._from = ""
        self._to   = ""
        self.refresh()

    def _print_receipt(self, p):
        inv_id = p.get("invoice_id")
        if not inv_id:
            messagebox.showerror("Error", "Cannot link this payment to an invoice.")
            return
        inv, _items, firm = db.get_invoice_full(inv_id)
        inv  = dict(inv)
        firm = dict(firm) if firm else {}
        fp = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile=f"Receipt_{p['invoice_number']}_{p['payment_date']}.pdf",
        )
        if not fp:
            return
        try:
            from report_export import export_payment_receipt_pdf
            export_payment_receipt_pdf(p, inv, firm, fp)
            messagebox.showinfo("Done", f"Receipt saved:\n{fp}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def _export_pdf(self):
        pmts = db.get_all_payments(self._from or None, self._to or None)
        if not pmts:
            messagebox.showinfo("No Data", "No payments to export.")
            return
        fp = filedialog.asksaveasfilename(defaultextension=".pdf",
                                          filetypes=[("PDF files", "*.pdf")],
                                          initialfile="Payments_Received.pdf")
        if not fp:
            return
        try:
            from report_export import export_payments_pdf
            export_payments_pdf(pmts, dict(db.get_firm_settings()), fp)
            messagebox.showinfo("Done", f"PDF saved:\n{fp}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def _export_excel(self):
        pmts = db.get_all_payments(self._from or None, self._to or None)
        if not pmts:
            messagebox.showinfo("No Data", "No payments to export.")
            return
        fp = filedialog.asksaveasfilename(defaultextension=".xlsx",
                                          filetypes=[("Excel files", "*.xlsx")],
                                          initialfile="Payments_Received.xlsx")
        if not fp:
            return
        try:
            from report_export import export_payments_excel
            export_payments_excel(pmts, dict(db.get_firm_settings()), fp)
            messagebox.showinfo("Done", f"Excel saved:\n{fp}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def _export_csv(self):
        pmts = db.get_all_payments(self._from or None, self._to or None)
        if not pmts:
            messagebox.showinfo("No Data", "No payments to export.")
            return
        fp = filedialog.asksaveasfilename(defaultextension=".csv",
                                          filetypes=[("CSV files", "*.csv")],
                                          initialfile="Payments_Received.csv")
        if not fp:
            return
        try:
            from report_export import export_payments_csv
            export_payments_csv(pmts, fp)
            messagebox.showinfo("Done", f"CSV saved:\n{fp}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))


# ── Invoices Page ─────────────────────────────────────────────────────────────

class InvoicesPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._filter = "All"
        self._search = ""

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._header("Invoices", "Create and manage GST tax invoices")

        # ── Stat cards ────────────────────────────────────────────────────────
        stats = db.get_dashboard_stats()
        outstanding = stats["total_invoiced"] - stats["total_paid"]
        overdue_inv = db.get_overdue_invoices()
        overdue_amt = sum(i["grand_total"] for i in overdue_inv)
        overdue_clr = "#e74c3c" if overdue_inv else "#2ecc71"

        sc = ctk.CTkFrame(self, fg_color="transparent")
        sc.pack(fill="x", padx=24, pady=(0, 10))
        for i in range(4):
            sc.columnconfigure(i, weight=1)
        for i, (title, val, color) in enumerate([
            ("Total Invoiced",   f"₹ {stats['total_invoiced']:,.0f}",  "#3498db"),
            ("Collected / Paid", f"₹ {stats['total_paid']:,.0f}",      "#2ecc71"),
            ("Outstanding",      f"₹ {outstanding:,.0f}",              "#f39c12"),
            ("Overdue",          f"₹ {overdue_amt:,.0f}  ({len(overdue_inv)})", overdue_clr),
        ]):
            c = self._card(sc, title, val, color)
            c.grid(row=0, column=i, padx=6, sticky="ew")

        # ── Toolbar: new invoice + search + filter + export ───────────────────
        tb = ctk.CTkFrame(self, fg_color="transparent")
        tb.pack(fill="x", padx=24, pady=(0, 8))

        ctk.CTkButton(tb, text="+ New Invoice", fg_color="#2ecc71",
                      hover_color="#27ae60", text_color="#000",
                      command=self._new_invoice).pack(side="left")

        ctk.CTkButton(tb, text="🔁 Recurring", width=110, height=32,
                      fg_color="#1a3a5c", hover_color="#2355c2",
                      font=ctk.CTkFont(size=12),
                      command=lambda: RecurringInvoicesDialog(self, self.app)
                      ).pack(side="left", padx=(8, 0))

        # Search entry
        self._search_var = ctk.StringVar(value=self._search)
        srch = ctk.CTkEntry(tb, textvariable=self._search_var,
                            placeholder_text="🔍  Search invoice # or client…",
                            width=220, height=30)
        srch.pack(side="left", padx=(12, 4))
        srch.bind("<KeyRelease>", lambda e: self._on_search())

        ctk.CTkButton(tb, text="✕", width=28, height=28, fg_color="transparent",
                      hover_color="#16213e",
                      command=self._clear_search).pack(side="left", padx=(0, 8))

        for status in ["All", "Draft", "Sent", "Partially Paid", "Paid", "Cancelled"]:
            active = status == self._filter
            ctk.CTkButton(
                tb, text=status, width=76, height=30,
                fg_color="#0f3460" if active else "transparent",
                hover_color="#16213e", border_width=1, border_color="#0f3460",
                font=ctk.CTkFont(size=11),
                command=lambda s=status: self._set_filter(s),
            ).pack(side="left", padx=3)

        # Export buttons on the right
        ctk.CTkButton(tb, text="📊 Excel", width=80, height=30,
                      fg_color="#16213e", hover_color="#0f3460",
                      font=ctk.CTkFont(size=11),
                      command=self._export_excel).pack(side="right", padx=3)
        ctk.CTkButton(tb, text="📄 PDF", width=70, height=30,
                      fg_color="#16213e", hover_color="#0f3460",
                      font=ctk.CTkFont(size=11),
                      command=self._export_pdf).pack(side="right", padx=3)

        # ── Table ─────────────────────────────────────────────────────────────
        tbl = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=12)
        tbl.pack(fill="both", expand=True, padx=24, pady=(0, 24))

        hdr = ctk.CTkFrame(tbl, fg_color="#0f3460", corner_radius=6)
        hdr.pack(fill="x", padx=12, pady=(12, 2))
        for col, w in [("Invoice No.", 140), ("Client", 180), ("Date", 95),
                       ("Due Date", 95), ("Taxable", 100), ("Tax", 80),
                       ("Total", 110), ("Status", 90), ("Actions", 200)]:
            ctk.CTkLabel(hdr, text=col, width=w,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#95a5a6").pack(side="left", padx=6, pady=6)

        scroll = ctk.CTkScrollableFrame(tbl, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        invoices = [dict(r) for r in db.get_all_invoices()]
        if self._filter != "All":
            invoices = [i for i in invoices if i["status"] == self._filter]
        q = self._search_var.get().strip().lower() if hasattr(self, "_search_var") else ""
        if q:
            invoices = [i for i in invoices
                        if q in i["invoice_number"].lower()
                        or q in (i.get("client_name") or "").lower()]

        today_s = datetime.now().strftime("%Y-%m-%d")
        if not invoices:
            ctk.CTkLabel(scroll, text="No invoices found.",
                         text_color="#95a5a6").pack(pady=30)
        else:
            sc_map = {"Draft": "#95a5a6", "Sent": "#3498db",
                      "Paid": "#2ecc71", "Cancelled": "#e74c3c",
                      "Partially Paid": "#9b59b6"}
            for inv in invoices:
                tax = inv["cgst_total"] + inv["sgst_total"] + inv["igst_total"]
                sc_color = sc_map.get(inv["status"], "#95a5a6")
                due = inv.get("due_date") or ""
                is_overdue = (due and due < today_s
                              and inv["status"] not in ("Paid", "Cancelled", "Partially Paid"))
                row_bg = "#2c0f0f" if is_overdue else "#16213e"
                row = ctk.CTkFrame(scroll, fg_color=row_bg, corner_radius=6)
                row.pack(fill="x", pady=2)
                for val, w, color in [
                    (inv["invoice_number"], 140, "#3498db"),
                    ((inv.get("client_name") or "—")[:22], 180, "#ecf0f1"),
                    (inv["invoice_date"],   95,  "#95a5a6"),
                    (due or "—",            95,  "#e74c3c" if is_overdue else "#95a5a6"),
                    (f"₹{inv['subtotal']:,.0f}", 100, "#ecf0f1"),
                    (f"₹{tax:,.0f}",             80,  "#f39c12"),
                    (f"₹{inv['grand_total']:,.0f}", 110, "#2ecc71"),
                ]:
                    ctk.CTkLabel(row, text=str(val), width=w,
                                 font=ctk.CTkFont(size=11),
                                 text_color=color).pack(side="left", padx=5, pady=6)
                # Status badge
                badge_text = ("OVERDUE" if is_overdue else inv["status"])
                badge_color = "#e74c3c" if is_overdue else sc_color
                ctk.CTkLabel(row, text=badge_text, width=90,
                             font=ctk.CTkFont(size=10, weight="bold"),
                             text_color=badge_color).pack(side="left", padx=4)
                # Action buttons
                ctk.CTkButton(row, text="PDF", width=46, height=26,
                              fg_color="#0f3460", hover_color="#1a4a8a",
                              font=ctk.CTkFont(size=10),
                              command=lambda iid=inv["id"]: self._gen_pdf(iid)
                              ).pack(side="left", padx=2)
                ctk.CTkButton(row, text="📱 WA", width=52, height=26,
                              fg_color="#075e54", hover_color="#128c7e",
                              font=ctk.CTkFont(size=10),
                              command=lambda iid=inv["id"]: self._whatsapp_share(iid)
                              ).pack(side="left", padx=2)
                ctk.CTkButton(row, text="✉ Email", width=58, height=26,
                              fg_color="#6c3483", hover_color="#7d3c98",
                              font=ctk.CTkFont(size=10),
                              command=lambda iid=inv["id"]: self._email_share(iid)
                              ).pack(side="left", padx=2)
                if inv["status"] == "Draft":
                    ctk.CTkButton(row, text="✉ Send", width=58, height=26,
                                  fg_color="#1a3a5c", hover_color="#2355c2",
                                  font=ctk.CTkFont(size=10),
                                  command=lambda iid=inv["id"]: self._mark_sent(iid)
                                  ).pack(side="left", padx=2)
                if inv["status"] in ("Draft", "Sent", "Partially Paid"):
                    ctk.CTkButton(row, text="💰 Pay", width=60, height=26,
                                  fg_color="#1a5c1a", hover_color="#27ae60",
                                  font=ctk.CTkFont(size=10),
                                  command=lambda iid=inv["id"], iv=inv: PaymentDialog(self, self.app, iid, iv)
                                  ).pack(side="left", padx=2)
                # IRN button: green if generated, grey otherwise
                irn_color = "#1a7a1a" if inv.get("einvoice_status") == "Generated" else "#2c3e50"
                irn_text  = "✓ IRN" if inv.get("einvoice_status") == "Generated" else "IRN"
                ctk.CTkButton(row, text=irn_text, width=46, height=26,
                              fg_color=irn_color, hover_color="#16a085",
                              font=ctk.CTkFont(size=10),
                              command=lambda iid=inv["id"]: EInvoiceDialog(self, self.app, iid)
                              ).pack(side="left", padx=2)
                # EWB button: green if generated
                ewb_color = "#1a5c7a" if inv.get("ewb_status") == "Generated" else "#2c3e50"
                ewb_text  = "✓ EWB" if inv.get("ewb_status") == "Generated" else "🚚 EWB"
                ctk.CTkButton(row, text=ewb_text, width=52, height=26,
                              fg_color=ewb_color, hover_color="#2980b9",
                              font=ctk.CTkFont(size=10),
                              command=lambda iid=inv["id"]: EWayBillDialog(self, self.app, iid)
                              ).pack(side="left", padx=2)
                ctk.CTkButton(row, text="Del", width=38, height=26,
                              fg_color="#7f1f1f", hover_color="#c0392b",
                              font=ctk.CTkFont(size=10),
                              command=lambda iid=inv["id"], inum=inv["invoice_number"]: self._delete(iid, inum)
                              ).pack(side="left", padx=2)

    def _on_search(self):
        self._search = self._search_var.get()
        self.refresh()

    def _clear_search(self):
        self._search = ""
        self.refresh()

    def _set_filter(self, status):
        self._filter = status
        self.refresh()

    def _new_invoice(self):
        InvoiceDialog(self, self.app)

    def _mark_sent(self, invoice_id):
        db.update_invoice_status(invoice_id, "Sent")
        self.refresh()

    def _gen_pdf(self, invoice_id):
        inv, items, firm = db.get_invoice_full(invoice_id)
        inv_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Invoices")
        os.makedirs(inv_dir, exist_ok=True)
        out = os.path.join(inv_dir, f"{inv['invoice_number']}.pdf")
        try:
            from invoice_pdf import generate_invoice_pdf
            generate_invoice_pdf(dict(inv), [dict(i) for i in items], dict(firm), out)
            if sys.platform == "win32":
                os.startfile(out)
            else:
                subprocess.run(["xdg-open", out])
            messagebox.showinfo("PDF Ready", f"Invoice saved to:\n{out}")
        except Exception as e:
            messagebox.showerror("PDF Error", f"Could not generate PDF:\n{e}")

    def _whatsapp_share(self, invoice_id):
        WhatsAppShareDialog(self, invoice_id)

    def _email_share(self, invoice_id):
        EmailShareDialog(self, invoice_id)

    def _export_pdf(self):
        invoices = [dict(r) for r in db.get_all_invoices()]
        if self._filter != "All":
            invoices = [i for i in invoices if i["status"] == self._filter]
        firm = db.get_firm_settings()
        self._run_export(rex.export_invoice_list_pdf, "Invoice_List.pdf",
                         invoices, dict(firm) if firm else {})

    def _export_excel(self):
        invoices = [dict(r) for r in db.get_all_invoices()]
        if self._filter != "All":
            invoices = [i for i in invoices if i["status"] == self._filter]
        firm = db.get_firm_settings()
        self._run_export(rex.export_invoice_list_excel, "Invoice_List.xlsx",
                         invoices, dict(firm) if firm else {})

    def _run_export(self, export_fn, default_name, *args):
        path = filedialog.asksaveasfilename(
            defaultextension=os.path.splitext(default_name)[1],
            initialfile=default_name,
            filetypes=[("All files", "*.*")],
        )
        if not path:
            return
        try:
            export_fn(*args, path)
            messagebox.showinfo("Exported", f"Saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def _delete(self, invoice_id, invoice_number):
        if messagebox.askyesno("Confirm", f"Delete invoice {invoice_number}?"):
            db.delete_invoice(invoice_id)
            self.refresh()


# ── Recurring Invoices Dialogs ────────────────────────────────────────────────

class RecurringInvoicesDialog(ctk.CTkToplevel):
    """List all recurring invoice templates; create / toggle / delete."""
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("Recurring Invoices")
        self.geometry("860x540")
        self.resizable(True, True)
        self.grab_set()
        self.configure(fg_color="#0d1117")
        self._build()

    def _build(self):
        for w in self.winfo_children():
            w.destroy()

        # Header
        hdr = ctk.CTkFrame(self, fg_color="#0f3460", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="🔁  Recurring Invoices",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="#ecf0f1").pack(side="left", padx=16, pady=10)
        ctk.CTkButton(hdr, text="+ New Template", width=130,
                      fg_color="#2ecc71", hover_color="#27ae60", text_color="#000",
                      command=self._new_template).pack(side="right", padx=12, pady=8)

        # Column headers
        hdr2 = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=0)
        hdr2.pack(fill="x", padx=0, pady=(0, 0))
        for txt, w in [("Client", 200), ("Frequency", 100), ("Next Due", 110),
                       ("Last Generated", 120), ("Status", 80), ("Actions", 180)]:
            ctk.CTkLabel(hdr2, text=txt, width=w, anchor="w",
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#bdc3c7").pack(side="left", padx=8, pady=6)

        # Scrollable list
        scroll = ctk.CTkScrollableFrame(self, fg_color="#0d1117")
        scroll.pack(fill="both", expand=True, padx=0)

        rows = db.get_recurring_invoices()
        if not rows:
            ctk.CTkLabel(scroll, text="No recurring invoice templates yet. Click '+ New Template' to create one.",
                         text_color="#95a5a6", wraplength=600).pack(pady=40)
        else:
            for i, r in enumerate(rows):
                r = dict(r)
                bg = "#0f1b2d" if i % 2 == 0 else "#16213e"
                row = ctk.CTkFrame(scroll, fg_color=bg, corner_radius=0)
                row.pack(fill="x")

                is_active = bool(r["is_active"])
                status_clr = "#2ecc71" if is_active else "#95a5a6"
                status_txt = "Active" if is_active else "Paused"

                vals = [
                    (r["client_name"], 200, "#ecf0f1"),
                    (r["frequency"].capitalize(), 100, "#3498db"),
                    (r["next_due"], 110, "#f39c12" if r["next_due"] <= __import__("datetime").date.today().strftime("%Y-%m-%d") else "#ecf0f1"),
                    (r["last_generated"] or "—", 120, "#7f8c8d"),
                    (status_txt, 80, status_clr),
                ]
                for txt, w, clr in vals:
                    ctk.CTkLabel(row, text=str(txt), width=w, anchor="w",
                                 font=ctk.CTkFont(size=11),
                                 text_color=clr).pack(side="left", padx=8, pady=6)

                btn_frame = ctk.CTkFrame(row, fg_color="transparent")
                btn_frame.pack(side="left", padx=4)

                rid = r["id"]
                ctk.CTkButton(btn_frame, text="⏸ Pause" if is_active else "▶ Resume",
                              width=80, height=24, font=ctk.CTkFont(size=10),
                              fg_color="#2c3e50", hover_color="#3d5166",
                              command=lambda rid=rid, ia=is_active: self._toggle(rid, not ia)
                              ).pack(side="left", padx=2)
                ctk.CTkButton(btn_frame, text="🗑 Delete",
                              width=70, height=24, font=ctk.CTkFont(size=10),
                              fg_color="#4a1010", hover_color="#7b1c1c",
                              command=lambda rid=rid: self._delete(rid)
                              ).pack(side="left", padx=2)

        # Close button
        foot = ctk.CTkFrame(self, fg_color="#0f3460", corner_radius=0)
        foot.pack(fill="x", side="bottom")
        ctk.CTkButton(foot, text="Close", width=80,
                      fg_color="#2c3e50", hover_color="#3d5166",
                      command=self.destroy).pack(side="right", padx=16, pady=8)

    def _new_template(self):
        RecurringInvoiceFormDialog(self, self.app, on_save=self._build)

    def _toggle(self, rid, new_state):
        db.toggle_recurring_invoice(rid, new_state)
        self._build()

    def _delete(self, rid):
        import tkinter.messagebox as mb
        if mb.askyesno("Delete Template", "Delete this recurring invoice template?", parent=self):
            db.delete_recurring_invoice(rid)
            self._build()


class RecurringInvoiceFormDialog(ctk.CTkToplevel):
    """Create a new recurring invoice template."""
    def __init__(self, parent, app, on_save=None):
        super().__init__(parent)
        self.app = app
        self._on_save = on_save
        self.title("New Recurring Invoice Template")
        self.geometry("600x620")
        self.resizable(False, False)
        self.grab_set()
        self.configure(fg_color="#0d1117")
        self._items = []
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="🔁  New Recurring Invoice Template",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#ecf0f1").pack(padx=20, pady=(16, 4), anchor="w")

        form = ctk.CTkScrollableFrame(self, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=20)

        def row(label, widget_fn):
            fr = ctk.CTkFrame(form, fg_color="transparent")
            fr.pack(fill="x", pady=4)
            ctk.CTkLabel(fr, text=label, width=130, anchor="w",
                         font=ctk.CTkFont(size=11), text_color="#bdc3c7").pack(side="left")
            w = widget_fn(fr)
            if w:
                w.pack(side="left", fill="x", expand=True)
            return w

        # Client dropdown
        clients = db.get_all_clients()
        client_names = [c["name"] for c in clients]
        self._client_map = {c["name"]: c["id"] for c in clients}
        self._client_var = ctk.StringVar(value=client_names[0] if client_names else "")
        row("Client *", lambda p: ctk.CTkOptionMenu(p, variable=self._client_var,
                                                     values=client_names, width=250))

        # Frequency
        self._freq_var = ctk.StringVar(value="monthly")
        row("Frequency *", lambda p: ctk.CTkOptionMenu(p, variable=self._freq_var,
                                                        values=["weekly","monthly","quarterly","yearly"],
                                                        width=160))

        # First due date
        from datetime import date
        self._due_var = ctk.StringVar(value=date.today().strftime("%Y-%m-%d"))
        row("First Due Date *", lambda p: ctk.CTkEntry(p, textvariable=self._due_var, width=140,
                                                        placeholder_text="YYYY-MM-DD"))

        # Notes
        self._notes_var = ctk.StringVar(value="")
        row("Notes", lambda p: ctk.CTkEntry(p, textvariable=self._notes_var, width=300))

        # Items section
        ctk.CTkLabel(form, text="Line Items", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#bdc3c7").pack(anchor="w", pady=(12, 4))

        self._items_frame = ctk.CTkFrame(form, fg_color="#16213e", corner_radius=6)
        self._items_frame.pack(fill="x")
        self._refresh_items()

        ctk.CTkButton(form, text="+ Add Item", width=110, height=28,
                      fg_color="#16213e", hover_color="#0f3460",
                      command=self._add_item).pack(anchor="w", pady=(6, 0))

        # Save button
        btn_bar = ctk.CTkFrame(self, fg_color="transparent")
        btn_bar.pack(fill="x", padx=20, pady=12)
        ctk.CTkButton(btn_bar, text="Cancel", width=90,
                      fg_color="#2c3e50", hover_color="#3d5166",
                      command=self.destroy).pack(side="right", padx=4)
        ctk.CTkButton(btn_bar, text="💾 Save Template", width=140,
                      fg_color="#1a5c1a", hover_color="#27ae60",
                      command=self._save).pack(side="right", padx=4)

    def _refresh_items(self):
        for w in self._items_frame.winfo_children():
            w.destroy()
        if not self._items:
            ctk.CTkLabel(self._items_frame, text="No items yet — click '+ Add Item'",
                         text_color="#7f8c8d", font=ctk.CTkFont(size=10)).pack(pady=8)
            return
        for idx, it in enumerate(self._items):
            r = ctk.CTkFrame(self._items_frame, fg_color="transparent")
            r.pack(fill="x", padx=8, pady=3)
            ctk.CTkLabel(r, text=f"{idx+1}.", width=20, text_color="#95a5a6").pack(side="left")
            ctk.CTkEntry(r, textvariable=it["desc"], width=160,
                         placeholder_text="Description").pack(side="left", padx=3)
            ctk.CTkEntry(r, textvariable=it["qty"], width=55,
                         placeholder_text="Qty").pack(side="left", padx=3)
            ctk.CTkEntry(r, textvariable=it["price"], width=80,
                         placeholder_text="Unit Price").pack(side="left", padx=3)
            ctk.CTkEntry(r, textvariable=it["gst"], width=50,
                         placeholder_text="GST%").pack(side="left", padx=3)
            ctk.CTkButton(r, text="✕", width=24, height=24, fg_color="#4a1010",
                          hover_color="#7b1c1c",
                          command=lambda i=idx: self._remove_item(i)).pack(side="left", padx=3)

    def _add_item(self):
        self._items.append({
            "desc":  ctk.StringVar(value=""),
            "qty":   ctk.StringVar(value="1"),
            "price": ctk.StringVar(value="0"),
            "gst":   ctk.StringVar(value="18"),
        })
        self._refresh_items()

    def _remove_item(self, idx):
        self._items.pop(idx)
        self._refresh_items()

    def _save(self):
        client_name = self._client_var.get()
        if not client_name or client_name not in self._client_map:
            import tkinter.messagebox as mb
            mb.showerror("Error", "Please select a client.", parent=self)
            return
        due = self._due_var.get().strip()
        if not due:
            import tkinter.messagebox as mb
            mb.showerror("Error", "Please enter a due date (YYYY-MM-DD).", parent=self)
            return
        items = []
        for it in self._items:
            d = it["desc"].get().strip()
            if not d:
                continue
            try:
                qty = float(it["qty"].get())
                price = float(it["price"].get())
                gst = float(it["gst"].get())
            except ValueError:
                import tkinter.messagebox as mb
                mb.showerror("Error", f"Invalid number in item '{d}'.", parent=self)
                return
            items.append({"description": d, "quantity": qty, "unit_price": price, "gst_rate": gst})
        if not items:
            import tkinter.messagebox as mb
            mb.showerror("Error", "Add at least one line item.", parent=self)
            return
        db.create_recurring_invoice(
            client_id=self._client_map[client_name],
            frequency=self._freq_var.get(),
            next_due=due,
            notes=self._notes_var.get().strip(),
            items=items)
        self.destroy()
        if self._on_save:
            self._on_save()


# ── Client Statement Dialog ───────────────────────────────────────────────────

class ClientStatementDialog(ctk.CTkToplevel):
    def __init__(self, parent, app, client_id, client_name):
        super().__init__(parent)
        self.app = app
        self.title(f"Statement — {client_name}")
        self.resizable(True, True)
        self.grab_set()
        self.update_idletasks()
        h = min(640, self.winfo_screenheight() - 60)
        self.geometry(f"820x{h}")
        self.configure(fg_color="#0d1117")

        rows = db.get_client_statement(client_id)
        client_info = next((dict(c) for c in db.get_all_clients() if c["id"] == client_id), {})

        # ── header ──────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="#0f3460", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text=f"📄  Account Statement  —  {client_name}",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="#ecf0f1").pack(side="left", padx=16, pady=10)
        from datetime import datetime as _dt
        ctk.CTkLabel(hdr, text=f"As of {_dt.today().strftime('%d %b %Y')}",
                     font=ctk.CTkFont(size=11), text_color="#7f8c8d").pack(side="right", padx=16)

        # ── client info strip ────────────────────────────────────────
        info = ctk.CTkFrame(self, fg_color="#0f1b2d", corner_radius=0)
        info.pack(fill="x")
        for label, val in [
            ("GSTIN", client_info.get("gstin") or "—"),
            ("Phone", client_info.get("phone") or "—"),
            ("Email", client_info.get("email") or "—"),
            ("State", client_info.get("state") or "—"),
        ]:
            ctk.CTkLabel(info, text=f"{label}: ", font=ctk.CTkFont(size=10),
                         text_color="#7f8c8d").pack(side="left", padx=(12,0), pady=6)
            ctk.CTkLabel(info, text=val, font=ctk.CTkFont(size=10),
                         text_color="#bdc3c7").pack(side="left", padx=(0,12))

        # ── table ────────────────────────────────────────────────────
        tbl = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=0)
        tbl.pack(fill="both", expand=True, padx=0, pady=0)

        # column header
        cols = [("Invoice #",130),("Date",95),("Due Date",95),
                ("Amount",100),("Paid",100),("Outstanding",110),("Status",80)]
        hdr2 = ctk.CTkFrame(tbl, fg_color="#0f3460", corner_radius=0)
        hdr2.pack(fill="x", padx=0, pady=0)
        for txt, w in cols:
            ctk.CTkLabel(hdr2, text=txt, width=w, anchor="w",
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#bdc3c7").pack(side="left", padx=6, pady=6)

        scroll = ctk.CTkScrollableFrame(tbl, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=0)

        status_colors = {"Paid":"#2ecc71","Sent":"#3498db","Draft":"#95a5a6","Cancelled":"#e74c3c","Partially Paid":"#9b59b6"}
        if not rows:
            ctk.CTkLabel(scroll, text="No invoices found for this client.",
                         text_color="#95a5a6").pack(pady=30)
        else:
            for r in rows:
                bg = "#0f1b2d" if rows.index(r) % 2 == 0 else "#16213e"
                row = ctk.CTkFrame(scroll, fg_color=bg, corner_radius=0)
                row.pack(fill="x")
                sc = status_colors.get(r["status"], "#95a5a6")
                vals = [
                    (r["invoice_number"],  130, "#3498db"),
                    (r["invoice_date"],     95, "#ecf0f1"),
                    (r["due_date"] or "—",  95, "#ecf0f1"),
                    (f"₹{r['grand_total']:,.2f}", 100, "#ecf0f1"),
                    (f"₹{r['paid']:,.2f}",  100, "#2ecc71"),
                    (f"₹{r['outstanding']:,.2f}", 110,
                     "#e74c3c" if r["outstanding"] > 0 else "#2ecc71"),
                    (r["status"],           80, sc),
                ]
                for txt, w, clr in vals:
                    ctk.CTkLabel(row, text=str(txt), width=w, anchor="w",
                                 font=ctk.CTkFont(size=11),
                                 text_color=clr).pack(side="left", padx=6, pady=5)

        # ── summary footer ───────────────────────────────────────────
        total_inv  = sum(r["grand_total"] for r in rows)
        total_paid = sum(r["paid"] for r in rows)
        total_due  = sum(r["outstanding"] for r in rows)

        foot = ctk.CTkFrame(self, fg_color="#0f3460", corner_radius=0)
        foot.pack(fill="x")
        for lbl, val, clr in [
            ("Total Invoiced", f"₹{total_inv:,.2f}", "#ecf0f1"),
            ("Total Received", f"₹{total_paid:,.2f}", "#2ecc71"),
            ("Total Outstanding", f"₹{total_due:,.2f}", "#e74c3c" if total_due > 0 else "#2ecc71"),
        ]:
            fr = ctk.CTkFrame(foot, fg_color="transparent")
            fr.pack(side="left", padx=20, pady=8)
            ctk.CTkLabel(fr, text=lbl, font=ctk.CTkFont(size=10),
                         text_color="#7f8c8d").pack(anchor="w")
            ctk.CTkLabel(fr, text=val, font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=clr).pack(anchor="w")

        ctk.CTkButton(foot, text="Close", width=80,
                      fg_color="#2c3e50", hover_color="#3d5166",
                      command=self.destroy).pack(side="right", padx=16, pady=8)


# ── Tally Import Dialog ────────────────────────────────────────────────────────

class TallyImportDialog(ctk.CTkToplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("Import from Tally")
        self.resizable(True, True)
        self.grab_set()
        self.update_idletasks()
        h = min(680, self.winfo_screenheight() - 60)
        self.geometry(f"820x{h}")
        self.configure(fg_color="#0d1117")
        self._data = None  # parsed tally data

        # ── header ──────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="#0f3460", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="🔄  Import from Tally XML",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="#ecf0f1").pack(side="left", padx=16, pady=10)

        # ── file picker ─────────────────────────────────────────────
        fp = ctk.CTkFrame(self, fg_color="#0f1b2d", corner_radius=8)
        fp.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(fp, text="Tally XML File:",
                     font=ctk.CTkFont(size=11), text_color="#bdc3c7").pack(side="left", padx=10, pady=8)
        self._path_var = ctk.StringVar(value="No file selected")
        ctk.CTkLabel(fp, textvariable=self._path_var, anchor="w",
                     font=ctk.CTkFont(size=11), text_color="#7f8c8d").pack(side="left", padx=4, fill="x", expand=True)
        ctk.CTkButton(fp, text="Browse…", width=90,
                      fg_color="#1a4a8a", hover_color="#2355c2",
                      command=self._browse).pack(side="right", padx=10, pady=6)

        # ── conflict option ─────────────────────────────────────────
        opt = ctk.CTkFrame(self, fg_color="transparent")
        opt.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(opt, text="If record already exists:",
                     font=ctk.CTkFont(size=11), text_color="#bdc3c7").pack(side="left", padx=4)
        self._conflict_var = ctk.StringVar(value="skip")
        ctk.CTkRadioButton(opt, text="Skip", variable=self._conflict_var, value="skip",
                           font=ctk.CTkFont(size=11)).pack(side="left", padx=8)
        ctk.CTkRadioButton(opt, text="Update", variable=self._conflict_var, value="update",
                           font=ctk.CTkFont(size=11)).pack(side="left", padx=4)

        # ── preview tabs ─────────────────────────────────────────────
        self._tab = ctk.CTkTabview(self, fg_color="#0d1117")
        self._tab.pack(fill="both", expand=True, padx=12, pady=4)
        self._tab.add("Clients")
        self._tab.add("Products")
        self._tab.add("Invoices")
        self._tab.add("Log")

        self._client_list  = self._make_list(self._tab.tab("Clients"))
        self._product_list = self._make_list(self._tab.tab("Products"))
        self._invoice_list = self._make_list(self._tab.tab("Invoices"))
        self._log_box      = ctk.CTkTextbox(self._tab.tab("Log"),
                                            fg_color="#0f1b2d", font=ctk.CTkFont(size=10),
                                            state="disabled")
        self._log_box.pack(fill="both", expand=True, padx=4, pady=4)

        # ── bottom bar ───────────────────────────────────────────────
        bar = ctk.CTkFrame(self, fg_color="#0f1b2d", corner_radius=0)
        bar.pack(fill="x")
        self._status_lbl = ctk.CTkLabel(bar, text="Select a Tally XML file to begin.",
                                         font=ctk.CTkFont(size=11), text_color="#7f8c8d")
        self._status_lbl.pack(side="left", padx=12, pady=8)
        ctk.CTkButton(bar, text="Close", width=80,
                      fg_color="#2c3e50", hover_color="#3d5166",
                      command=self.destroy).pack(side="right", padx=10, pady=8)
        self._import_btn = ctk.CTkButton(bar, text="▶  Import All", width=120,
                                          fg_color="#27ae60", hover_color="#1e8449",
                                          state="disabled", command=self._do_import)
        self._import_btn.pack(side="right", padx=4, pady=8)

    def _make_list(self, parent):
        frame = ctk.CTkScrollableFrame(parent, fg_color="#0d1117")
        frame.pack(fill="both", expand=True)
        return frame

    def _clear_list(self, frame):
        for w in frame.winfo_children():
            w.destroy()

    def _browse(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Select Tally XML Export",
            filetypes=[("XML files", "*.xml"), ("All files", "*.*")]
        )
        if not path:
            return
        self._path_var.set(path)
        self._parse(path)

    def _parse(self, path):
        try:
            from tally_import import parse_tally_xml
            data = parse_tally_xml(path)
        except Exception as e:
            self._status_lbl.configure(text=f"Error: {e}", text_color="#e74c3c")
            return

        self._data = data
        ledgers   = data["ledgers"]
        stock     = data["stock_items"]
        vouchers  = data["vouchers"]

        # Populate Clients tab
        self._clear_list(self._client_list)
        self._add_header(self._client_list, ["Name", "GSTIN", "State", "Phone"])
        for c in ledgers:
            self._add_row(self._client_list,
                          [c["name"], c["gstin"] or "—", c["state"] or "—", c["phone"] or "—"])

        # Populate Products tab
        self._clear_list(self._product_list)
        self._add_header(self._product_list, ["Name", "Unit", "HSN", "GST %", "Rate"])
        for p in stock:
            self._add_row(self._product_list,
                          [p["name"], p["unit"], p["hsn_code"] or "—",
                           f"{p['gst_rate']}%", f"₹{p['selling_price']:,.2f}"])

        # Populate Invoices tab
        self._clear_list(self._invoice_list)
        self._add_header(self._invoice_list, ["Invoice #", "Date", "Party", "Items", "Total"])
        for v in vouchers:
            self._add_row(self._invoice_list,
                          [v["invoice_number"], v["invoice_date"],
                           v["party_name"], str(len(v["items"])),
                           f"₹{v['grand_total']:,.2f}"])

        self._status_lbl.configure(
            text=f"Found: {len(ledgers)} clients · {len(stock)} products · {len(vouchers)} invoices",
            text_color="#27ae60"
        )
        state = "normal" if (ledgers or stock or vouchers) else "disabled"
        self._import_btn.configure(state=state)

    def _add_header(self, frame, cols):
        hdr = ctk.CTkFrame(frame, fg_color="#1a3a5c", corner_radius=4)
        hdr.pack(fill="x", pady=(0, 2))
        for col in cols:
            ctk.CTkLabel(hdr, text=col, anchor="w",
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#bdc3c7").pack(side="left", padx=8, pady=4, expand=True, fill="x")

    def _add_row(self, frame, vals):
        row = ctk.CTkFrame(frame, fg_color="#0f1b2d", corner_radius=4)
        row.pack(fill="x", pady=1)
        for v in vals:
            ctk.CTkLabel(row, text=str(v), anchor="w",
                         font=ctk.CTkFont(size=10),
                         text_color="#ecf0f1").pack(side="left", padx=8, pady=3, expand=True, fill="x")

    def _log(self, msg):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.configure(state="disabled")
        self._log_box.see("end")

    def _do_import(self):
        if not self._data:
            return
        self._import_btn.configure(state="disabled", text="Importing…")
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")
        self._tab.set("Log")

        conflict = self._conflict_var.get()
        counts = {"clients": 0, "products": 0, "invoices": 0, "skipped": 0, "errors": 0}

        # ── existing lookup maps ─────────────────────────────────────
        existing_clients  = {c["name"].lower(): dict(c) for c in db.get_all_clients()}
        existing_products = {p["name"].lower(): dict(p) for p in db.get_all_products()}
        existing_invoices = {
            str(inv["invoice_number"]).lower()
            for inv in db.get_all_invoices()
        }

        # ── Import clients ───────────────────────────────────────────
        for c in self._data["ledgers"]:
            name = c["name"]
            key  = name.lower()
            try:
                if key in existing_clients:
                    if conflict == "update":
                        ec = existing_clients[key]
                        db.update_client(ec["id"], name, c["email"], c["phone"],
                                         c["address"], c["gstin"], c["state"])
                        self._log(f"[Updated] Client: {name}")
                        counts["clients"] += 1
                    else:
                        self._log(f"[Skipped] Client exists: {name}")
                        counts["skipped"] += 1
                else:
                    db.add_client(name, c["email"], c["phone"],
                                  c["address"], c["gstin"], c["state"])
                    existing_clients[key] = {"name": name}
                    self._log(f"[Added] Client: {name}")
                    counts["clients"] += 1
            except Exception as e:
                self._log(f"[Error] Client {name}: {e}")
                counts["errors"] += 1

        # ── Import products ──────────────────────────────────────────
        import re
        for p in self._data["stock_items"]:
            name = p["name"]
            key  = name.lower()
            # Auto-generate SKU from name
            sku = re.sub(r"[^A-Z0-9]", "", name.upper())[:10] or "SKU"
            try:
                if key in existing_products:
                    if conflict == "update":
                        ep = existing_products[key]
                        db.update_product(ep["id"], name, ep.get("sku", sku),
                                          ep.get("description", ""), p["selling_price"],
                                          ep.get("stock_quantity", 0),
                                          ep.get("low_stock_threshold", 5),
                                          p["unit"], p["hsn_code"], p["gst_rate"])
                        self._log(f"[Updated] Product: {name}")
                        counts["products"] += 1
                    else:
                        self._log(f"[Skipped] Product exists: {name}")
                        counts["skipped"] += 1
                else:
                    db.add_product(name, sku, "", p["selling_price"], 0, 5,
                                   p["unit"], p["hsn_code"], p["gst_rate"])
                    existing_products[key] = {"name": name}
                    self._log(f"[Added] Product: {name}")
                    counts["products"] += 1
            except Exception as e:
                self._log(f"[Error] Product {name}: {e}")
                counts["errors"] += 1

        # Refresh client map after import
        existing_clients = {c["name"].lower(): dict(c) for c in db.get_all_clients()}

        # ── Import invoices ──────────────────────────────────────────
        for v in self._data["vouchers"]:
            inv_no = v["invoice_number"]
            if inv_no.lower() in existing_invoices:
                self._log(f"[Skipped] Invoice exists: {inv_no}")
                counts["skipped"] += 1
                continue

            party_key = v["party_name"].lower()
            client = existing_clients.get(party_key)
            if not client:
                # Auto-create minimal client
                try:
                    db.add_client(v["party_name"])
                    existing_clients = {c["name"].lower(): dict(c) for c in db.get_all_clients()}
                    client = existing_clients.get(party_key)
                except Exception:
                    pass

            if not client:
                self._log(f"[Error] Invoice {inv_no}: client '{v['party_name']}' not found")
                counts["errors"] += 1
                continue

            if not v["items"]:
                self._log(f"[Skipped] Invoice {inv_no}: no line items")
                counts["skipped"] += 1
                continue

            try:
                from datetime import datetime, timedelta
                inv_date = v["invoice_date"] or datetime.today().strftime("%Y-%m-%d")
                try:
                    due_date = (datetime.strptime(inv_date, "%Y-%m-%d") +
                                timedelta(days=30)).strftime("%Y-%m-%d")
                except ValueError:
                    due_date = inv_date

                db.create_invoice(
                    invoice_number=inv_no,
                    client_id=client["id"],
                    invoice_date=inv_date,
                    due_date=due_date,
                    supply_type=v.get("supply_type", "inter"),
                    items=v["items"],
                    status="Draft",
                )
                existing_invoices.add(inv_no.lower())
                self._log(f"[Added] Invoice: {inv_no} ({v['party_name']})")
                counts["invoices"] += 1
            except Exception as e:
                self._log(f"[Error] Invoice {inv_no}: {e}")
                counts["errors"] += 1

        summary = (
            f"\n── Import complete ──\n"
            f"  Clients:  {counts['clients']} imported\n"
            f"  Products: {counts['products']} imported\n"
            f"  Invoices: {counts['invoices']} imported\n"
            f"  Skipped:  {counts['skipped']}\n"
            f"  Errors:   {counts['errors']}\n"
        )
        self._log(summary)
        self._status_lbl.configure(
            text=f"Done — {counts['clients']} clients, {counts['products']} products, {counts['invoices']} invoices imported.",
            text_color="#27ae60"
        )
        self._import_btn.configure(state="normal", text="▶  Import All")

        # Refresh whichever page is currently visible
        try:
            if self.app.current_page:
                self.app.current_page.refresh()
        except Exception:
            pass


# ── Payment Dialog ────────────────────────────────────────────────────────────

PAYMENT_MODES = ["Bank Transfer", "UPI", "NEFT / RTGS", "Cheque", "Cash", "Credit Card"]

class PaymentDialog(ctk.CTkToplevel):
    def __init__(self, parent, app, invoice_id, inv):
        super().__init__(parent)
        self.app        = app
        self.invoice_id = invoice_id
        self.inv        = inv
        self.title(f"Receive Payment – {inv['invoice_number']}")
        self.geometry("460x460")
        self.grab_set()
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Receive Payment",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#ecf0f1").pack(padx=20, pady=(16, 4), anchor="w")

        # Invoice summary banner
        banner = ctk.CTkFrame(self, fg_color="#0f3460", corner_radius=8)
        banner.pack(fill="x", padx=20, pady=(0, 10))
        inv = self.inv
        ctk.CTkLabel(banner, text=f"{inv['invoice_number']}  ·  {inv.get('client_name', '—')}",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#3498db").pack(side="left", padx=14, pady=10)
        ctk.CTkLabel(banner, text=f"₹ {inv['grand_total']:,.2f}",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#2ecc71").pack(side="right", padx=14)

        # Prior payments, if any
        prior = db.get_invoice_payments(self.invoice_id)
        if prior:
            paid_so_far = sum(p["amount"] for p in prior)
            remaining   = inv["grand_total"] - paid_so_far
            info = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=6)
            info.pack(fill="x", padx=20, pady=(0, 8))
            ctk.CTkLabel(info,
                         text=f"Already received: ₹{paid_so_far:,.2f}  |  Balance: ₹{remaining:,.2f}",
                         font=ctk.CTkFont(size=11), text_color="#f39c12"
                         ).pack(padx=12, pady=6)

        frame = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=10)
        frame.pack(fill="both", expand=True, padx=20, pady=(0, 12))

        def lbl(text, default=""):
            ctk.CTkLabel(frame, text=text, text_color="#95a5a6",
                         font=ctk.CTkFont(size=10)).pack(anchor="w", padx=16, pady=(10, 0))
            var = ctk.StringVar(value=default)
            ctk.CTkEntry(frame, textvariable=var).pack(fill="x", padx=16, pady=(2, 0))
            return var

        def combo(text, values, default=""):
            ctk.CTkLabel(frame, text=text, text_color="#95a5a6",
                         font=ctk.CTkFont(size=10)).pack(anchor="w", padx=16, pady=(10, 0))
            var = ctk.StringVar(value=default or values[0])
            ctk.CTkComboBox(frame, values=values, variable=var).pack(fill="x", padx=16, pady=(2, 0))
            return var

        today = datetime.now().strftime("%Y-%m-%d")
        _, _, outstanding = db.get_invoice_outstanding(self.invoice_id)
        default_amt = outstanding if outstanding > 0 else inv["grand_total"]
        self.pay_date  = lbl("Payment Date *", today)
        self.amount    = lbl("Amount Received (₹) *", f"{default_amt:.2f}")
        self.pay_mode  = combo("Payment Mode *", PAYMENT_MODES)
        self.reference = lbl("Reference No. (UTR / Cheque / UPI ID)")
        ctk.CTkFrame(frame, fg_color="transparent", height=4).pack()

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 20))
        ctk.CTkButton(btn_row, text="Cancel",
                      fg_color="#2c3e50", hover_color="#34495e",
                      command=self.destroy).pack(side="right")
        ctk.CTkButton(btn_row, text="Record Payment", width=140,
                      fg_color="#2ecc71", hover_color="#27ae60", text_color="#000",
                      command=self._save).pack(side="right", padx=8)

    def _save(self):
        date  = self.pay_date.get().strip()
        amt_s = self.amount.get().strip()
        mode  = self.pay_mode.get().strip()
        ref   = self.reference.get().strip()

        if not date or not amt_s:
            messagebox.showerror("Error", "Date and amount are required.")
            return
        try:
            amt = float(amt_s)
            if amt <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Enter a valid positive amount.")
            return

        try:
            db.record_payment(self.invoice_id, amt, date, mode, ref)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        full = amt >= self.inv["grand_total"]
        msg  = f"Payment of ₹{amt:,.2f} recorded."
        if full:
            msg += "\nInvoice marked as Paid."
        messagebox.showinfo("Payment Recorded", msg)
        self.app.refresh_current()
        self.destroy()


# ── Invoice View Dialog (read-only, opened from Dashboard) ─────────────────────

class InvoiceViewDialog(ctk.CTkToplevel):
    def __init__(self, parent, app, invoice_id):
        super().__init__(parent)
        self.app = app
        inv, items, firm = db.get_invoice_full(invoice_id)
        inv = dict(inv)
        items = [dict(it) for it in items]

        self.title(f"Invoice {inv.get('invoice_number','')}")
        self.resizable(True, True)
        self.grab_set()
        self.update_idletasks()
        h = min(680, self.winfo_screenheight() - 60)
        self.geometry(f"780x{h}")
        self.configure(fg_color="#0d1117")

        # ── header bar ──────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="#0f3460", corner_radius=0)
        hdr.pack(fill="x", padx=0, pady=0)
        ctk.CTkLabel(hdr, text=inv.get("invoice_number",""),
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#ecf0f1").pack(side="left", padx=16, pady=10)
        status = inv.get("status","")
        status_colors = {"Draft":"#f39c12","Sent":"#3498db","Paid":"#27ae60","Cancelled":"#e74c3c","Partially Paid":"#9b59b6"}
        sc = status_colors.get(status, "#95a5a6")
        ctk.CTkLabel(hdr, text=f"● {status}",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=sc).pack(side="left", padx=8)

        # ── scrollable body ─────────────────────────────────────────
        body = ctk.CTkScrollableFrame(self, fg_color="#0d1117")
        body.pack(fill="both", expand=True, padx=12, pady=8)

        def row2(parent, label, value):
            f = ctk.CTkFrame(parent, fg_color="transparent")
            f.pack(fill="x", pady=1)
            ctk.CTkLabel(f, text=label, width=160, anchor="w",
                         font=ctk.CTkFont(size=11), text_color="#7f8c8d").pack(side="left")
            ctk.CTkLabel(f, text=str(value or "—"), anchor="w",
                         font=ctk.CTkFont(size=11), text_color="#ecf0f1").pack(side="left")

        # dates / client
        sec1 = ctk.CTkFrame(body, fg_color="#0f1b2d", corner_radius=8)
        sec1.pack(fill="x", pady=(0,8))
        ctk.CTkLabel(sec1, text="Invoice Details",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#3498db").pack(anchor="w", padx=12, pady=(8,4))
        row2(sec1, "Date:", inv.get("invoice_date",""))
        row2(sec1, "Due Date:", inv.get("due_date",""))
        row2(sec1, "Supply Type:", inv.get("supply_type",""))
        if inv.get("notes"):
            row2(sec1, "Notes:", inv.get("notes"))
        ctk.CTkFrame(sec1, height=6, fg_color="transparent").pack()

        sec2 = ctk.CTkFrame(body, fg_color="#0f1b2d", corner_radius=8)
        sec2.pack(fill="x", pady=(0,8))
        ctk.CTkLabel(sec2, text="Client",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#3498db").pack(anchor="w", padx=12, pady=(8,4))
        row2(sec2, "Name:", inv.get("client_name",""))
        row2(sec2, "Address:", inv.get("client_address",""))
        row2(sec2, "GSTIN:", inv.get("client_gstin",""))
        row2(sec2, "Phone:", inv.get("client_phone",""))
        ctk.CTkFrame(sec2, height=6, fg_color="transparent").pack()

        # items table
        sec3 = ctk.CTkFrame(body, fg_color="#0f1b2d", corner_radius=8)
        sec3.pack(fill="x", pady=(0,8))
        ctk.CTkLabel(sec3, text="Items",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#3498db").pack(anchor="w", padx=12, pady=(8,4))
        # table header
        th = ctk.CTkFrame(sec3, fg_color="#1a3a5c", corner_radius=0)
        th.pack(fill="x", padx=8, pady=(0,2))
        for col, w, txt in [("desc",240,"Description"),("qty",60,"Qty"),
                             ("rate",90,"Rate"),("gst",60,"GST%"),("amt",90,"Amount")]:
            ctk.CTkLabel(th, text=txt, width=w, anchor="w",
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#bdc3c7").pack(side="left", padx=4, pady=4)
        for it in items:
            tr = ctk.CTkFrame(sec3, fg_color="transparent")
            tr.pack(fill="x", padx=8)
            amt = it.get("amount") or (it.get("quantity",0) * it.get("unit_price",0))
            for val, w in [(it.get("description",""),240),(it.get("quantity",""),60),
                           (f"₹{it.get('unit_price',0):,.2f}",90),
                           (f"{it.get('gst_rate',0)}%",60),(f"₹{amt:,.2f}",90)]:
                ctk.CTkLabel(tr, text=str(val), width=w, anchor="w",
                             font=ctk.CTkFont(size=10),
                             text_color="#ecf0f1").pack(side="left", padx=4, pady=2)
        ctk.CTkFrame(sec3, height=6, fg_color="transparent").pack()

        # totals
        sec4 = ctk.CTkFrame(body, fg_color="#0f1b2d", corner_radius=8)
        sec4.pack(fill="x", pady=(0,8))
        ctk.CTkLabel(sec4, text="Totals",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#3498db").pack(anchor="w", padx=12, pady=(8,4))
        row2(sec4, "Subtotal:", f"₹{inv.get('subtotal',0):,.2f}")
        if inv.get("cgst_total",0):
            row2(sec4, "CGST:", f"₹{inv.get('cgst_total',0):,.2f}")
            row2(sec4, "SGST:", f"₹{inv.get('sgst_total',0):,.2f}")
        if inv.get("igst_total",0):
            row2(sec4, "IGST:", f"₹{inv.get('igst_total',0):,.2f}")
        if inv.get("discount_pct",0):
            row2(sec4, "Discount:", f"{inv.get('discount_pct',0)}%")
        ctk.CTkLabel(sec4, text=f"Grand Total:  ₹{inv.get('grand_total',0):,.2f}",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#27ae60").pack(anchor="w", padx=12, pady=(4,8))

        # ── Payment history section ─────────────────────────────────
        grand_total, total_paid, outstanding = db.get_invoice_outstanding(invoice_id)
        payments = db.get_invoice_payments(invoice_id)

        sec5 = ctk.CTkFrame(body, fg_color="#0f1b2d", corner_radius=8)
        sec5.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(sec5, text="Payments",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#3498db").pack(anchor="w", padx=12, pady=(8, 4))

        if payments:
            # Table header
            ph = ctk.CTkFrame(sec5, fg_color="#1a3a5c", corner_radius=0)
            ph.pack(fill="x", padx=8, pady=(0, 2))
            for txt, w in [("Date", 100), ("Mode", 120), ("Reference", 150), ("Amount", 100)]:
                ctk.CTkLabel(ph, text=txt, width=w, anchor="w",
                             font=ctk.CTkFont(size=10, weight="bold"),
                             text_color="#bdc3c7").pack(side="left", padx=4, pady=4)
            for p in payments:
                pr = ctk.CTkFrame(sec5, fg_color="transparent")
                pr.pack(fill="x", padx=8)
                for val, w in [(p.get("entry_date",""), 100),
                               (p.get("paid_into","") or "—", 120),
                               (p.get("reference","") or "—", 150),
                               (f"₹{p.get('amount',0):,.2f}", 100)]:
                    ctk.CTkLabel(pr, text=str(val), width=w, anchor="w",
                                 font=ctk.CTkFont(size=10),
                                 text_color="#ecf0f1").pack(side="left", padx=4, pady=2)
        else:
            ctk.CTkLabel(sec5, text="No payments recorded yet.",
                         font=ctk.CTkFont(size=11), text_color="#7f8c8d"
                         ).pack(anchor="w", padx=12, pady=(0, 4))

        # Outstanding / paid summary
        summary = ctk.CTkFrame(sec5, fg_color="#0d1117", corner_radius=6)
        summary.pack(fill="x", padx=8, pady=(4, 10))
        ctk.CTkLabel(summary, text=f"Total Paid:  ₹{total_paid:,.2f}",
                     font=ctk.CTkFont(size=11), text_color="#2ecc71").pack(side="left", padx=12, pady=6)
        outstanding_color = "#e74c3c" if outstanding > 0 else "#2ecc71"
        ctk.CTkLabel(summary, text=f"Outstanding:  ₹{outstanding:,.2f}",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=outstanding_color).pack(side="right", padx=12, pady=6)

        # bottom buttons
        btn_bar = ctk.CTkFrame(self, fg_color="#0f1b2d", corner_radius=0)
        btn_bar.pack(fill="x", padx=0, pady=0)
        ctk.CTkButton(btn_bar, text="Close", width=90,
                      fg_color="#2c3e50", hover_color="#3d5166",
                      command=self.destroy).pack(side="right", padx=12, pady=8)
        ctk.CTkButton(btn_bar, text="📄 PDF", width=90,
                      fg_color="#0f3460", hover_color="#1a4a8a",
                      command=lambda: self._gen_pdf(invoice_id, inv, items, firm)
                      ).pack(side="right", padx=4, pady=8)
        if status in ("Draft", "Sent", "Partially Paid"):
            pay_lbl = "💰 Receive Payment" if outstanding > 0 else "💰 Mark as Paid"
            ctk.CTkButton(btn_bar, text=pay_lbl, width=160,
                          fg_color="#1a5c1a", hover_color="#27ae60",
                          command=lambda: PaymentDialog(self, self.app, invoice_id, inv)
                          ).pack(side="left", padx=12, pady=8)

    def _gen_pdf(self, invoice_id, inv, items, firm):
        from invoice_pdf import generate_invoice_pdf
        import os
        inv_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Invoices")
        os.makedirs(inv_dir, exist_ok=True)
        path = os.path.join(inv_dir, f"{inv.get('invoice_number','invoice')}.pdf")
        generate_invoice_pdf(dict(inv), items, dict(firm) if firm else {}, path)
        os.startfile(path)


# ── E-Way Bill Dialog ──────────────────────────────────────────────────────────

class EWayBillDialog(ctk.CTkToplevel):
    """
    Displays E-Way Bill status for an invoice and allows:
    - Generate EWB (calls NIC EWB API)
    - Export EWB JSON
    - Update Vehicle Number
    - Cancel EWB
    """

    _TRANS_MODES    = ["Road", "Rail", "Air", "Ship"]
    _SUPPLY_TYPES   = ["Outward", "Inward"]
    _SUB_SUPPLY     = ["Supply", "Import", "Export", "Job Work",
                       "For Own Use", "Job Work Returns", "Goods Returns",
                       "Sales Return", "Others"]

    def __init__(self, parent, app, invoice_id: int):
        super().__init__(parent)
        self.app        = app
        self.invoice_id = invoice_id
        self.title("🚚  E-Way Bill")
        self.geometry("680x640")
        self.resizable(False, False)
        self.grab_set()
        self.after(50, self.lift)

        inv_row, items, firm = db.get_invoice_full(invoice_id)
        self._inv   = dict(inv_row)  if inv_row  else {}
        self._items = [dict(i) for i in items]
        self._firm  = dict(firm)     if firm      else {}

        # Header
        hdr = ctk.CTkFrame(self, fg_color="#0f3460", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text=f"🚚  E-Way Bill  —  {self._inv.get('invoice_number','')}",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(padx=20, pady=12)

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=12)

        # Current EWB status
        status       = self._inv.get("ewb_status") or "Not Generated"
        ewb_no       = self._inv.get("ewb_number") or ""
        ewb_date     = self._inv.get("ewb_date") or ""
        ewb_valid    = self._inv.get("ewb_valid_until") or ""
        vehicle_no   = self._inv.get("ewb_vehicle_no") or ""
        trans_id     = self._inv.get("ewb_transporter_id") or ""

        s_color = ("#2ecc71" if status == "Generated"
                   else "#e74c3c" if status == "Cancelled"
                   else "#7f8c8d")
        sf = ctk.CTkFrame(body, fg_color="#16213e", corner_radius=8)
        sf.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(sf, text="EWB Status", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#95a5a6").pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(sf, text=status, font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=s_color).pack(anchor="w", padx=12)

        if ewb_no:
            for label, val in [("EWB Number", ewb_no), ("EWB Date", ewb_date),
                                ("Valid Until", ewb_valid), ("Vehicle No.", vehicle_no),
                                ("Transporter ID", trans_id or "—")]:
                rw = ctk.CTkFrame(sf, fg_color="transparent")
                rw.pack(fill="x", padx=12, pady=2)
                ctk.CTkLabel(rw, text=f"{label}:", width=110, text_color="#95a5a6",
                             font=ctk.CTkFont(size=11)).pack(side="left")
                ctk.CTkLabel(rw, text=val or "—", text_color="#ecf0f1",
                             font=ctk.CTkFont(size=11)).pack(side="left")
        ctk.CTkFrame(sf, fg_color="transparent", height=8).pack()

        # Credentials check
        missing = []
        for k, label in [("ewb_username", "EWB Username"), ("ewb_password", "EWB Password")]:
            if not self._firm.get(k, "").strip():
                missing.append(label)

        if missing:
            warn = ctk.CTkFrame(body, fg_color="#2d1b00", corner_radius=8)
            warn.pack(fill="x", pady=(0, 12))
            ctk.CTkLabel(warn,
                         text=f"⚠  Missing EWB credentials: {', '.join(missing)}\n"
                              "    Go to Settings → E-Way Bill to configure them.",
                         font=ctk.CTkFont(size=11), text_color="#f39c12",
                         justify="left").pack(padx=12, pady=10)

        # ── Transport details form (only shown when not yet generated) ─────────
        if status not in ("Generated", "Cancelled"):
            ff = ctk.CTkFrame(body, fg_color="#16213e", corner_radius=8)
            ff.pack(fill="x", pady=(0, 12))
            ctk.CTkLabel(ff, text="Transport Details",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#95a5a6").pack(anchor="w", padx=12, pady=(10, 4))

            def _lbl_field(parent, label, var):
                ctk.CTkLabel(parent, text=label, text_color="#95a5a6",
                             font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12, pady=(4, 0))
                ctk.CTkEntry(parent, textvariable=var).pack(fill="x", padx=12, pady=(2, 0))

            self._vehicle_var  = ctk.StringVar()
            self._trans_id_var = ctk.StringVar()
            self._distance_var = ctk.StringVar(value="0")
            self._trans_doc_no_var   = ctk.StringVar()
            self._trans_doc_date_var = ctk.StringVar()

            _lbl_field(ff, "Vehicle Number (e.g. TN01AB1234)", self._vehicle_var)
            _lbl_field(ff, "Transporter GSTIN (optional)", self._trans_id_var)
            _lbl_field(ff, "Transport Distance (km)", self._distance_var)

            # Transport mode
            ctk.CTkLabel(ff, text="Transport Mode", text_color="#95a5a6",
                         font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12, pady=(6, 0))
            self._trans_mode_var = ctk.StringVar(value="Road")
            ctk.CTkComboBox(ff, values=self._TRANS_MODES,
                            variable=self._trans_mode_var).pack(fill="x", padx=12, pady=(2, 0))

            # Supply type
            ctk.CTkLabel(ff, text="Supply Type", text_color="#95a5a6",
                         font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12, pady=(6, 0))
            self._supply_type_var = ctk.StringVar(value="Outward")
            ctk.CTkComboBox(ff, values=self._SUPPLY_TYPES,
                            variable=self._supply_type_var).pack(fill="x", padx=12, pady=(2, 0))

            # Sub supply type
            ctk.CTkLabel(ff, text="Sub Supply Type", text_color="#95a5a6",
                         font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12, pady=(6, 0))
            self._sub_supply_var = ctk.StringVar(value="Supply")
            ctk.CTkComboBox(ff, values=self._SUB_SUPPLY,
                            variable=self._sub_supply_var).pack(fill="x", padx=12, pady=(2, 0))

            ctk.CTkFrame(ff, fg_color="transparent", height=6).pack()

        # ── Vehicle update form (shown when already generated) ─────────────────
        if status == "Generated":
            vf = ctk.CTkFrame(body, fg_color="#16213e", corner_radius=8)
            vf.pack(fill="x", pady=(0, 12))
            ctk.CTkLabel(vf, text="Update Vehicle Number",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#95a5a6").pack(anchor="w", padx=12, pady=(10, 4))
            ctk.CTkLabel(vf, text="New Vehicle Number", text_color="#95a5a6",
                         font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12, pady=(4, 0))
            self._new_vehicle_var = ctk.StringVar(value=vehicle_no)
            ctk.CTkEntry(vf, textvariable=self._new_vehicle_var
                         ).pack(fill="x", padx=12, pady=(2, 0))
            ctk.CTkButton(vf, text="🔄  Update Vehicle", height=32,
                          fg_color="#1a3a5c", hover_color="#2355c2",
                          command=self._update_vehicle,
                          ).pack(fill="x", padx=12, pady=(8, 10))

        # ── Action buttons ────────────────────────────────────────────────────
        bf = ctk.CTkFrame(body, fg_color="transparent")
        bf.pack(fill="x", pady=(4, 0))

        can_gen = not missing and status not in ("Generated",)
        ctk.CTkButton(
            bf, text="⚡  Generate E-Way Bill", height=36,
            fg_color="#1a6b1a" if can_gen else "#2c3e50",
            hover_color="#27ae60" if can_gen else "#2c3e50",
            state="normal" if can_gen else "disabled",
            command=self._generate_ewb,
        ).pack(fill="x", pady=4)

        ctk.CTkButton(
            bf, text="💾  Export EWB JSON", height=36,
            fg_color="#1a3a5c", hover_color="#2355c2",
            command=self._export_json,
        ).pack(fill="x", pady=4)

        if status == "Generated" and not missing:
            ctk.CTkButton(
                bf, text="🗑  Cancel E-Way Bill", height=36,
                fg_color="#7f1f1f", hover_color="#c0392b",
                command=self._cancel_ewb,
            ).pack(fill="x", pady=4)

        self._status_lbl = ctk.CTkLabel(body, text="", font=ctk.CTkFont(size=11),
                                         text_color="#f39c12", wraplength=620, justify="left")
        self._status_lbl.pack(anchor="w", pady=(8, 0))

    # ── helpers ───────────────────────────────────────────────────────────────

    def _get_client(self):
        client_id = self._inv.get("client_id")
        if client_id:
            for c in db.get_all_clients():
                if c["id"] == client_id:
                    return dict(c)
        return {}

    def _build_ewb_client(self):
        from ewaybill import EWBClient
        f = self._firm
        return EWBClient(
            gstin    = f.get("gstin", ""),
            username = f.get("ewb_username", ""),
            password = f.get("ewb_password", ""),
            sandbox  = bool(f.get("ewb_sandbox", 1)),
        )

    def _get_trans_mode_code(self) -> str:
        from ewaybill import TRANS_MODES
        return TRANS_MODES.get(self._trans_mode_var.get(), "1")

    def _get_supply_type_code(self) -> str:
        from ewaybill import SUPPLY_TYPES
        return SUPPLY_TYPES.get(self._supply_type_var.get(), "O")

    def _get_sub_supply_code(self) -> int:
        from ewaybill import SUB_SUPPLY_TYPES
        return SUB_SUPPLY_TYPES.get(self._sub_supply_var.get(), 1)

    def _generate_ewb(self):
        self._status_lbl.configure(text="Authenticating with EWB portal…", text_color="#f39c12")
        self.update()
        try:
            from ewaybill import build_ewb_json
            client = self._get_client()
            ewb_c  = self._build_ewb_client()

            try:
                dist = int(self._distance_var.get().strip() or 0)
            except ValueError:
                dist = 0

            payload = build_ewb_json(
                invoice        = self._inv,
                items          = self._items,
                firm           = self._firm,
                client         = client,
                transporter_id = self._trans_id_var.get().strip(),
                vehicle_no     = self._vehicle_var.get().strip(),
                trans_mode     = self._get_trans_mode_code(),
                trans_distance = dist,
                trans_doc_no   = self._trans_doc_no_var.get().strip(),
                trans_doc_date = self._trans_doc_date_var.get().strip(),
                supply_type    = self._get_supply_type_code(),
                sub_supply_type= self._get_sub_supply_code(),
            )

            self._status_lbl.configure(text="Generating E-Way Bill…")
            self.update()

            result = ewb_c.generate_ewb(payload)
            ewb_no    = str(result.get("ewayBillNo", ""))
            ewb_date  = result.get("ewayBillDate", "")
            ewb_valid = result.get("validUpto", "")
            veh_no    = self._vehicle_var.get().strip()
            tid       = self._trans_id_var.get().strip()

            db.update_invoice_ewb(
                self.invoice_id, ewb_no, ewb_date, ewb_valid,
                vehicle_no=veh_no, transporter_id=tid, status="Generated",
            )
            self._status_lbl.configure(
                text=f"✓ E-Way Bill Generated!\nEWB No: {ewb_no}  |  Valid Until: {ewb_valid}",
                text_color="#2ecc71",
            )
            if hasattr(self.master, "refresh"):
                self.master.refresh()
        except Exception as e:
            self._status_lbl.configure(text=f"✗ Error: {e}", text_color="#e74c3c")

    def _export_json(self):
        try:
            from ewaybill import build_ewb_json
            import json as _json
            client  = self._get_client()
            ewb_c   = self._build_ewb_client()
            payload = build_ewb_json(
                invoice        = self._inv,
                items          = self._items,
                firm           = self._firm,
                client         = client,
                transporter_id = getattr(self, "_trans_id_var", ctk.StringVar()).get().strip(),
                vehicle_no     = getattr(self, "_vehicle_var",  ctk.StringVar()).get().strip(),
            )
            default_name = f"ewb_{self._inv.get('invoice_number','').replace('/','-')}.json"
            path = filedialog.asksaveasfilename(
                title="Save E-Way Bill JSON",
                defaultextension=".json",
                initialfile=default_name,
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
            if path:
                with open(path, "w", encoding="utf-8") as fh:
                    _json.dump(payload, fh, indent=2, ensure_ascii=False)
                self._status_lbl.configure(text=f"✓ Saved to {path}", text_color="#2ecc71")
        except Exception as e:
            self._status_lbl.configure(text=f"✗ Error: {e}", text_color="#e74c3c")

    def _update_vehicle(self):
        new_veh = self._new_vehicle_var.get().strip().upper()
        if not new_veh:
            messagebox.showerror("Error", "Enter a vehicle number.")
            return
        self._status_lbl.configure(text="Updating vehicle number…", text_color="#f39c12")
        self.update()
        try:
            ewb_c = self._build_ewb_client()
            from ewaybill import _STATE_CODES
            state_code = _STATE_CODES.get(self._firm.get("state", ""), 0)
            ewb_c.update_vehicle(
                ewb_no     = self._inv.get("ewb_number", ""),
                vehicle_no = new_veh,
                from_place = self._firm.get("city", ""),
                from_state = state_code,
            )
            db.update_invoice_ewb(
                self.invoice_id,
                self._inv.get("ewb_number", ""),
                self._inv.get("ewb_date", ""),
                self._inv.get("ewb_valid_until", ""),
                vehicle_no=new_veh,
                transporter_id=self._inv.get("ewb_transporter_id", ""),
                status="Generated",
            )
            self._status_lbl.configure(
                text=f"✓ Vehicle updated to {new_veh}", text_color="#2ecc71")
            if hasattr(self.master, "refresh"):
                self.master.refresh()
        except Exception as e:
            self._status_lbl.configure(text=f"✗ Error: {e}", text_color="#e74c3c")

    def _cancel_ewb(self):
        ewb_no = self._inv.get("ewb_number", "")
        if not ewb_no:
            return
        if not messagebox.askyesno("Cancel EWB",
                                   f"Cancel E-Way Bill:\n{ewb_no}\n\nThis cannot be undone. Proceed?"):
            return
        self._status_lbl.configure(text="Cancelling E-Way Bill…", text_color="#f39c12")
        self.update()
        try:
            ewb_c = self._build_ewb_client()
            ewb_c.cancel_ewb(ewb_no, cancel_reason=2, cancel_remarks="Data entry mistake")
            db.update_invoice_ewb(
                self.invoice_id,
                ewb_no,
                self._inv.get("ewb_date", ""),
                self._inv.get("ewb_valid_until", ""),
                status="Cancelled",
            )
            self._status_lbl.configure(text="✓ E-Way Bill Cancelled.", text_color="#e74c3c")
            if hasattr(self.master, "refresh"):
                self.master.refresh()
        except Exception as e:
            self._status_lbl.configure(text=f"✗ Error: {e}", text_color="#e74c3c")


# ── WhatsApp Invoice Share Dialog ─────────────────────────────────────────────

class WhatsAppShareDialog(ctk.CTkToplevel):
    """Generate PDF and open WhatsApp Web with a pre-filled message."""

    def __init__(self, parent, invoice_id: int):
        super().__init__(parent)
        self.invoice_id = invoice_id
        self.title("Share Invoice via WhatsApp")
        self.geometry("540x560")
        self.resizable(False, False)
        self.grab_set()

        inv, _items, firm = db.get_invoice_full(invoice_id)
        self._inv  = dict(inv)
        self._firm = dict(firm) if firm else {}

        # ── Build PDF path ──────────────────────────────────────────────────
        inv_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Invoices")
        os.makedirs(inv_dir, exist_ok=True)
        self._pdf_path = os.path.join(inv_dir, f"{self._inv.get('invoice_number','Invoice')}.pdf")

        # ── Defaults ───────────────────────────────────────────────────────
        raw_phone = str(self._inv.get("client_phone") or "").strip()
        self._pdf_generated = False

        frm = ctk.CTkFrame(self, fg_color="transparent")
        frm.pack(fill="both", expand=True, padx=20, pady=14)

        # Header
        ctk.CTkLabel(frm, text="📱  WhatsApp Invoice Sharing",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(0, 10))

        # Invoice summary card
        card = ctk.CTkFrame(frm, fg_color="#1a3a5c", corner_radius=8)
        card.pack(fill="x", pady=(0, 12))
        inv_info = (
            f"Invoice: {self._inv.get('invoice_number','')}   |   "
            f"Date: {self._inv.get('invoice_date','')}   |   "
            f"Amount: ₹{self._inv.get('grand_total',0):,.2f}"
        )
        ctk.CTkLabel(card, text=inv_info, font=ctk.CTkFont(size=11),
                     text_color="#ecf0f1").pack(padx=12, pady=8)

        # Phone number
        ctk.CTkLabel(frm, text="WhatsApp Number  (with country code, e.g. 919876543210)",
                     font=ctk.CTkFont(size=11), text_color=COLORS["text_dim"]).pack(anchor="w")
        self._phone_var = ctk.StringVar(value=self._clean_phone(raw_phone))
        ctk.CTkEntry(frm, textvariable=self._phone_var, width=480,
                     placeholder_text="91XXXXXXXXXX").pack(anchor="w", pady=(2, 10))

        # Message
        ctk.CTkLabel(frm, text="Message  (edit before sending)",
                     font=ctk.CTkFont(size=11), text_color=COLORS["text_dim"]).pack(anchor="w")
        self._msg_box = ctk.CTkTextbox(frm, height=160, width=480)
        self._msg_box.pack(anchor="w", pady=(2, 10))
        self._msg_box.insert("0.0", self._default_message())

        # PDF path row
        pdf_row = ctk.CTkFrame(frm, fg_color="transparent")
        pdf_row.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(pdf_row, text="PDF will be saved to:", font=ctk.CTkFont(size=10),
                     text_color=COLORS["text_dim"]).pack(side="left")
        ctk.CTkLabel(pdf_row, text=os.path.basename(self._pdf_path),
                     font=ctk.CTkFont(size=10), text_color="#2980b9").pack(side="left", padx=4)

        self._copy_btn = ctk.CTkButton(frm, text="📋 Copy PDF Path", width=160, height=28,
                                       fg_color="#2c3e50", hover_color="#34495e",
                                       font=ctk.CTkFont(size=11),
                                       state="disabled", command=self._copy_path)
        self._copy_btn.pack(anchor="w", pady=(0, 10))

        # Action buttons
        btn_row = ctk.CTkFrame(frm, fg_color="transparent")
        btn_row.pack(fill="x", pady=(4, 0))

        ctk.CTkButton(btn_row, text="Cancel", width=90, fg_color="#555",
                      hover_color="#444", command=self.destroy).pack(side="right", padx=4)
        ctk.CTkButton(btn_row, text="📤 Open in WhatsApp Web", width=200,
                      fg_color="#075e54", hover_color="#128c7e",
                      command=self._send_whatsapp).pack(side="right", padx=4)
        ctk.CTkButton(btn_row, text="🖨 Generate PDF", width=130,
                      fg_color="#0f3460", hover_color="#1a4a8a",
                      command=self._generate_pdf).pack(side="right", padx=4)

    def _clean_phone(self, raw: str) -> str:
        phone = raw.replace(" ", "").replace("-", "").replace("+", "")
        if phone and not phone.startswith("91"):
            phone = "91" + phone.lstrip("0")
        return phone

    def _default_message(self) -> str:
        inv  = self._inv
        firm = self._firm
        firm_name = firm.get("firm_name") or "Us"
        due_date  = inv.get("due_date") or ""
        lines = [
            f"Dear {inv.get('client_name') or 'Customer'},",
            "",
            "Please find your invoice details below:",
            f"  Invoice No : {inv.get('invoice_number', '')}",
            f"  Date       : {inv.get('invoice_date', '')}",
            f"  Amount Due : ₹{inv.get('grand_total', 0):,.2f}",
        ]
        if due_date:
            lines.append(f"  Due By     : {due_date}")
        lines += [
            "",
            "Kindly arrange payment at your earliest convenience.",
            "",
            f"Regards,",
            firm_name,
        ]
        return "\n".join(lines)

    def _generate_pdf(self):
        try:
            from invoice_pdf import generate_invoice_pdf
            inv, items, firm = db.get_invoice_full(self.invoice_id)
            generate_invoice_pdf(dict(inv), [dict(i) for i in items],
                                 dict(firm) if firm else {}, self._pdf_path)
            self._pdf_generated = True
            self._copy_btn.configure(state="normal", fg_color="#1a5276")
            messagebox.showinfo("PDF Ready",
                                f"PDF saved to:\n{self._pdf_path}\n\n"
                                "Use 'Copy PDF Path' or attach it manually in WhatsApp Web.",
                                parent=self)
        except Exception as e:
            messagebox.showerror("PDF Error", str(e), parent=self)

    def _copy_path(self):
        self.clipboard_clear()
        self.clipboard_append(self._pdf_path)
        messagebox.showinfo("Copied", "PDF path copied to clipboard.\n"
                            "In WhatsApp Web attach the file from that path.",
                            parent=self)

    def _send_whatsapp(self):
        import urllib.parse, webbrowser
        phone = self._phone_var.get().strip()
        msg   = self._msg_box.get("0.0", "end").strip()
        if not msg:
            messagebox.showwarning("Validation", "Message cannot be empty.", parent=self)
            return
        encoded = urllib.parse.quote(msg)
        url = (f"https://wa.me/{phone}?text={encoded}"
               if phone else f"https://wa.me/?text={encoded}")
        webbrowser.open(url)
        if not self._pdf_generated:
            messagebox.showinfo(
                "Tip",
                "WhatsApp Web opened with the message pre-filled.\n\n"
                "To attach the invoice PDF:\n"
                "1. Click 'Generate PDF' first.\n"
                "2. Use 'Copy PDF Path' to get the file path.\n"
                "3. In WhatsApp Web click the 📎 attachment icon and attach the file.",
                parent=self
            )


# ── Email Invoice Share Dialog ────────────────────────────────────────────────

class EmailShareDialog(ctk.CTkToplevel):
    """Send invoice as email with PDF attachment via configured SMTP."""

    def __init__(self, parent, invoice_id: int):
        super().__init__(parent)
        self.invoice_id = invoice_id
        self.title("Send Invoice via Email")
        self.geometry("560x600")
        self.resizable(False, False)
        self.grab_set()

        inv, _items, firm = db.get_invoice_full(invoice_id)
        self._inv  = dict(inv)
        self._firm = dict(firm) if firm else {}

        # SMTP settings
        fs = db.get_firm_settings()
        self._fs = dict(fs) if fs else {}

        inv_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Invoices")
        os.makedirs(inv_dir, exist_ok=True)
        self._pdf_path = os.path.join(inv_dir, f"{self._inv.get('invoice_number','Invoice')}.pdf")

        frm = ctk.CTkFrame(self, fg_color="transparent")
        frm.pack(fill="both", expand=True, padx=20, pady=14)

        ctk.CTkLabel(frm, text="✉  Send Invoice by Email",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(0, 10))

        # Invoice summary card
        card = ctk.CTkFrame(frm, fg_color="#1a3a5c", corner_radius=8)
        card.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(card,
                     text=(f"Invoice: {self._inv.get('invoice_number','')}   |   "
                           f"Date: {self._inv.get('invoice_date','')}   |   "
                           f"Amount: ₹{self._inv.get('grand_total',0):,.2f}"),
                     font=ctk.CTkFont(size=11), text_color="#ecf0f1").pack(padx=12, pady=8)

        # Check SMTP config
        if not self._fs.get("smtp_user"):
            ctk.CTkLabel(frm,
                         text="⚠  SMTP not configured. Go to Settings → 📧 Email to set it up.",
                         font=ctk.CTkFont(size=11), text_color=COLORS["warning"]).pack(anchor="w", pady=(0, 10))

        # To
        ctk.CTkLabel(frm, text="To *", font=ctk.CTkFont(size=11),
                     text_color=COLORS["text_dim"]).pack(anchor="w")
        self._to_var = ctk.StringVar(value=self._inv.get("client_email") or "")
        ctk.CTkEntry(frm, textvariable=self._to_var, width=500,
                     placeholder_text="customer@example.com").pack(anchor="w", pady=(2, 8))

        # CC
        ctk.CTkLabel(frm, text="CC", font=ctk.CTkFont(size=11),
                     text_color=COLORS["text_dim"]).pack(anchor="w")
        self._cc_var = ctk.StringVar(value=self._fs.get("email", ""))
        ctk.CTkEntry(frm, textvariable=self._cc_var, width=500).pack(anchor="w", pady=(2, 8))

        # Subject
        ctk.CTkLabel(frm, text="Subject", font=ctk.CTkFont(size=11),
                     text_color=COLORS["text_dim"]).pack(anchor="w")
        self._subj_var = ctk.StringVar(value=self._default_subject())
        ctk.CTkEntry(frm, textvariable=self._subj_var, width=500).pack(anchor="w", pady=(2, 8))

        # Body
        ctk.CTkLabel(frm, text="Message", font=ctk.CTkFont(size=11),
                     text_color=COLORS["text_dim"]).pack(anchor="w")
        self._body_box = ctk.CTkTextbox(frm, height=150, width=500)
        self._body_box.pack(anchor="w", pady=(2, 8))
        self._body_box.insert("0.0", self._default_body())

        # Attach PDF checkbox
        self._attach_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(frm, text="Attach invoice PDF", variable=self._attach_var,
                        font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(0, 10))

        # Status label
        self._status_lbl = ctk.CTkLabel(frm, text="", font=ctk.CTkFont(size=11))
        self._status_lbl.pack(anchor="w")

        # Buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=8)
        ctk.CTkButton(btn_row, text="Cancel", width=90, fg_color="#555",
                      hover_color="#444", command=self.destroy).pack(side="right", padx=4)
        self._send_btn = ctk.CTkButton(btn_row, text="📤 Send Email", width=140,
                                       fg_color="#6c3483", hover_color="#7d3c98",
                                       command=self._send)
        self._send_btn.pack(side="right", padx=4)

    def _default_subject(self):
        firm_name = self._firm.get("firm_name") or "Us"
        inv_no    = self._inv.get("invoice_number", "")
        return f"Invoice {inv_no} from {firm_name}"

    def _default_body(self):
        firm_name = self._firm.get("firm_name") or "Us"
        inv       = self._inv
        due_date  = inv.get("due_date") or ""
        lines = [
            f"Dear {inv.get('client_name') or 'Customer'},",
            "",
            "Please find attached your invoice details:",
            f"  Invoice No : {inv.get('invoice_number', '')}",
            f"  Date       : {inv.get('invoice_date', '')}",
            f"  Amount Due : ₹{inv.get('grand_total', 0):,.2f}",
        ]
        if due_date:
            lines.append(f"  Due By     : {due_date}")
        lines += [
            "",
            "Kindly arrange payment at your earliest convenience.",
            "Please feel free to contact us for any queries.",
            "",
            "Regards,",
            firm_name,
        ]
        return "\n".join(lines)

    def _send(self):
        import smtplib, ssl
        from email.message import EmailMessage

        to_addr = self._to_var.get().strip()
        if not to_addr:
            messagebox.showwarning("Validation", "To address is required.", parent=self); return

        fs   = self._fs
        host = fs.get("smtp_host", "smtp.gmail.com")
        user = fs.get("smtp_user", "")
        pwd  = fs.get("smtp_password", "")
        tls  = bool(fs.get("smtp_tls", 1))
        from_name = fs.get("smtp_from_name") or fs.get("firm_name") or user
        try:
            port = int(fs.get("smtp_port", 587))
        except (ValueError, TypeError):
            port = 587

        if not user:
            messagebox.showerror("SMTP Not Configured",
                                 "Go to Settings → 📧 Email and configure your SMTP credentials.",
                                 parent=self); return

        self._send_btn.configure(state="disabled")
        self._status_lbl.configure(text="Sending…", text_color="#f39c12")
        self.update_idletasks()

        try:
            msg = EmailMessage()
            msg["Subject"] = self._subj_var.get().strip()
            msg["From"]    = f"{from_name} <{user}>"
            msg["To"]      = to_addr
            cc = self._cc_var.get().strip()
            if cc:
                msg["CC"] = cc
            msg.set_content(self._body_box.get("0.0", "end").strip())

            if self._attach_var.get():
                # Generate PDF
                from invoice_pdf import generate_invoice_pdf
                inv, items, firm = db.get_invoice_full(self.invoice_id)
                generate_invoice_pdf(dict(inv), [dict(i) for i in items],
                                     dict(firm) if firm else {}, self._pdf_path)
                with open(self._pdf_path, "rb") as f:
                    msg.add_attachment(f.read(), maintype="application", subtype="pdf",
                                       filename=os.path.basename(self._pdf_path))

            if tls:
                s = smtplib.SMTP(host, port, timeout=15)
                s.ehlo(); s.starttls(context=ssl.create_default_context()); s.ehlo()
            else:
                s = smtplib.SMTP_SSL(host, port, timeout=15,
                                     context=ssl.create_default_context())
            s.login(user, pwd)
            s.send_message(msg)
            s.quit()

            self._status_lbl.configure(text=f"✓ Sent to {to_addr}", text_color=COLORS["success"])
            self._send_btn.configure(state="normal")
            self.after(2000, self.destroy)

        except Exception as e:
            self._status_lbl.configure(text=f"✗ {e}", text_color=COLORS["danger"])
            self._send_btn.configure(state="normal")


# ── E-Invoice Dialog ───────────────────────────────────────────────────────────

class EInvoiceDialog(ctk.CTkToplevel):
    """
    Shows the e-invoice (IRN) status for an invoice and allows:
    - Generate IRN (calls IRP API)
    - Export Invoice JSON (saves the IRP payload to disk)
    - Cancel IRN
    """

    def __init__(self, parent, app, invoice_id: int):
        super().__init__(parent)
        self.app        = app
        self.invoice_id = invoice_id
        self.title("🧾  E-Invoice (IRN)")
        self.geometry("640x520")
        self.resizable(False, False)
        self.grab_set()
        self.after(50, self.lift)

        inv_row, items, firm = db.get_invoice_full(invoice_id)
        self._inv  = dict(inv_row)  if inv_row  else {}
        self._items = [dict(i) for i in items]
        self._firm = dict(firm)     if firm      else {}

        # Header
        hdr = ctk.CTkFrame(self, fg_color="#0f3460", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text=f"🧾  E-Invoice  —  {self._inv.get('invoice_number','')}",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(padx=20, pady=12)

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=12)

        # Current IRN status card
        status = self._inv.get("einvoice_status") or "Not Generated"
        irn    = self._inv.get("irn") or ""
        ack_no = self._inv.get("ack_number") or ""
        ack_dt = self._inv.get("ack_date") or ""

        s_color = "#2ecc71" if status == "Generated" else ("#e74c3c" if status == "Cancelled" else "#7f8c8d")
        sf = ctk.CTkFrame(body, fg_color="#16213e", corner_radius=8)
        sf.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(sf, text="IRN Status", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#95a5a6").pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(sf, text=status, font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=s_color).pack(anchor="w", padx=12)

        if irn:
            for label, val in [("IRN", irn), ("Ack Number", ack_no), ("Ack Date", ack_dt)]:
                row = ctk.CTkFrame(sf, fg_color="transparent")
                row.pack(fill="x", padx=12, pady=2)
                ctk.CTkLabel(row, text=f"{label}:", width=90, text_color="#95a5a6",
                             font=ctk.CTkFont(size=11)).pack(side="left")
                val_lbl = ctk.CTkLabel(row, text=val or "—", text_color="#ecf0f1",
                                       font=ctk.CTkFont(size=11))
                val_lbl.pack(side="left")
        ctk.CTkFrame(sf, fg_color="transparent", height=8).pack()

        # Credentials check
        missing = []
        for k, label in [("irp_client_id","Client ID"), ("irp_client_secret","Client Secret"),
                         ("irp_username","IRP Username"), ("irp_password","IRP Password")]:
            if not self._firm.get(k, "").strip():
                missing.append(label)

        if missing:
            warn = ctk.CTkFrame(body, fg_color="#2d1b00", corner_radius=8)
            warn.pack(fill="x", pady=(0, 12))
            ctk.CTkLabel(warn,
                         text=f"⚠  Missing IRP credentials: {', '.join(missing)}\n"
                              "    Go to Settings → E-Invoice to configure them.",
                         font=ctk.CTkFont(size=11), text_color="#f39c12",
                         justify="left").pack(padx=12, pady=10)

        # Action buttons
        bf = ctk.CTkFrame(body, fg_color="transparent")
        bf.pack(fill="x", pady=(4, 0))

        can_generate = not missing and status not in ("Generated",)
        ctk.CTkButton(
            bf, text="⚡  Generate IRN", height=36,
            fg_color="#1a6b1a" if can_generate else "#2c3e50",
            hover_color="#27ae60" if can_generate else "#2c3e50",
            state="normal" if can_generate else "disabled",
            command=self._generate_irn,
        ).pack(fill="x", pady=4)

        ctk.CTkButton(
            bf, text="💾  Export Invoice JSON", height=36,
            fg_color="#1a3a5c", hover_color="#2355c2",
            command=self._export_json,
        ).pack(fill="x", pady=4)

        if status == "Generated" and not missing:
            ctk.CTkButton(
                bf, text="🗑  Cancel IRN", height=36,
                fg_color="#7f1f1f", hover_color="#c0392b",
                command=self._cancel_irn,
            ).pack(fill="x", pady=4)

        # Status label for async feedback
        self._status_lbl = ctk.CTkLabel(body, text="", font=ctk.CTkFont(size=11),
                                         text_color="#f39c12", wraplength=580, justify="left")
        self._status_lbl.pack(anchor="w", pady=(8, 0))

    # ── helpers ───────────────────────────────────────────────────────────────

    def _get_client(self):
        client_id = self._inv.get("client_id")
        if client_id:
            rows = db.get_all_clients()
            for c in rows:
                if c["id"] == client_id:
                    return dict(c)
        return {}

    def _build_irp_client(self):
        from einvoice import IRPClient
        f = self._firm
        return IRPClient(
            gstin         = f.get("gstin", ""),
            client_id     = f.get("irp_client_id", ""),
            client_secret = f.get("irp_client_secret", ""),
            username      = f.get("irp_username", ""),
            password      = f.get("irp_password", ""),
            sandbox       = bool(f.get("einvoice_sandbox", 1)),
        )

    def _generate_irn(self):
        self._status_lbl.configure(text="Authenticating with IRP…", text_color="#f39c12")
        self.update()
        try:
            from einvoice import build_einvoice_json
            client  = self._get_client()
            irp     = self._build_irp_client()
            payload = build_einvoice_json(self._inv, self._items, self._firm, client)

            self._status_lbl.configure(text="Generating IRN… (this may take a few seconds)")
            self.update()

            result = irp.generate_irn(payload)
            irn      = result.get("Irn", "")
            ack_no   = str(result.get("AckNo", ""))
            ack_dt   = result.get("AckDt", "")
            signed_qr = result.get("SignedQRCode", "")

            db.update_invoice_irn(self.invoice_id, irn, ack_no, ack_dt,
                                  signed_qr=signed_qr, status="Generated")
            self._status_lbl.configure(
                text=f"✓ IRN Generated Successfully!\nIRN: {irn[:40]}…",
                text_color="#2ecc71"
            )
            # Refresh parent
            if hasattr(self.master, "refresh"):
                self.master.refresh()
        except Exception as e:
            self._status_lbl.configure(text=f"✗ Error: {e}", text_color="#e74c3c")

    def _export_json(self):
        try:
            from einvoice import build_einvoice_json
            import json as _json
            client  = self._get_client()
            irp     = self._build_irp_client()
            payload = build_einvoice_json(self._inv, self._items, self._firm, client)
            default_name = f"einvoice_{self._inv.get('invoice_number','').replace('/','-')}.json"
            path = filedialog.asksaveasfilename(
                title="Save E-Invoice JSON",
                defaultextension=".json",
                initialfile=default_name,
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
            if path:
                with open(path, "w", encoding="utf-8") as fh:
                    _json.dump(payload, fh, indent=2, ensure_ascii=False)
                self._status_lbl.configure(text=f"✓ Saved to {path}", text_color="#2ecc71")
        except Exception as e:
            self._status_lbl.configure(text=f"✗ Error: {e}", text_color="#e74c3c")

    def _cancel_irn(self):
        irn = self._inv.get("irn", "")
        if not irn:
            return
        if not messagebox.askyesno("Cancel IRN",
                                   f"Cancel IRN:\n{irn}\n\nThis cannot be undone. Proceed?"):
            return
        self._status_lbl.configure(text="Cancelling IRN…", text_color="#f39c12")
        self.update()
        try:
            irp = self._build_irp_client()
            irp.cancel_irn(irn, reason_code=2, remark="Data entry mistake")
            db.update_invoice_irn(self.invoice_id, irn,
                                  self._inv.get("ack_number", ""),
                                  self._inv.get("ack_date", ""),
                                  status="Cancelled")
            self._status_lbl.configure(text="✓ IRN Cancelled.", text_color="#e74c3c")
            if hasattr(self.master, "refresh"):
                self.master.refresh()
        except Exception as e:
            self._status_lbl.configure(text=f"✗ Error: {e}", text_color="#e74c3c")


# ── Invoice Dialog ─────────────────────────────────────────────────────────────

class InvoiceDialog(ctk.CTkToplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("New Invoice")
        self.resizable(True, True)
        self.grab_set()
        self.update_idletasks()
        screen_h = self.winfo_screenheight()
        h = min(760, screen_h - 60)
        self.geometry(f"900x{h}")

        self.items = []
        self.clients  = db.get_all_clients()
        self.products = db.get_all_products()
        self.firm     = db.get_firm_settings()
        self.client_map  = {c["name"]: dict(c) for c in self.clients}
        self.product_map = {f"{p['name']} ({p['sku']})": dict(p) for p in self.products}
        self._due_days = int((dict(self.firm).get("default_due_days") or 30) if self.firm else 30)
        self._items_scroll = None  # guard: set during _build

        self._build()

    # ── build ─────────────────────────────────────────────────────────────────

    def _build(self):
        main = ctk.CTkScrollableFrame(self, fg_color="#0d1117")
        main.pack(fill="both", expand=True)
        self._main = main

        ctk.CTkLabel(main, text="New Tax Invoice",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color="#ecf0f1").pack(padx=20, pady=(16, 4), anchor="w")

        # ── top two-column section ────────────────────────────────────────────
        top = ctk.CTkFrame(main, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(0, 10))
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=1)

        def lbl_entry(parent, label, default="", width=300):
            ctk.CTkLabel(parent, text=label, text_color="#95a5a6",
                         font=ctk.CTkFont(size=10)).pack(anchor="w", padx=14, pady=(6, 0))
            var = ctk.StringVar(value=str(default))
            ctk.CTkEntry(parent, textvariable=var, width=width, height=32
                         ).pack(padx=14, pady=(2, 0), anchor="w")
            return var

        today = datetime.now().strftime("%Y-%m-%d")
        due   = (datetime.now() + timedelta(days=self._due_days)).strftime("%Y-%m-%d")

        left = ctk.CTkFrame(top, fg_color="#16213e", corner_radius=10)
        left.grid(row=0, column=0, padx=(0, 6), sticky="nsew")
        ctk.CTkLabel(left, text="Invoice Details",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#95a5a6").pack(padx=14, pady=(10, 2), anchor="w")
        self.inv_num  = lbl_entry(left, "Invoice Number *", db.generate_invoice_number())
        self.inv_date = lbl_entry(left, "Invoice Date *", today)
        self.inv_due  = lbl_entry(left, "Due Date", due)
        self.notes_var = lbl_entry(left, "Notes", "")
        ctk.CTkFrame(left, fg_color="transparent", height=8).pack()

        right = ctk.CTkFrame(top, fg_color="#16213e", corner_radius=10)
        right.grid(row=0, column=1, padx=(6, 0), sticky="nsew")
        ctk.CTkLabel(right, text="Client & Tax Type",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#95a5a6").pack(padx=14, pady=(10, 2), anchor="w")

        client_names = [c["name"] for c in self.clients]
        ctk.CTkLabel(right, text="Client *", text_color="#95a5a6",
                     font=ctk.CTkFont(size=10)).pack(anchor="w", padx=14, pady=(6, 0))
        self.client_var = ctk.StringVar(value=client_names[0] if client_names else "")
        ctk.CTkComboBox(right, values=client_names, variable=self.client_var,
                        width=300, command=self._auto_supply_type).pack(padx=14, pady=(2, 0), anchor="w")

        ctk.CTkLabel(right, text="Supply Type", text_color="#95a5a6",
                     font=ctk.CTkFont(size=10)).pack(anchor="w", padx=14, pady=(10, 0))
        self.supply_var = ctk.StringVar(value="intra")
        sf = ctk.CTkFrame(right, fg_color="transparent")
        sf.pack(padx=14, anchor="w")
        ctk.CTkRadioButton(sf, text="Intra-State (CGST + SGST)",
                           variable=self.supply_var, value="intra",
                           command=self._on_supply_change).pack(side="left", pady=4)
        ctk.CTkRadioButton(sf, text="Inter-State (IGST)",
                           variable=self.supply_var, value="inter",
                           command=self._on_supply_change).pack(side="left", padx=12)

        supply_note = ctk.CTkLabel(right, text="", text_color="#f39c12",
                                   font=ctk.CTkFont(size=10))
        supply_note.pack(anchor="w", padx=14)
        self._supply_note = supply_note
        ctk.CTkFrame(right, fg_color="transparent", height=8).pack()

        # ── add item row ──────────────────────────────────────────────────────
        add_sec = ctk.CTkFrame(main, fg_color="#16213e", corner_radius=10)
        add_sec.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(add_sec, text="Add Line Item",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#95a5a6").pack(padx=14, pady=(10, 4), anchor="w")

        add_row = ctk.CTkFrame(add_sec, fg_color="transparent")
        add_row.pack(fill="x", padx=14, pady=(0, 10))

        pnames = list(self.product_map.keys())
        self.add_product_var = ctk.StringVar(value=pnames[0] if pnames else "")
        ctk.CTkComboBox(add_row, values=pnames, variable=self.add_product_var,
                        width=240, command=self._on_product_select
                        ).pack(side="left", padx=(0, 4))

        ctk.CTkLabel(add_row, text="Qty:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(8, 2))
        self.add_qty = ctk.CTkEntry(add_row, width=55, height=32)
        self.add_qty.insert(0, "1")
        self.add_qty.pack(side="left", padx=(0, 4))

        ctk.CTkLabel(add_row, text="Rate (₹):", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(8, 2))
        self.add_rate = ctk.CTkEntry(add_row, width=90, height=32)
        self.add_rate.pack(side="left", padx=(0, 4))

        ctk.CTkLabel(add_row, text="GST%:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(8, 2))
        self.add_gst = ctk.StringVar(value="18")
        ctk.CTkComboBox(add_row, values=GST_RATES, variable=self.add_gst,
                        width=70).pack(side="left", padx=(0, 8))
        ctk.CTkButton(add_row, text="Add →", width=90, height=32,
                      fg_color="#0f3460", hover_color="#1a4a8a",
                      command=self._add_item).pack(side="left")

        if pnames:
            self._on_product_select(pnames[0])

        # ── items list ────────────────────────────────────────────────────────
        ctk.CTkLabel(main, text="Invoice Items",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#ecf0f1").pack(padx=20, pady=(0, 4), anchor="w")

        items_outer = ctk.CTkFrame(main, fg_color="#16213e", corner_radius=10)
        items_outer.pack(fill="x", padx=20, pady=(0, 10))

        hdr_row = ctk.CTkFrame(items_outer, fg_color="#0f3460", corner_radius=4)
        hdr_row.pack(fill="x", padx=8, pady=(8, 2))
        for col, w in [("Description", 220), ("HSN", 65), ("Qty", 48), ("Unit", 48),
                       ("Rate", 80), ("Taxable", 90), ("GST", 70), ("Total", 90), ("", 32)]:
            ctk.CTkLabel(hdr_row, text=col, width=w,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#95a5a6").pack(side="left", padx=3, pady=4)

        self._items_scroll = ctk.CTkScrollableFrame(items_outer, fg_color="transparent", height=160)
        self._items_scroll.pack(fill="x", padx=8, pady=(0, 8))
        self._no_items_lbl = ctk.CTkLabel(self._items_scroll, text="No items added yet.",
                                           text_color="#555")
        self._no_items_lbl.pack(pady=16)

        # ── discount ──────────────────────────────────────────────────────────
        disc_row = ctk.CTkFrame(main, fg_color="transparent")
        disc_row.pack(fill="x", padx=20, pady=(0, 4))
        ctk.CTkLabel(disc_row, text="Discount  %",
                     text_color="#95a5a6", font=ctk.CTkFont(size=11)).pack(side="right", padx=(0, 8))
        self.discount_var = ctk.StringVar(value="0")
        disc_entry = ctk.CTkEntry(disc_row, textvariable=self.discount_var, width=70, height=28)
        disc_entry.pack(side="right")
        disc_entry.bind("<KeyRelease>", lambda e: self._draw_totals())

        # ── totals ────────────────────────────────────────────────────────────
        self.totals_frame = ctk.CTkFrame(main, fg_color="#16213e", corner_radius=10)
        self.totals_frame.pack(fill="x", padx=20, pady=(0, 10))
        self._draw_totals()

        # ── buttons ───────────────────────────────────────────────────────────
        btn_row = ctk.CTkFrame(main, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 20))
        ctk.CTkButton(btn_row, text="Cancel",
                      fg_color="#7f1f1f", hover_color="#c0392b",
                      command=self.destroy).pack(side="right")
        ctk.CTkButton(btn_row, text="Save + PDF", width=120,
                      fg_color="#0f3460", hover_color="#1a4a8a",
                      command=lambda: self._save(gen_pdf=True, status="Draft")).pack(side="right", padx=6)
        ctk.CTkButton(btn_row, text="Save & Send", width=120,
                      fg_color="#2355c2", hover_color="#1a4a8a",
                      command=lambda: self._save(gen_pdf=False, status="Sent")).pack(side="right", padx=0)
        ctk.CTkButton(btn_row, text="Save Draft", width=110,
                      fg_color="#2ecc71", hover_color="#27ae60", text_color="#000",
                      command=lambda: self._save(gen_pdf=False, status="Draft")).pack(side="right", padx=6)

        # detect supply type now that all widgets exist
        self._auto_supply_type(self.client_var.get())

    # ── helpers ───────────────────────────────────────────────────────────────

    def _on_product_select(self, name):
        p = self.product_map.get(name)
        if not p:
            return
        self.add_rate.delete(0, "end")
        self.add_rate.insert(0, str(p["unit_price"]))
        self.add_gst.set(str(int(p.get("gst_rate", 18))))

    def _auto_supply_type(self, client_name=None):
        client = self.client_map.get(client_name or self.client_var.get())
        firm   = self.firm
        if client and firm and client["state"] and firm["state"]:
            same = client["state"] == firm["state"]
            self.supply_var.set("intra" if same else "inter")
            self._supply_note.configure(
                text=f"Auto-detected: {'Intra' if same else 'Inter'}-state "
                     f"({firm['state']} vs {client['state']})"
            )
        self._on_supply_change()

    def _on_supply_change(self):
        self._refresh_items_display()
        self._draw_totals()

    def _add_item(self):
        p_key = self.add_product_var.get()
        p     = self.product_map.get(p_key)
        try:
            qty      = float(self.add_qty.get())
            rate     = float(self.add_rate.get())
            gst_rate = float(self.add_gst.get())
        except ValueError:
            messagebox.showerror("Error", "Enter valid numeric values for Qty, Rate, and GST%.")
            return
        if qty <= 0:
            messagebox.showerror("Error", "Quantity must be greater than 0.")
            return
        self.items.append({
            "description": p["name"] if p else p_key,
            "hsn_code":    p["hsn_code"] if p else "",
            "quantity":    qty,
            "unit":        p["unit"] if p else "pcs",
            "unit_price":  rate,
            "gst_rate":    gst_rate,
            "product_id":  p["id"] if p else None,
        })
        self._refresh_items_display()
        self._draw_totals()

    def _refresh_items_display(self):
        if not self._items_scroll:
            return
        for w in self._items_scroll.winfo_children():
            w.destroy()
        if not self.items:
            ctk.CTkLabel(self._items_scroll, text="No items added yet.",
                         text_color="#555").pack(pady=16)
            return
        supply = self.supply_var.get()
        for idx, it in enumerate(self.items):
            taxable  = round(it["quantity"] * it["unit_price"], 2)
            gst_rate = it["gst_rate"]
            tax      = round(taxable * gst_rate / 100, 2)
            total    = round(taxable + tax, 2)
            gst_str  = f"C+S {gst_rate}%" if supply == "intra" else f"IGST {gst_rate}%"

            row = ctk.CTkFrame(self._items_scroll, fg_color="#16213e", corner_radius=4)
            row.pack(fill="x", pady=1)
            for val, w in [
                (it["description"][:28], 220), (it["hsn_code"] or "—", 65),
                (f"{it['quantity']:g}", 48),   (it["unit"], 48),
                (f"₹{it['unit_price']:,.2f}", 80),
                (f"₹{taxable:,.2f}", 90), (gst_str, 70), (f"₹{total:,.2f}", 90),
            ]:
                ctk.CTkLabel(row, text=str(val), width=w,
                             font=ctk.CTkFont(size=10),
                             text_color="#ecf0f1").pack(side="left", padx=3, pady=4)
            ctk.CTkButton(row, text="✕", width=28, height=24,
                          fg_color="#7f1f1f", hover_color="#c0392b",
                          font=ctk.CTkFont(size=10),
                          command=lambda i=idx: self._remove_item(i)
                          ).pack(side="left", padx=2)

    def _remove_item(self, idx):
        self.items.pop(idx)
        self._refresh_items_display()
        self._draw_totals()

    def _draw_totals(self):
        if not hasattr(self, "totals_frame"):
            return
        for w in self.totals_frame.winfo_children():
            w.destroy()
        supply   = self.supply_var.get()
        subtotal = cgst = sgst = igst = 0.0
        for it in self.items:
            taxable  = round(it["quantity"] * it["unit_price"], 2)
            gst_rate = it["gst_rate"]
            subtotal += taxable
            if supply == "intra":
                half  = round(taxable * gst_rate / 2 / 100, 2)
                cgst += half
                sgst += half
            else:
                igst += round(taxable * gst_rate / 100, 2)
        pre_discount = round(subtotal + cgst + sgst + igst, 2)
        try:
            disc_pct = max(0.0, min(100.0, float(self.discount_var.get())))
        except (ValueError, AttributeError):
            disc_pct = 0.0
        disc_amt = round(pre_discount * disc_pct / 100, 2)
        grand = round(pre_discount - disc_amt, 2)

        summary = [("Taxable Amount:", f"₹ {subtotal:,.2f}", "#ecf0f1")]
        if supply == "intra":
            summary += [("CGST:", f"₹ {cgst:,.2f}", "#f39c12"),
                        ("SGST:", f"₹ {sgst:,.2f}", "#f39c12")]
        else:
            summary += [("IGST:", f"₹ {igst:,.2f}", "#f39c12")]
        if disc_pct > 0:
            summary.append((f"Discount ({disc_pct:g}%):", f"- ₹ {disc_amt:,.2f}", "#e74c3c"))
        summary.append(("GRAND TOTAL:", f"₹ {grand:,.2f}", "#2ecc71"))

        col = ctk.CTkFrame(self.totals_frame, fg_color="transparent")
        col.pack(anchor="e", padx=20, pady=10)
        for label, val, color in summary:
            r = ctk.CTkFrame(col, fg_color="transparent")
            r.pack(anchor="e", pady=1)
            ctk.CTkLabel(r, text=label, width=160, text_color="#95a5a6",
                         font=ctk.CTkFont(size=11)).pack(side="left")
            bold = "bold" if label == "GRAND TOTAL:" else "normal"
            ctk.CTkLabel(r, text=val, width=130, text_color=color,
                         font=ctk.CTkFont(size=12, weight=bold),
                         anchor="e").pack(side="left")

    # ── save ──────────────────────────────────────────────────────────────────

    def _save(self, gen_pdf=False, status="Draft"):
        invoice_number = self.inv_num.get().strip()
        client_name    = self.client_var.get().strip()
        inv_date       = self.inv_date.get().strip()

        if not invoice_number or not client_name or not inv_date:
            messagebox.showerror("Error", "Invoice number, client, and date are required.")
            return
        if not self.items:
            messagebox.showerror("Error", "Add at least one line item.")
            return
        client = self.client_map.get(client_name)
        if not client:
            messagebox.showerror("Error", "Select a valid client.")
            return

        # Credit limit check (warn, don't block)
        credit_limit = client.get("credit_limit") or 0
        if credit_limit > 0:
            outstanding = db.get_client_outstanding(client["id"])
            # Estimate this invoice's grand total
            supply = self.supply_var.get()
            inv_total = 0.0
            for it in self.items:
                taxable = round(it["quantity"] * it["unit_price"], 2)
                inv_total += taxable + round(taxable * it["gst_rate"] / 100, 2)
            if outstanding + inv_total > credit_limit:
                proceed = messagebox.askyesno(
                    "⚠ Credit Limit Exceeded",
                    f"Client '{client_name}' has a credit limit of ₹{credit_limit:,.0f}.\n"
                    f"Current outstanding: ₹{outstanding:,.0f}\n"
                    f"This invoice amount: ₹{inv_total:,.0f}\n"
                    f"Total after invoice: ₹{outstanding + inv_total:,.0f}\n\n"
                    "This exceeds the credit limit. Save anyway?",
                )
                if not proceed:
                    return

        try:
            disc_pct = max(0.0, min(100.0, float(self.discount_var.get())))
        except ValueError:
            disc_pct = 0.0
        try:
            inv_id = db.create_invoice(
                invoice_number=invoice_number,
                client_id=client["id"],
                invoice_date=inv_date,
                due_date=self.inv_due.get().strip(),
                supply_type=self.supply_var.get(),
                items=self.items,
                notes=self.notes_var.get(),
                status=status,
                discount_pct=disc_pct,
            )
        except Exception as e:
            messagebox.showerror("Save Error", str(e))
            return

        if gen_pdf:
            inv, items, firm = db.get_invoice_full(inv_id)
            inv_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Invoices")
            os.makedirs(inv_dir, exist_ok=True)
            out = os.path.join(inv_dir, f"{invoice_number}.pdf")
            try:
                from invoice_pdf import generate_invoice_pdf
                generate_invoice_pdf(dict(inv), [dict(i) for i in items], dict(firm), out)
                if sys.platform == "win32":
                    os.startfile(out)
                else:
                    subprocess.run(["xdg-open", out])
                messagebox.showinfo("Invoice Saved", f"PDF saved to:\n{out}")
            except Exception as e:
                messagebox.showerror("PDF Error", f"Invoice saved but PDF failed:\n{e}")
        else:
            messagebox.showinfo("Saved", f"Invoice {invoice_number} saved as {status}.")

        self.app.refresh_current()
        self.destroy()


# ── Settings Page ──────────────────────────────────────────────────────────────

class SettingsPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)

    # ── layout helpers ────────────────────────────────────────────────────────

    def _section(self, parent, title):
        f = ctk.CTkFrame(parent, fg_color="#16213e", corner_radius=10)
        f.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#3498db").pack(padx=16, pady=(12, 4), anchor="w")
        return f

    def _field(self, parent, label, default=""):
        ctk.CTkLabel(parent, text=label, text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(6, 0))
        var = ctk.StringVar(value=str(default or ""))
        ctk.CTkEntry(parent, textvariable=var).pack(fill="x", padx=16, pady=(2, 0))
        return var

    def _half_fields(self, parent, pairs):
        fr = ctk.CTkFrame(parent, fg_color="transparent")
        fr.pack(fill="x", padx=16, pady=(6, 0))
        fr.columnconfigure(0, weight=1)
        fr.columnconfigure(1, weight=1)
        vars_ = []
        for col_idx, (label, default) in enumerate(pairs):
            col = ctk.CTkFrame(fr, fg_color="transparent")
            col.grid(row=0, column=col_idx, padx=(0 if col_idx == 0 else 8, 0), sticky="ew")
            ctk.CTkLabel(col, text=label, text_color="#95a5a6",
                         font=ctk.CTkFont(size=11)).pack(anchor="w")
            var = ctk.StringVar(value=str(default or ""))
            ctk.CTkEntry(col, textvariable=var).pack(fill="x")
            vars_.append(var)
        return vars_

    # ── validation ────────────────────────────────────────────────────────────

    def _validate_gstin(self, *_):
        try:
            g = self._gstin_var.get().strip().upper()
            if not g:
                self._gstin_lbl.configure(text="", text_color="#95a5a6")
            elif re.fullmatch(r"\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d]", g):
                self._gstin_lbl.configure(text="✓ Valid GSTIN format", text_color="#2ecc71")
            else:
                self._gstin_lbl.configure(
                    text=f"✗ Must be 15 chars — e.g. 29ABCDE1234F1Z5  ({len(g)} now)",
                    text_color="#e74c3c")
        except Exception:
            pass

    def _validate_ifsc(self, *_):
        try:
            v = self._ifsc_var.get().strip().upper()
            if not v:
                self._ifsc_lbl.configure(text="", text_color="#95a5a6")
            elif re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", v):
                self._ifsc_lbl.configure(text="✓ Valid IFSC format", text_color="#2ecc71")
            else:
                self._ifsc_lbl.configure(
                    text="✗ Format: 4 letters + 0 + 6 alphanumeric  (e.g. SBIN0005943)",
                    text_color="#e74c3c")
        except Exception:
            pass

    # ── preview ───────────────────────────────────────────────────────────────

    def _refresh_preview(self, *_):
        try:
            name  = self._firm_name_var.get() or "Your Firm Name"
            city  = self._city_var.get()
            state = self._firm_state.get()
            gstin = self._gstin_var.get().strip().upper()
            phone = self._firm_phone_var.get()
            parts = [p for p in [city, state] if p]
            detail = "  |  ".join(p for p in [
                ", ".join(parts),
                f"GSTIN: {gstin}" if gstin else "",
                f"Ph: {phone}" if phone else "",
            ] if p) or "— Add address details —"
            self._prev_name_lbl.configure(text=name)
            self._prev_detail_lbl.configure(text=detail)
        except Exception:
            pass

    # ── data management ───────────────────────────────────────────────────────

    def _quick_backup(self):
        try:
            path = db.auto_backup()
            messagebox.showinfo("Backup Complete",
                                f"Backup saved to:\n{path}\n\nOlder backups beyond 7 are removed automatically.")
            self.refresh()
        except Exception as e:
            messagebox.showerror("Backup Failed", str(e))

    def _backup_db(self):
        import shutil
        path = filedialog.asksaveasfilename(
            title="Save Database Backup",
            defaultextension=".db",
            initialfile=f"accounting_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
            filetypes=[("SQLite Database", "*.db"), ("All files", "*.*")])
        if not path:
            return
        shutil.copy(db.DB_PATH, path)
        messagebox.showinfo("Backup Complete", f"Database backed up to:\n{path}")

    def _restore_db(self):
        import shutil
        path = filedialog.askopenfilename(
            title="Select Backup File to Restore",
            filetypes=[("SQLite Database", "*.db"), ("All files", "*.*")])
        if not path:
            return
        if not messagebox.askyesno("Confirm Restore",
                "⚠  This will OVERWRITE your current database with the backup.\n\n"
                "All data entered after the backup was created will be LOST.\n\n"
                "Are you absolutely sure you want to continue?"):
            return
        shutil.copy(path, db.DB_PATH)
        messagebox.showinfo("Restore Complete",
                            "Database restored.\n\nPlease close and reopen the app for changes to take effect.")

    def _export_all(self):
        path = filedialog.asksaveasfilename(
            title="Export All Data to Excel",
            defaultextension=".xlsx",
            initialfile=f"accounting_export_{datetime.now().strftime('%Y%m%d')}.xlsx",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")])
        if not path:
            return
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill
            wb = openpyxl.Workbook()
            wb.remove(wb.active)
            hdr_font = Font(bold=True, color="FFFFFF")
            hdr_fill = PatternFill("solid", fgColor="1a3a5c")

            def add_sheet(ws_name, rows, hdrs):
                ws = wb.create_sheet(ws_name)
                ws.append(hdrs)
                for cell in ws[1]:
                    cell.font = hdr_font
                    cell.fill = hdr_fill
                for r in rows:
                    d = dict(r)
                    ws.append([d.get(h, "") for h in hdrs])

            add_sheet("Clients", db.get_all_clients(),
                      ["id","name","email","phone","address","gstin","state","created_at"])
            add_sheet("Products", db.get_all_products(),
                      ["id","name","sku","unit_price","stock_quantity","unit","hsn_code","gst_rate"])
            add_sheet("Invoices", db.get_all_invoices(),
                      ["id","invoice_number","client_name","invoice_date","due_date",
                       "subtotal","cgst_total","sgst_total","igst_total","grand_total","status"])

            with db.get_connection() as conn:
                exps = conn.execute("""
                    SELECT je.entry_date, la_e.name AS expense_account, la_c.name AS paid_from,
                           je.narration, jl.debit AS amount
                    FROM journal_entries je
                    JOIN journal_entry_lines jl  ON jl.journal_id  = je.id
                    JOIN ledger_accounts la_e    ON la_e.id        = jl.account_id  AND la_e.account_type = 'Expense'
                    JOIN journal_entry_lines jl2 ON jl2.journal_id = je.id          AND jl2.account_id != jl.account_id
                    JOIN ledger_accounts la_c    ON la_c.id        = jl2.account_id
                    WHERE jl.debit > 0
                    ORDER BY je.entry_date DESC
                """).fetchall()
            add_sheet("Expenses", exps, ["entry_date","expense_account","paid_from","narration","amount"])

            wb.save(path)
            messagebox.showinfo("Export Complete", f"All data exported to:\n{path}")
            try:
                os.startfile(path)
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    # ── main refresh ──────────────────────────────────────────────────────────

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._header("Settings", "Firm configuration, app preferences, and data management")

        firm = dict(db.get_firm_settings() or {})

        # Bottom save bar (pack before tabview so it stays anchored)
        bar = ctk.CTkFrame(self, fg_color="#0d1117", corner_radius=0)
        bar.pack(fill="x", side="bottom")
        ctk.CTkButton(bar, text="💾  Save Settings", width=200, height=40,
                      fg_color="#2ecc71", hover_color="#27ae60", text_color="#000",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=self._save).pack(side="right", padx=16, pady=8)
        self._saved_lbl = ctk.CTkLabel(bar, text="", font=ctk.CTkFont(size=11),
                                        text_color="#7f8c8d")
        self._saved_lbl.pack(side="right", padx=4, pady=8)

        # Tabview
        tabs = ctk.CTkTabview(self, fg_color="#16213e")
        tabs.pack(fill="both", expand=True, padx=24, pady=(0, 4))
        t1 = tabs.add("🏢  Firm")
        t2 = tabs.add("🏦  Bank")
        t3 = tabs.add("📋  Preferences")
        t4 = tabs.add("💾  Data")
        t6 = tabs.add("🧾  E-Invoice")
        self._build_einvoice_tab(t6, firm)
        t7 = tabs.add("🚚  E-Way Bill")
        self._build_ewb_tab(t7, firm)
        t8 = tabs.add("📧  Email")
        self._build_email_tab(t8, firm)
        t9 = tabs.add("🖨  Printer")
        self._build_printer_tab(t9)
        is_admin = self.app.current_user.get("role") == "admin"
        if is_admin:
            t5 = tabs.add("👥  Users")
            self._build_users_tab(t5)

        # ── Tab 1: Firm ───────────────────────────────────────────────────────
        sc1 = ctk.CTkScrollableFrame(t1, fg_color="transparent")
        sc1.pack(fill="both", expand=True)

        # Live preview card
        pv = ctk.CTkFrame(sc1, fg_color="#0d1b2a", corner_radius=8,
                          border_width=1, border_color="#2c3e50")
        pv.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(pv, text="  Invoice Header Preview",
                     font=ctk.CTkFont(size=9), text_color="#555").pack(anchor="w", padx=10, pady=(6, 0))
        self._prev_name_lbl = ctk.CTkLabel(pv, text=firm.get("firm_name", "") or "Your Firm Name",
                                            font=ctk.CTkFont(size=14, weight="bold"),
                                            text_color="#3498db")
        self._prev_name_lbl.pack(anchor="w", padx=10)
        self._prev_detail_lbl = ctk.CTkLabel(pv, text="", font=ctk.CTkFont(size=10),
                                              text_color="#95a5a6")
        self._prev_detail_lbl.pack(anchor="w", padx=10, pady=(0, 8))

        f1 = self._section(sc1, "🏢  Firm Details")
        self._firm_name_var = self._field(f1, "Firm Name *", firm.get("firm_name", ""))
        self._firm_name_var.trace_add("write", self._refresh_preview)
        self._address_var = self._field(f1, "Address", firm.get("address", ""))

        v = self._half_fields(f1, [("City", firm.get("city", "")), ("Pincode", firm.get("pincode", ""))])
        self._city_var, self._pincode_var = v

        ctk.CTkLabel(f1, text="State", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(6, 0))
        self._firm_state = ctk.StringVar(value=firm.get("state", "") or "")
        ctk.CTkComboBox(f1, values=INDIAN_STATES, variable=self._firm_state
                        ).pack(fill="x", padx=16, pady=(2, 0))
        self._firm_state.trace_add("write", self._refresh_preview)

        ctk.CTkLabel(f1, text="GSTIN (15-digit)", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(6, 0))
        self._gstin_var = ctk.StringVar(value=firm.get("gstin", "") or "")
        ctk.CTkEntry(f1, textvariable=self._gstin_var).pack(fill="x", padx=16, pady=(2, 0))
        self._gstin_lbl = ctk.CTkLabel(f1, text="", font=ctk.CTkFont(size=10))
        self._gstin_lbl.pack(anchor="w", padx=16)
        self._gstin_var.trace_add("write", self._validate_gstin)
        self._gstin_var.trace_add("write", self._refresh_preview)
        self._validate_gstin()

        v = self._half_fields(f1, [("Phone", firm.get("phone", "")), ("Email", firm.get("email", ""))])
        self._firm_phone_var, self._firm_email_var = v
        self._firm_phone_var.trace_add("write", self._refresh_preview)
        ctk.CTkFrame(f1, fg_color="transparent", height=10).pack()
        self._refresh_preview()

        # ── Tab 2: Bank ───────────────────────────────────────────────────────
        sc2 = ctk.CTkScrollableFrame(t2, fg_color="transparent")
        sc2.pack(fill="both", expand=True)

        f2 = self._section(sc2, "🏦  Bank Details")
        self._bank_name_var    = self._field(f2, "Bank Name",      firm.get("bank_name", ""))
        self._bank_account_var = self._field(f2, "Account Number", firm.get("bank_account", ""))

        ctk.CTkLabel(f2, text="IFSC Code", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(6, 0))
        self._ifsc_var = ctk.StringVar(value=firm.get("bank_ifsc", "") or "")
        ctk.CTkEntry(f2, textvariable=self._ifsc_var).pack(fill="x", padx=16, pady=(2, 0))
        self._ifsc_lbl = ctk.CTkLabel(f2, text="", font=ctk.CTkFont(size=10))
        self._ifsc_lbl.pack(anchor="w", padx=16)
        self._ifsc_var.trace_add("write", self._validate_ifsc)
        self._validate_ifsc()

        self._bank_branch_var = self._field(f2, "Branch", firm.get("bank_branch", ""))

        f2b = self._section(sc2, "📱  UPI Payment")
        ctk.CTkLabel(f2b, text="  UPI ID lets clients scan a QR code on the invoice to pay instantly.",
                     font=ctk.CTkFont(size=10), text_color="#7f8c8d").pack(anchor="w", padx=16, pady=(0, 4))
        self._upi_id_var = self._field(f2b, "UPI ID  (e.g. yourname@upi)", firm.get("upi_id", ""))
        ctk.CTkLabel(f2b, text="  Leave blank to hide the QR code from invoices.",
                     font=ctk.CTkFont(size=10), text_color="#7f8c8d").pack(anchor="w", padx=16, pady=(0, 8))
        ctk.CTkFrame(f2b, fg_color="transparent", height=4).pack()

        # ── Tab 3: Preferences ────────────────────────────────────────────────
        sc3 = ctk.CTkScrollableFrame(t3, fg_color="transparent")
        sc3.pack(fill="both", expand=True)

        f3a = self._section(sc3, "🧾  Invoice Settings")
        self._inv_prefix_var = self._field(f3a, "Invoice Number Prefix  (e.g. INV, BILL, GEN)",
                                            firm.get("invoice_prefix", "INV") or "INV")
        ctk.CTkLabel(f3a, text="  Numbers will appear as:  PREFIX-2025-0001",
                     font=ctk.CTkFont(size=10), text_color="#7f8c8d").pack(anchor="w", padx=16, pady=(0, 4))
        v = self._half_fields(f3a, [
            ("Default Payment Due (days)", str(firm.get("default_due_days", 30) or 30)),
            ("Default GST Rate (%)",       str(firm.get("default_gst_rate",  18) or 18)),
        ])
        self._due_days_var, self._gst_rate_var = v
        ctk.CTkFrame(f3a, fg_color="transparent", height=8).pack()

        f3b = self._section(sc3, "📅  Fiscal Year")
        ctk.CTkLabel(f3b, text="Start Month", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(6, 0))
        _months = [
            "1 – January",   "2 – February",   "3 – March",
            "4 – April  (India standard)",
            "5 – May",       "6 – June",        "7 – July",
            "8 – August",    "9 – September",   "10 – October",
            "11 – November", "12 – December",
        ]
        fy_num = str(firm.get("fiscal_year_start", 4) or 4)
        default_fy = next((m for m in _months if m.startswith(fy_num + " ") or m.startswith(fy_num + "–")), _months[3])
        self._fy_start_var = ctk.StringVar(value=default_fy)
        ctk.CTkComboBox(f3b, values=_months, variable=self._fy_start_var,
                        width=300).pack(anchor="w", padx=16, pady=(2, 0))
        ctk.CTkLabel(f3b, text="  Used for default date ranges in reports",
                     font=ctk.CTkFont(size=10), text_color="#7f8c8d").pack(anchor="w", padx=16, pady=(2, 8))

        f3c = self._section(sc3, "📝  Document Defaults")
        self._sig_name_var = self._field(f3c, "Authorised Signatory Name", firm.get("signature_name", ""))
        ctk.CTkLabel(f3c, text="Terms & Conditions (one per line)",
                     text_color="#95a5a6", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(10, 0))
        self._terms_box = ctk.CTkTextbox(f3c, height=100, font=ctk.CTkFont(size=11))
        self._terms_box.pack(fill="x", padx=16, pady=(2, 0))
        self._terms_box.insert("1.0", firm.get("terms", "") or "")
        ctk.CTkFrame(f3c, fg_color="transparent", height=10).pack()

        # ── Tab 4: Data ───────────────────────────────────────────────────────
        sc4 = ctk.CTkScrollableFrame(t4, fg_color="transparent")
        sc4.pack(fill="both", expand=True)

        f4a = self._section(sc4, "🗂  Database Backup & Restore")

        # Last backup info
        backups = db.list_backups()
        if backups:
            last = backups[0]
            info_text = f"Last backup:  {last['modified']}  ({last['size_kb']} KB)  —  {len(backups)} backup(s) stored"
            info_color = "#2ecc71"
        else:
            info_text = "No backups found. Create your first backup now."
            info_color = "#e67e22"
        ctk.CTkLabel(f4a, text=info_text, text_color=info_color,
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(6, 4))
        ctk.CTkLabel(f4a,
                     text=f"Backup folder:  {db.get_backup_folder()}",
                     text_color="#7f8c8d", font=ctk.CTkFont(size=10),
                     justify="left").pack(anchor="w", padx=16, pady=(0, 8))

        btn_row = ctk.CTkFrame(f4a, fg_color="transparent")
        btn_row.pack(anchor="w", padx=16, pady=(0, 8))
        ctk.CTkButton(btn_row, text="⚡  Quick Backup", width=160,
                      fg_color="#1a4a2a", hover_color="#27ae60",
                      command=self._quick_backup).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="⬇  Export Backup…", width=160,
                      fg_color="#1a3a5c", hover_color="#2980b9",
                      command=self._backup_db).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="⬆  Restore…", width=130,
                      fg_color="#4a1a1a", hover_color="#922b21",
                      command=self._restore_db).pack(side="left")

        # Recent backups list
        if backups:
            ctk.CTkLabel(f4a, text="Recent backups:", text_color="#95a5a6",
                         font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=16, pady=(8, 2))
            for b in backups[:5]:
                row = ctk.CTkFrame(f4a, fg_color="#0d1117", corner_radius=6)
                row.pack(fill="x", padx=16, pady=2)
                ctk.CTkLabel(row, text=b["modified"], font=ctk.CTkFont(size=11),
                             text_color="#ecf0f1").pack(side="left", padx=10, pady=5)
                ctk.CTkLabel(row, text=f"{b['size_kb']} KB", font=ctk.CTkFont(size=10),
                             text_color="#7f8c8d").pack(side="right", padx=10)
        ctk.CTkFrame(f4a, fg_color="transparent", height=8).pack()

        f4b = self._section(sc4, "📤  Export All Data")
        ctk.CTkLabel(f4b,
                     text="Export every table (clients, products, invoices, expenses) to a single\n"
                          "Excel workbook — useful for analysis or as a human-readable backup.",
                     text_color="#7f8c8d", font=ctk.CTkFont(size=11),
                     justify="left").pack(anchor="w", padx=16, pady=(4, 10))
        ctk.CTkButton(f4b, text="📊  Export All to Excel", width=200,
                      fg_color="#1a3a2a", hover_color="#27ae60",
                      command=self._export_all).pack(anchor="w", padx=16, pady=(0, 12))

        f4c = self._section(sc4, "🔄  Import from Tally")
        ctk.CTkLabel(f4c,
                     text="Import Clients, Products, and Invoices from a Tally ERP 9 or\n"
                          "Tally Prime XML export file.",
                     text_color="#7f8c8d", font=ctk.CTkFont(size=11),
                     justify="left").pack(anchor="w", padx=16, pady=(4, 10))
        ctk.CTkButton(f4c, text="🔄  Open Tally Import…", width=200,
                      fg_color="#1a3a5c", hover_color="#2355c2",
                      command=lambda: TallyImportDialog(self, self.app)
                      ).pack(anchor="w", padx=16, pady=(0, 12))

    # ── E-Invoice Tab ─────────────────────────────────────────────────────────

    def _build_einvoice_tab(self, parent, firm):
        sc = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        sc.pack(fill="both", expand=True)

        f = self._section(sc, "🧾  IRP / NIC E-Invoice Credentials")
        ctk.CTkLabel(
            f,
            text=(
                "  E-invoicing is mandatory for GST-registered businesses with turnover > ₹5 Cr.\n"
                "  Register on einvoice1.nic.in to get your Client ID, Client Secret and credentials."
            ),
            font=ctk.CTkFont(size=10), text_color="#7f8c8d", justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 8))

        self._irp_client_id_var     = self._field(f, "Client ID",     firm.get("irp_client_id", ""))
        self._irp_client_secret_var = self._field(f, "Client Secret", firm.get("irp_client_secret", ""))
        self._irp_username_var      = self._field(f, "IRP Username (GSTIN login)", firm.get("irp_username", ""))

        ctk.CTkLabel(f, text="IRP Password", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(6, 0))
        self._irp_password_var = ctk.StringVar(value=firm.get("irp_password", ""))
        ctk.CTkEntry(f, textvariable=self._irp_password_var, show="•"
                     ).pack(fill="x", padx=16, pady=(2, 0))

        ctk.CTkLabel(f, text="Mode", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(10, 0))
        self._einvoice_sandbox_var = ctk.StringVar(
            value="Sandbox (Testing)" if firm.get("einvoice_sandbox", 1) else "Production"
        )
        ctk.CTkComboBox(f, values=["Sandbox (Testing)", "Production"],
                        variable=self._einvoice_sandbox_var
                        ).pack(fill="x", padx=16, pady=(2, 0))

        ctk.CTkLabel(
            f,
            text=(
                "  ⚠  Use Sandbox mode for testing. Switch to Production only when live.\n"
                "  Sandbox URL: einvoice1-sandbox.nic.in  |  Production: einvoice1.nic.in"
            ),
            font=ctk.CTkFont(size=10), text_color="#e67e22", justify="left",
        ).pack(anchor="w", padx=16, pady=(4, 12))

        fi = self._section(sc, "ℹ️  How to Get IRP Credentials")
        for step in [
            "1.  Visit einvoice1.nic.in and log in with your GSTIN credentials.",
            "2.  Go to 'API Registration' → Register your application.",
            "3.  You will receive a Client ID and Client Secret via email.",
            "4.  Enter them above and click 💾 Save Settings.",
            "5.  Use the 'Generate IRN' button on any invoice to test.",
        ]:
            ctk.CTkLabel(fi, text=step, font=ctk.CTkFont(size=11),
                         text_color="#bdc3c7", justify="left"
                         ).pack(anchor="w", padx=16, pady=2)
        ctk.CTkFrame(fi, fg_color="transparent", height=8).pack()

    # ── E-Way Bill Tab ────────────────────────────────────────────────────────

    def _build_ewb_tab(self, parent, firm):
        sc = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        sc.pack(fill="both", expand=True)

        f = self._section(sc, "🚚  E-Way Bill Credentials")
        ctk.CTkLabel(
            f,
            text=(
                "  E-Way Bill is mandatory for movement of goods worth > ₹50,000.\n"
                "  Register on ewaybillgst.gov.in using your GSTIN login."
            ),
            font=ctk.CTkFont(size=10), text_color="#7f8c8d", justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 8))

        self._ewb_username_var = self._field(f, "EWB Username (GSTIN login)",
                                             firm.get("ewb_username", ""))

        ctk.CTkLabel(f, text="EWB Password", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(6, 0))
        self._ewb_password_var = ctk.StringVar(value=firm.get("ewb_password", ""))
        ctk.CTkEntry(f, textvariable=self._ewb_password_var, show="•"
                     ).pack(fill="x", padx=16, pady=(2, 0))

        ctk.CTkLabel(f, text="Mode", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(10, 0))
        self._ewb_sandbox_var = ctk.StringVar(
            value="Sandbox (Testing)" if firm.get("ewb_sandbox", 1) else "Production"
        )
        ctk.CTkComboBox(f, values=["Sandbox (Testing)", "Production"],
                        variable=self._ewb_sandbox_var
                        ).pack(fill="x", padx=16, pady=(2, 0))

        ctk.CTkLabel(
            f,
            text=(
                "  ⚠  Use Sandbox mode for testing. Switch to Production only when live.\n"
                "  Sandbox: ewaybill-sandbox.nic.in  |  Production: ewaybillgst.gov.in"
            ),
            font=ctk.CTkFont(size=10), text_color="#e67e22", justify="left",
        ).pack(anchor="w", padx=16, pady=(4, 12))

        fi = self._section(sc, "ℹ️  How to Get EWB Credentials")
        for step in [
            "1.  Visit ewaybillgst.gov.in and log in with your GSTIN credentials.",
            "2.  Go to 'Registration' → 'For SMS' or 'For API' to enable API access.",
            "3.  Your username is your GSTIN and password is set during registration.",
            "4.  Enter them above and click 💾 Save Settings.",
            "5.  Use the '🚚 EWB' button on any invoice to generate an E-Way Bill.",
        ]:
            ctk.CTkLabel(fi, text=step, font=ctk.CTkFont(size=11),
                         text_color="#bdc3c7", justify="left"
                         ).pack(anchor="w", padx=16, pady=2)
        ctk.CTkFrame(fi, fg_color="transparent", height=8).pack()

    def _build_email_tab(self, parent, firm):
        sc = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        sc.pack(fill="both", expand=True)

        f = self._section(sc, "📧  Outgoing Email (SMTP)")
        ctk.CTkLabel(
            f,
            text=(
                "  Configure your outgoing mail server to send invoice emails directly.\n"
                "  Gmail: use smtp.gmail.com port 587 with an App Password\n"
                "  (Google Account → Security → 2-Step Verification → App passwords)."
            ),
            font=ctk.CTkFont(size=10), text_color="#7f8c8d", justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 10))

        self._smtp_host_var = self._field(f, "SMTP Host", firm.get("smtp_host", "smtp.gmail.com"))
        self._smtp_port_var = self._field(f, "SMTP Port", str(firm.get("smtp_port", 587)))
        self._smtp_user_var = self._field(f, "Login / Username (email address)", firm.get("smtp_user", ""))
        self._smtp_from_name_var = self._field(f, "From Name (shown to recipient)", firm.get("smtp_from_name", ""))

        ctk.CTkLabel(f, text="Password / App Password", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(6, 0))
        self._smtp_password_var = ctk.StringVar(value=firm.get("smtp_password", ""))
        ctk.CTkEntry(f, textvariable=self._smtp_password_var, show="•"
                     ).pack(fill="x", padx=16, pady=(2, 0))

        ctk.CTkLabel(f, text="Encryption", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(10, 0))
        self._smtp_tls_var = ctk.StringVar(
            value="STARTTLS (port 587)" if firm.get("smtp_tls", 1) else "SSL/TLS (port 465)"
        )
        ctk.CTkComboBox(f, values=["STARTTLS (port 587)", "SSL/TLS (port 465)"],
                        variable=self._smtp_tls_var).pack(fill="x", padx=16, pady=(2, 0))

        test_row = ctk.CTkFrame(f, fg_color="transparent")
        test_row.pack(fill="x", padx=16, pady=(14, 4))
        self._smtp_test_lbl = ctk.CTkLabel(test_row, text="", font=ctk.CTkFont(size=11))
        self._smtp_test_lbl.pack(side="left")
        ctk.CTkButton(test_row, text="🔌 Test Connection", width=160,
                      fg_color="#1a3a5c", hover_color="#2355c2",
                      command=self._test_smtp).pack(side="right")

        ctk.CTkFrame(f, fg_color="transparent", height=12).pack()

    def _test_smtp(self):
        import smtplib, ssl
        host = self._smtp_host_var.get().strip()
        user = self._smtp_user_var.get().strip()
        pwd  = self._smtp_password_var.get()
        tls  = "STARTTLS" in self._smtp_tls_var.get()
        try:
            port = int(self._smtp_port_var.get().strip())
        except ValueError:
            port = 587 if tls else 465
        self._smtp_test_lbl.configure(text="Testing…", text_color="#f39c12")
        self.update_idletasks()
        try:
            if tls:
                s = smtplib.SMTP(host, port, timeout=10)
                s.ehlo(); s.starttls(context=ssl.create_default_context()); s.ehlo()
            else:
                s = smtplib.SMTP_SSL(host, port, timeout=10,
                                     context=ssl.create_default_context())
            if user and pwd:
                s.login(user, pwd)
            s.quit()
            self._smtp_test_lbl.configure(text="✓ Connection OK", text_color=COLORS["success"])
        except Exception as e:
            self._smtp_test_lbl.configure(text=f"✗ {e}", text_color=COLORS["danger"])

    # ── save ──────────────────────────────────────────────────────────────────

    def _save(self):
        name = self._firm_name_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Firm name is required.")
            return
        try:
            due_days = int(self._due_days_var.get().strip() or 30)
        except ValueError:
            messagebox.showerror("Error", "Default due days must be a whole number."); return
        try:
            gst_rate = float(self._gst_rate_var.get().strip() or 18)
        except ValueError:
            messagebox.showerror("Error", "Default GST rate must be a number."); return

        raw_fy = self._fy_start_var.get().strip().split("–")[0].split("—")[0].strip()
        try:
            fy_start = int(raw_fy)
        except ValueError:
            fy_start = 4

        sandbox_val = 1 if "Sandbox" in self._einvoice_sandbox_var.get() else 0
        ewb_sandbox_val = 1 if "Sandbox" in self._ewb_sandbox_var.get() else 0

        db.save_firm_settings(
            firm_name       = name,
            address         = self._address_var.get(),
            city            = self._city_var.get(),
            state           = self._firm_state.get(),
            pincode         = self._pincode_var.get(),
            gstin           = self._gstin_var.get().strip().upper(),
            phone           = self._firm_phone_var.get(),
            email           = self._firm_email_var.get(),
            bank_name       = self._bank_name_var.get(),
            bank_account    = self._bank_account_var.get(),
            bank_ifsc       = self._ifsc_var.get().strip().upper(),
            bank_branch     = self._bank_branch_var.get(),
            terms           = self._terms_box.get("1.0", "end").strip(),
            signature_name  = self._sig_name_var.get(),
            invoice_prefix  = self._inv_prefix_var.get().strip() or "INV",
            default_due_days= due_days,
            default_gst_rate= gst_rate,
            fiscal_year_start= fy_start,
            upi_id          = self._upi_id_var.get().strip(),
            irp_client_id     = self._irp_client_id_var.get().strip(),
            irp_client_secret = self._irp_client_secret_var.get().strip(),
            irp_username      = self._irp_username_var.get().strip(),
            irp_password      = self._irp_password_var.get(),
            einvoice_sandbox  = sandbox_val,
            ewb_username      = self._ewb_username_var.get().strip(),
            ewb_password      = self._ewb_password_var.get(),
            ewb_sandbox       = ewb_sandbox_val,
            smtp_host         = self._smtp_host_var.get().strip(),
            smtp_port         = int(self._smtp_port_var.get().strip() or 587),
            smtp_user         = self._smtp_user_var.get().strip(),
            smtp_password     = self._smtp_password_var.get(),
            smtp_tls          = 1 if "STARTTLS" in self._smtp_tls_var.get() else 0,
            smtp_from_name    = self._smtp_from_name_var.get().strip(),
        )
        self._saved_lbl.configure(text=f"Saved  {datetime.now().strftime('%I:%M %p')}")
        self._refresh_preview()

    # ── Printer Tab ───────────────────────────────────────────────────────────

    def _build_printer_tab(self, parent):
        import thermal_receipt
        cfg = thermal_receipt.load_config()

        sc = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        sc.pack(fill="both", expand=True)

        f = self._section(sc, "🖨  Thermal Receipt Printer")

        # Enable toggle
        ctk.CTkLabel(f, text="Enable thermal printing",
                     text_color="#95a5a6", font=ctk.CTkFont(size=11)
                     ).pack(anchor="w", padx=16, pady=(10, 0))
        self._printer_enabled_var = ctk.StringVar(
            value="Enabled" if cfg.get("enabled") else "Disabled")
        ctk.CTkSegmentedButton(
            f, values=["Enabled", "Disabled"],
            variable=self._printer_enabled_var,
            command=self._on_printer_type_change,
        ).pack(anchor="w", padx=16, pady=(4, 0))

        # Type
        ctk.CTkLabel(f, text="Connection type",
                     text_color="#95a5a6", font=ctk.CTkFont(size=11)
                     ).pack(anchor="w", padx=16, pady=(10, 0))
        self._printer_type_var = ctk.StringVar(
            value="Windows Printer" if cfg.get("type", "windows") == "windows"
            else "Network (TCP/IP)")
        ctk.CTkSegmentedButton(
            f, values=["Windows Printer", "Network (TCP/IP)"],
            variable=self._printer_type_var,
            command=self._on_printer_type_change,
        ).pack(anchor="w", padx=16, pady=(4, 0))

        # Windows printer name + refresh
        self._win_printer_frame = ctk.CTkFrame(f, fg_color="transparent")
        self._win_printer_frame.pack(fill="x", padx=16, pady=(8, 0))
        ctk.CTkLabel(self._win_printer_frame, text="Windows printer name",
                     text_color="#95a5a6", font=ctk.CTkFont(size=11)
                     ).pack(anchor="w")
        prow = ctk.CTkFrame(self._win_printer_frame, fg_color="transparent")
        prow.pack(fill="x")
        prow.columnconfigure(0, weight=1)
        printers = thermal_receipt.list_windows_printers()
        self._printer_name_var = ctk.StringVar(value=cfg.get("name", ""))
        combo = ctk.CTkComboBox(
            prow, variable=self._printer_name_var,
            values=printers if printers else ["(no printers found)"])
        combo.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            prow, text="⟳", width=36, height=32,
            fg_color="#1e3a5f", hover_color="#2a4f80",
            command=lambda: combo.configure(
                values=thermal_receipt.list_windows_printers() or ["(no printers found)"])
        ).grid(row=0, column=1, padx=(6, 0))

        # Network fields
        self._net_printer_frame = ctk.CTkFrame(f, fg_color="transparent")
        self._net_printer_frame.pack(fill="x", padx=16, pady=(8, 0))
        nr = ctk.CTkFrame(self._net_printer_frame, fg_color="transparent")
        nr.pack(fill="x")
        nr.columnconfigure(0, weight=3)
        nr.columnconfigure(1, weight=1)
        ctk.CTkLabel(nr, text="Printer IP address",
                     text_color="#95a5a6", font=ctk.CTkFont(size=11)
                     ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(nr, text="Port",
                     text_color="#95a5a6", font=ctk.CTkFont(size=11)
                     ).grid(row=0, column=1, sticky="w", padx=(8, 0))
        self._printer_ip_var   = ctk.StringVar(value=cfg.get("ip", ""))
        self._printer_port_var = ctk.StringVar(value=str(cfg.get("port", 9100)))
        ctk.CTkEntry(nr, textvariable=self._printer_ip_var,
                     placeholder_text="192.168.1.100"
                     ).grid(row=1, column=0, sticky="ew")
        ctk.CTkEntry(nr, textvariable=self._printer_port_var, width=70
                     ).grid(row=1, column=1, sticky="ew", padx=(8, 0))

        # Paper width
        ctk.CTkLabel(f, text="Paper width",
                     text_color="#95a5a6", font=ctk.CTkFont(size=11)
                     ).pack(anchor="w", padx=16, pady=(10, 0))
        self._printer_width_var = ctk.StringVar(
            value="80mm (standard)" if cfg.get("width", 80) >= 70 else "58mm (narrow)")
        ctk.CTkSegmentedButton(
            f, values=["80mm (standard)", "58mm (narrow)"],
            variable=self._printer_width_var,
        ).pack(anchor="w", padx=16, pady=(4, 0))

        # Auto-print
        ctk.CTkLabel(f, text="Auto-print every bill",
                     text_color="#95a5a6", font=ctk.CTkFont(size=11)
                     ).pack(anchor="w", padx=16, pady=(10, 0))
        self._printer_auto_var = ctk.StringVar(
            value="Yes (auto)" if cfg.get("auto_print", True) else "No (ask me)")
        ctk.CTkSegmentedButton(
            f, values=["Yes (auto)", "No (ask me)"],
            variable=self._printer_auto_var,
        ).pack(anchor="w", padx=16, pady=(4, 12))

        # Buttons
        btn_row = ctk.CTkFrame(f, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkButton(
            btn_row, text="💾  Save Printer Settings", height=36,
            fg_color="#0d9488", hover_color="#0a7a70",
            command=self._save_printer_settings,
        ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            btn_row, text="🖨  Test Print", height=36, width=120,
            fg_color="#1e3a5f", hover_color="#2a4f80",
            command=self._test_print,
        ).pack(side="left")

        self._on_printer_type_change()

    def _on_printer_type_change(self, *_):
        try:
            is_net = self._printer_type_var.get() == "Network (TCP/IP)"
            enabled = self._printer_enabled_var.get() == "Enabled"
            state = "normal" if enabled else "disabled"
            # show/hide relevant frame
            if is_net:
                self._win_printer_frame.pack_forget()
                self._net_printer_frame.pack(fill="x", padx=16, pady=(8, 0),
                                              after=self._win_printer_frame)
            else:
                self._net_printer_frame.pack_forget()
                self._win_printer_frame.pack(fill="x", padx=16, pady=(8, 0))
        except Exception:
            pass

    def _save_printer_settings(self):
        import thermal_receipt
        try:
            cfg = {
                "enabled":    self._printer_enabled_var.get() == "Enabled",
                "type":       "network" if self._printer_type_var.get() == "Network (TCP/IP)"
                              else "windows",
                "name":       self._printer_name_var.get().strip(),
                "ip":         self._printer_ip_var.get().strip(),
                "port":       int(self._printer_port_var.get().strip() or 9100),
                "width":      80 if "80" in self._printer_width_var.get() else 58,
                "auto_print": self._printer_auto_var.get() == "Yes (auto)",
            }
            thermal_receipt.save_config(cfg)
            messagebox.showinfo("Saved", "Printer settings saved.", parent=self)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def _test_print(self):
        import thermal_receipt
        try:
            self._save_printer_settings()
            thermal_receipt.test_print()
            messagebox.showinfo("Test Print", "Test page sent to printer!", parent=self)
        except Exception as e:
            messagebox.showerror("Print Error",
                                 f"Could not reach printer:\n{e}", parent=self)

    # ── Users Tab (admin only) ─────────────────────────────────────────────────

    def _build_users_tab(self, parent):
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(12, 8))
        ctk.CTkLabel(top, text="Manage Users",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(side="left")

        ctk.CTkButton(
            top, text="+ Add User", width=110, height=34,
            fg_color="#2ecc71", hover_color="#27ae60", text_color="#000",
            command=lambda: AddEditUserDialog(self, self._reload_users_tab),
        ).pack(side="right")

        # Also "Change My Password" button
        ctk.CTkButton(
            top, text="🔑 Change My Password", width=170, height=34,
            fg_color="#0f3460", hover_color="#1a5276",
            command=lambda: ChangePasswordDialog(self, self.app.current_user["id"]),
        ).pack(side="right", padx=(0, 8))

        self._users_list_frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        self._users_list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        self._reload_users_table()

    def _reload_users_tab(self):
        self._reload_users_table()

    def _reload_users_table(self):
        for w in self._users_list_frame.winfo_children():
            w.destroy()

        # Header
        hdr = ctk.CTkFrame(self._users_list_frame, fg_color="#0f3460", corner_radius=6)
        hdr.pack(fill="x", pady=(0, 4))
        for col, width, text in [
            (0, 140, "Username"), (1, 160, "Full Name"),
            (2, 80, "Role"), (3, 70, "Active"), (4, 100, "Actions"),
        ]:
            ctk.CTkLabel(hdr, text=text, font=ctk.CTkFont(size=12, weight="bold"),
                         width=width, anchor="w").grid(
                row=0, column=col, padx=8, pady=6, sticky="w")

        users = db.get_all_users()
        current_id = self.app.current_user["id"]

        for i, user in enumerate(users):
            bg = "#16213e" if i % 2 == 0 else "#1a2744"
            row = ctk.CTkFrame(self._users_list_frame, fg_color=bg, corner_radius=4)
            row.pack(fill="x", pady=1)

            ctk.CTkLabel(row, text=user["username"], width=140, anchor="w",
                         font=ctk.CTkFont(size=12)).grid(row=0, column=0, padx=8, pady=6, sticky="w")
            ctk.CTkLabel(row, text=user.get("full_name", "") or "—", width=160, anchor="w",
                         font=ctk.CTkFont(size=12), text_color="#bdc3c7").grid(
                row=0, column=1, padx=8, pady=6, sticky="w")

            role_color = "#e94560" if user["role"] == "admin" else "#3498db"
            ctk.CTkLabel(row, text=user["role"].capitalize(), width=80, anchor="w",
                         font=ctk.CTkFont(size=11), text_color=role_color).grid(
                row=0, column=2, padx=8, pady=6, sticky="w")

            status = "✅" if user["is_active"] else "❌"
            ctk.CTkLabel(row, text=status, width=70, anchor="w").grid(
                row=0, column=3, padx=8, pady=6, sticky="w")

            act_frame = ctk.CTkFrame(row, fg_color="transparent")
            act_frame.grid(row=0, column=4, padx=8, pady=4, sticky="w")

            ctk.CTkButton(
                act_frame, text="Edit", width=52, height=28,
                fg_color="#2c3e50", hover_color="#3498db",
                font=ctk.CTkFont(size=11),
                command=lambda u=user: AddEditUserDialog(self, self._reload_users_tab, u),
            ).pack(side="left", padx=(0, 4))

            # Cannot delete yourself or the last admin
            is_self = user["id"] == current_id
            is_last_admin = (user["role"] == "admin" and
                             sum(1 for u in users if u["role"] == "admin") <= 1)
            if not is_self and not is_last_admin:
                ctk.CTkButton(
                    act_frame, text="Del", width=42, height=28,
                    fg_color="#6c2626", hover_color="#e74c3c",
                    font=ctk.CTkFont(size=11),
                    command=lambda uid=user["id"]: self._delete_user(uid),
                ).pack(side="left")

    def _delete_user(self, user_id):
        if messagebox.askyesno("Delete User", "Are you sure you want to delete this user?"):
            db.delete_user(user_id)
            self._reload_users_table()


# ── Expenses Page ─────────────────────────────────────────────────────────────

class ExpensesPage(BasePage):

    _RANGES = {
        "This Month":    lambda t: (t.replace(day=1).strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d")),
        "Last Month":    lambda t: ((t.replace(day=1) - timedelta(days=1)).replace(day=1).strftime("%Y-%m-%d"),
                                    (t.replace(day=1) - timedelta(days=1)).strftime("%Y-%m-%d")),
        "This Quarter":  lambda t: (
            t.replace(month=((t.month - 1) // 3) * 3 + 1, day=1).strftime("%Y-%m-%d"),
            t.strftime("%Y-%m-%d")),
        "This Year":     lambda t: (t.replace(month=1, day=1).strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d")),
        "All Time":      lambda t: ("2000-01-01", t.strftime("%Y-%m-%d")),
    }

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._range_key = "This Month"
        self._search    = ""

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._header("Expenses", "Record and track business expenses")

        today = datetime.now()
        from_d, to_d = self._RANGES[self._range_key](today)

        # ── Top toolbar ───────────────────────────────────────────────────────
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=24, pady=(0, 10))
        ctk.CTkButton(bar, text="+ Record Expense", width=160, height=34,
                      fg_color="#e74c3c", hover_color="#c0392b",
                      command=lambda: ExpenseDialog(self, self.app)
                      ).pack(side="left")

        # Search
        self._search_var = ctk.StringVar(value=self._search)
        srch = ctk.CTkEntry(bar, textvariable=self._search_var,
                            placeholder_text="🔍  Search description or account…",
                            width=220, height=30)
        srch.pack(side="left", padx=(12, 2))
        srch.bind("<KeyRelease>", lambda e: self._on_search())
        ctk.CTkButton(bar, text="✕", width=28, height=28, fg_color="transparent",
                      hover_color="#16213e",
                      command=self._clear_search).pack(side="left", padx=(0, 10))

        # Date range quick buttons
        for label in self._RANGES:
            active = label == self._range_key
            ctk.CTkButton(
                bar, text=label, height=28,
                width=len(label) * 7 + 16,
                fg_color="#0f3460" if active else "transparent",
                hover_color="#16213e", border_width=1, border_color="#0f3460",
                font=ctk.CTkFont(size=10),
                command=lambda l=label: self._set_range(l),
            ).pack(side="left", padx=2)

        # Export buttons
        ctk.CTkButton(bar, text="📊 Excel", width=80, height=28,
                      fg_color="#16213e", hover_color="#0f3460",
                      font=ctk.CTkFont(size=10),
                      command=lambda: self._export("excel", from_d, to_d)
                      ).pack(side="right", padx=2)
        ctk.CTkButton(bar, text="📄 PDF", width=70, height=28,
                      fg_color="#16213e", hover_color="#0f3460",
                      font=ctk.CTkFont(size=10),
                      command=lambda: self._export("pdf", from_d, to_d)
                      ).pack(side="right", padx=2)

        # ── Stat cards ────────────────────────────────────────────────────────
        summary_now  = db.get_expense_summary(from_d, to_d)
        total_period = sum(r["total"] for r in summary_now)

        # Last month for comparison
        lm_f, lm_t = self._RANGES["Last Month"](today)
        lm_total    = sum(r["total"] for r in db.get_expense_summary(lm_f, lm_t))

        # YTD
        ytd_f, ytd_t = self._RANGES["This Year"](today)
        ytd_total    = sum(r["total"] for r in db.get_expense_summary(ytd_f, ytd_t))

        entries_all = db.get_expense_entries(from_d, to_d)
        entry_count = len(entries_all)

        sc = ctk.CTkFrame(self, fg_color="transparent")
        sc.pack(fill="x", padx=24, pady=(0, 10))
        for i in range(4):
            sc.columnconfigure(i, weight=1)
        for i, (title, val, color, icon) in enumerate([
            (self._range_key,  f"₹ {total_period:,.0f}", "#e74c3c", "💸"),
            ("Last Month",     f"₹ {lm_total:,.0f}",     "#f39c12", "📅"),
            ("Year to Date",   f"₹ {ytd_total:,.0f}",    "#9b59b6", "📆"),
            ("Entries",        str(entry_count),          "#3498db", "📋"),
        ]):
            c = self._card(sc, title, val, color, icon)
            c.grid(row=0, column=i, padx=6, pady=4, sticky="ew")

        # ── Category breakdown ────────────────────────────────────────────────
        if summary_now:
            cat_frame = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=12)
            cat_frame.pack(fill="x", padx=24, pady=(0, 10))
            ctk.CTkLabel(cat_frame, text="Spend by Category",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#95a5a6").pack(padx=16, pady=(10, 4), anchor="w")
            inner = ctk.CTkFrame(cat_frame, fg_color="transparent")
            inner.pack(fill="x", padx=16, pady=(0, 10))
            cat_colors = ["#e74c3c","#e67e22","#f39c12","#2ecc71","#3498db","#9b59b6"]
            grand_total = sum(r["total"] for r in summary_now) or 1
            max_total   = max(r["total"] for r in summary_now) or 1
            for idx, r in enumerate(summary_now):
                bar_w = max(6, int(r["total"] / max_total * 260))
                pct   = r["total"] / grand_total * 100
                clr   = cat_colors[idx % len(cat_colors)]
                cat_row = ctk.CTkFrame(inner, fg_color="transparent")
                cat_row.pack(fill="x", pady=2)
                ctk.CTkLabel(cat_row, text=r["account_name"],
                             width=175, anchor="w",
                             font=ctk.CTkFont(size=11),
                             text_color="#ecf0f1").pack(side="left")
                bar_bg = ctk.CTkFrame(cat_row, fg_color="#0d1117",
                                      corner_radius=4, height=14, width=265)
                bar_bg.pack(side="left", padx=(4, 6))
                bar_bg.pack_propagate(False)
                ctk.CTkFrame(bar_bg, fg_color=clr, corner_radius=4,
                             height=14, width=bar_w).place(x=0, y=0)
                ctk.CTkLabel(cat_row, text=f"₹{r['total']:,.0f}",
                             font=ctk.CTkFont(size=11, weight="bold"),
                             text_color=clr, width=85, anchor="e").pack(side="left")
                ctk.CTkLabel(cat_row, text=f"{pct:.1f}%",
                             font=ctk.CTkFont(size=10),
                             text_color="#7f8c8d", width=42, anchor="e").pack(side="left")

        # ── Expense table ─────────────────────────────────────────────────────
        tbl = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=12)
        tbl.pack(fill="both", expand=True, padx=24, pady=(0, 24))

        hdr = ctk.CTkFrame(tbl, fg_color="#0f3460", corner_radius=6)
        hdr.pack(fill="x", padx=12, pady=(10, 2))
        for col, w in [("Date", 95), ("Account", 165), ("Paid From", 130),
                       ("Description", 240), ("Ref", 100), ("Amount", 110), ("", 46)]:
            ctk.CTkLabel(hdr, text=col, width=w,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#95a5a6").pack(side="left", padx=6, pady=6)

        scroll = ctk.CTkScrollableFrame(tbl, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        q = self._search_var.get().strip() if hasattr(self, "_search_var") else ""
        entries = db.get_expense_entries(from_d, to_d, search=q or None)

        if not entries:
            ctk.CTkLabel(scroll, text="No expenses found.",
                         text_color="#95a5a6").pack(pady=30)
            return

        cat_color_map = {}
        _clrs = ["#e74c3c","#e67e22","#f39c12","#2ecc71","#3498db","#9b59b6"]
        for r in summary_now:
            cat_color_map[r["account_name"]] = _clrs[len(cat_color_map) % len(_clrs)]

        for e in [dict(r) for r in entries]:
            row = ctk.CTkFrame(scroll, fg_color="#16213e", corner_radius=4)
            row.pack(fill="x", pady=1)
            acct_color = cat_color_map.get(e["expense_account"], "#e67e22")
            ctk.CTkLabel(row, text=e["entry_date"], width=95,
                         font=ctk.CTkFont(size=11), text_color="#95a5a6"
                         ).pack(side="left", padx=6, pady=6)
            ctk.CTkLabel(row, text=(e["expense_account"] or "")[:22], width=165,
                         font=ctk.CTkFont(size=11), text_color=acct_color,
                         anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=(e["paid_from"] or "")[:18], width=130,
                         font=ctk.CTkFont(size=11), text_color="#3498db",
                         anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=(e["narration"] or "")[:36], width=240,
                         font=ctk.CTkFont(size=11), text_color="#ecf0f1",
                         anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=(e["reference"] or "")[:14], width=100,
                         font=ctk.CTkFont(size=10), text_color="#7f8c8d",
                         anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=f"₹{e['amount']:,.0f}", width=110,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#e74c3c", anchor="e").pack(side="left", padx=4)
            ctk.CTkButton(row, text="🗑", width=36, height=26,
                          fg_color="#7f1f1f", hover_color="#c0392b",
                          font=ctk.CTkFont(size=11),
                          command=lambda eid=e["id"], desc=(e["narration"] or ""): self._delete(eid, desc)
                          ).pack(side="left", padx=(4, 6))

    def _set_range(self, key):
        self._range_key = key
        self.refresh()

    def _on_search(self):
        self._search = self._search_var.get()
        self.refresh()

    def _clear_search(self):
        self._search = ""
        self.refresh()

    def _delete(self, je_id, desc):
        short = desc[:40] + "…" if len(desc) > 40 else desc
        if messagebox.askyesno("Delete Expense", f'Delete expense:\n"{short}"?'):
            db.delete_expense_entry(je_id)
            self.refresh()

    def _export(self, fmt, from_d, to_d):
        entries = [dict(r) for r in db.get_expense_entries(from_d, to_d)]
        summary = [dict(r) for r in db.get_expense_summary(from_d, to_d)]
        firm    = db.get_firm_settings()
        firm_d  = dict(firm) if firm else {}
        label   = self._range_key.replace(" ", "_")
        if fmt == "pdf":
            default = f"Expenses_{label}.pdf"
            fn      = rex.export_expense_pdf
        else:
            default = f"Expenses_{label}.xlsx"
            fn      = rex.export_expense_excel
        path = filedialog.asksaveasfilename(
            defaultextension=os.path.splitext(default)[1],
            initialfile=default,
            filetypes=[("All files", "*.*")],
        )
        if not path:
            return
        try:
            fn(entries, summary, from_d, to_d, firm_d, path)
            messagebox.showinfo("Exported", f"Saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))


class ExpenseDialog(ctk.CTkToplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("Record Expense")
        self.geometry("460x420")
        self.grab_set()
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Record Expense",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#ecf0f1").pack(padx=20, pady=(16, 4), anchor="w")

        frame = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=10)
        frame.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        def lbl(text, default=""):
            ctk.CTkLabel(frame, text=text, text_color="#95a5a6",
                         font=ctk.CTkFont(size=10)).pack(anchor="w", padx=16, pady=(10, 0))
            var = ctk.StringVar(value=default)
            ctk.CTkEntry(frame, textvariable=var).pack(fill="x", padx=16, pady=(2, 0))
            return var

        def combo(text, values, default=""):
            ctk.CTkLabel(frame, text=text, text_color="#95a5a6",
                         font=ctk.CTkFont(size=10)).pack(anchor="w", padx=16, pady=(10, 0))
            var = ctk.StringVar(value=default or (values[0] if values else ""))
            ctk.CTkComboBox(frame, values=values, variable=var).pack(fill="x", padx=16, pady=(2, 0))
            return var

        # Expense accounts
        all_accts = db.get_all_accounts()
        exp_accts = [f"{a['code']} – {a['name']}" for a in all_accts if a["account_type"] == "Expense"]
        pay_accts = [f"{a['code']} – {a['name']}" for a in all_accts
                     if a["account_type"] == "Asset" and a["code"] in ("1002", "1003")]

        today = datetime.now().strftime("%Y-%m-%d")
        self.date     = lbl("Date *", today)
        self.exp_var  = combo("Expense Account *", exp_accts)
        self.pay_var  = combo("Paid From *", pay_accts)
        self.amount   = lbl("Amount (₹) *")
        self.narr     = lbl("Description *")
        self.ref      = lbl("Reference / Bill No.")

        ctk.CTkFrame(frame, fg_color="transparent", height=4).pack()

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 20))
        ctk.CTkButton(btn_row, text="Cancel",
                      fg_color="#2c3e50", hover_color="#34495e",
                      command=self.destroy).pack(side="right")
        ctk.CTkButton(btn_row, text="Save Expense", width=130,
                      fg_color="#e74c3c", hover_color="#c0392b",
                      command=self._save).pack(side="right", padx=8)

    def _save(self):
        date   = self.date.get().strip()
        narr   = self.narr.get().strip()
        ref    = self.ref.get().strip()
        amt_s  = self.amount.get().strip()
        exp_n  = self.exp_var.get()
        pay_n  = self.pay_var.get()

        if not date or not narr or not amt_s:
            messagebox.showerror("Error", "Date, description, and amount are required.")
            return
        try:
            amt = float(amt_s)
            if amt <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Enter a valid positive amount.")
            return

        all_accts  = db.get_all_accounts()
        acct_map   = {f"{a['code']} – {a['name']}": a for a in all_accts}
        exp_acct   = acct_map.get(exp_n)
        pay_acct   = acct_map.get(pay_n)
        if not exp_acct or not pay_acct:
            messagebox.showerror("Error", "Select valid expense and payment accounts.")
            return

        lines = [
            {"account_id": exp_acct["id"], "debit": amt,  "credit": 0.0},
            {"account_id": pay_acct["id"], "debit": 0.0,  "credit": amt},
        ]
        try:
            db.add_journal_entry(date, narr, ref, lines)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        messagebox.showinfo("Saved", f"Expense of ₹{amt:,.2f} recorded successfully!")
        self.app.refresh_current()
        self.destroy()


# ── Purchases Page ────────────────────────────────────────────────────────────

class PurchasesPage(BasePage):

    _RANGES = {
        "This Month": lambda t: (t.replace(day=1).strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d")),
        "Last Month":  lambda t: (
            (t.replace(day=1) - timedelta(days=1)).replace(day=1).strftime("%Y-%m-%d"),
            (t.replace(day=1) - timedelta(days=1)).strftime("%Y-%m-%d")),
        "This Year":   lambda t: (t.replace(month=1, day=1).strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d")),
        "All Time":    lambda t: ("2000-01-01", t.strftime("%Y-%m-%d")),
    }

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._range_key    = "This Month"
        self._status_filter = "All"

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._header("Purchases / Bills", "Track purchase bills and vendor payments")

        today = datetime.now()
        from_d, to_d = self._RANGES[self._range_key](today)

        # ── Toolbar ───────────────────────────────────────────────────────────
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=24, pady=(0, 8))
        ctk.CTkButton(bar, text="+ New Purchase", width=140, height=34,
                      fg_color="#8e44ad", hover_color="#6c3483",
                      command=lambda: PurchaseDialog(self, self.app)
                      ).pack(side="left")
        ctk.CTkButton(bar, text="👥 Vendors", width=90, height=34,
                      fg_color="#16213e", hover_color="#0f3460",
                      command=lambda: VendorsDialog(self, self.app)
                      ).pack(side="left", padx=(8, 0))

        # Date range
        for label in self._RANGES:
            active = label == self._range_key
            ctk.CTkButton(
                bar, text=label, height=28,
                width=len(label) * 7 + 16,
                fg_color="#0f3460" if active else "transparent",
                hover_color="#16213e", border_width=1, border_color="#0f3460",
                font=ctk.CTkFont(size=10),
                command=lambda l=label: self._set_range(l),
            ).pack(side="left", padx=2)

        # Status filter
        for s in ["All", "Unpaid", "Paid"]:
            active = s == self._status_filter
            ctk.CTkButton(
                bar, text=s, height=28, width=56,
                fg_color="#8e44ad" if active else "transparent",
                hover_color="#6c3483", border_width=1, border_color="#6c3483",
                font=ctk.CTkFont(size=10),
                command=lambda x=s: self._set_status(x),
            ).pack(side="left", padx=2)

        # Export
        ctk.CTkButton(bar, text="📊 Excel", width=80, height=28,
                      fg_color="#16213e", hover_color="#0f3460",
                      font=ctk.CTkFont(size=10),
                      command=lambda: self._export("excel", from_d, to_d)
                      ).pack(side="right", padx=2)
        ctk.CTkButton(bar, text="📄 PDF", width=70, height=28,
                      fg_color="#16213e", hover_color="#0f3460",
                      font=ctk.CTkFont(size=10),
                      command=lambda: self._export("pdf", from_d, to_d)
                      ).pack(side="right", padx=2)

        # ── KPI tiles ─────────────────────────────────────────────────────────
        purchases = [dict(r) for r in db.get_all_purchases(from_d, to_d)]
        unpaid    = [p for p in purchases if p["status"] == "Unpaid"]
        gst_in    = sum(p["cgst_total"] + p["sgst_total"] + p["igst_total"] for p in purchases)

        sc = ctk.CTkFrame(self, fg_color="transparent")
        sc.pack(fill="x", padx=24, pady=(0, 8))
        for i in range(4):
            sc.columnconfigure(i, weight=1)
        for i, (title, val, color) in enumerate([
            (self._range_key,  f"₹ {sum(p['grand_total'] for p in purchases):,.0f}", "#8e44ad"),
            ("Unpaid Bills",   f"₹ {sum(p['grand_total'] for p in unpaid):,.0f}  ({len(unpaid)})", "#e74c3c"),
            ("GST Input",      f"₹ {gst_in:,.0f}",                                                "#3498db"),
            ("Bills Count",    str(len(purchases)),                                                "#2ecc71"),
        ]):
            self._card(sc, title, val, color).grid(row=0, column=i, padx=6, sticky="ew")

        # ── Table ─────────────────────────────────────────────────────────────
        filtered = purchases
        if self._status_filter != "All":
            filtered = [p for p in purchases if p["status"] == self._status_filter]

        tbl = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=12)
        tbl.pack(fill="both", expand=True, padx=24, pady=(0, 24))

        COLS = [("Date", 95), ("Bill #", 110), ("Vendor", 180), ("Subtotal", 95),
                ("GST", 80), ("Grand Total", 100), ("Status", 90), ("", 160)]
        hdr = ctk.CTkFrame(tbl, fg_color="#0f3460", corner_radius=0)
        hdr.pack(fill="x")
        for col, w in COLS:
            ctk.CTkLabel(hdr, text=col, font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#bdc3c7", width=w, anchor="w"
                         ).pack(side="left", padx=8, pady=7)

        body = ctk.CTkScrollableFrame(tbl, fg_color="transparent")
        body.pack(fill="both", expand=True)

        if not filtered:
            ctk.CTkLabel(body, text="No purchase bills found.",
                         text_color="#7f8c8d",
                         font=ctk.CTkFont(size=13)).pack(pady=40)
            return

        for i, p in enumerate(filtered):
            row_bg = "#1a1a2e" if i % 2 == 0 else "#0f1626"
            row = ctk.CTkFrame(body, fg_color=row_bg, corner_radius=0, height=40)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            status_color = "#2ecc71" if p["status"] == "Paid" else "#e74c3c"
            gst_p = p["cgst_total"] + p["sgst_total"] + p["igst_total"]

            for val, w in [
                (p["bill_date"], 95),
                (p["bill_number"] or "—", 110),
                (p["vendor_name"][:24], 180),
                (f"₹{p['subtotal']:,.0f}", 95),
                (f"₹{gst_p:,.0f}", 80),
                (f"₹{p['grand_total']:,.0f}", 100),
            ]:
                ctk.CTkLabel(row, text=str(val), font=ctk.CTkFont(size=11),
                             text_color="#ecf0f1", width=w, anchor="w"
                             ).pack(side="left", padx=8)

            ctk.CTkLabel(row, text=p["status"], font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=status_color, width=90, anchor="w"
                         ).pack(side="left", padx=4)

            if p["status"] == "Unpaid":
                ctk.CTkButton(row, text="💳 Pay", width=70, height=28,
                              fg_color="#1a3a5c", hover_color="#2355c2",
                              font=ctk.CTkFont(size=10),
                              command=lambda pp=p: self._pay_bill(pp)
                              ).pack(side="left", padx=2)

            ctk.CTkButton(row, text="🗑", width=36, height=28,
                          fg_color="#7f1f1f", hover_color="#c0392b",
                          font=ctk.CTkFont(size=11),
                          command=lambda pid=p["id"], bn=p["bill_number"]: self._delete(pid, bn)
                          ).pack(side="left", padx=2)

    def _set_range(self, key):
        self._range_key = key
        self.refresh()

    def _set_status(self, s):
        self._status_filter = s
        self.refresh()

    def _pay_bill(self, p):
        PurchasePaymentDialog(self, self.app, p)

    def _delete(self, pid, bill_number):
        label = bill_number or f"ID {pid}"
        if messagebox.askyesno("Delete Purchase",
                               f"Delete purchase bill '{label}'?\nThis will also reverse its journal entry."):
            db.delete_purchase(pid)
            self.refresh()

    def _export(self, fmt, from_d, to_d):
        purchases = [dict(r) for r in db.get_all_purchases(from_d, to_d)]
        if not purchases:
            messagebox.showinfo("No Data", "No purchases to export.")
            return
        firm  = dict(db.get_firm_settings())
        label = self._range_key.replace(" ", "_")
        if fmt == "pdf":
            default = f"Purchases_{label}.pdf"
            fn = rex.export_purchases_pdf
        else:
            default = f"Purchases_{label}.xlsx"
            fn = rex.export_purchases_excel
        path = filedialog.asksaveasfilename(
            defaultextension=os.path.splitext(default)[1],
            initialfile=default,
            filetypes=[("All files", "*.*")],
        )
        if not path:
            return
        try:
            fn(purchases, firm, path)
            messagebox.showinfo("Exported", f"Saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))


class PurchaseDialog(ctk.CTkToplevel):
    """Multi-line purchase bill entry with vendor, GST, and payment mode."""

    GST_RATES = ["0", "5", "12", "18", "28"]

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app   = app
        self.title("New Purchase / Bill")
        self.geometry("680x680")
        self.grab_set()
        self.items = []  # list of dicts with entry widgets
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="New Purchase / Bill",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#ecf0f1").pack(padx=20, pady=(14, 4), anchor="w")

        # ── Top meta section ──────────────────────────────────────────────────
        meta = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=10)
        meta.pack(fill="x", padx=20, pady=(0, 8))
        meta.columnconfigure(0, weight=1)
        meta.columnconfigure(1, weight=1)
        meta.columnconfigure(2, weight=1)
        meta.columnconfigure(3, weight=1)

        def lbl_field(parent, text, default="", row=0, col=0, colspan=1):
            ctk.CTkLabel(parent, text=text, text_color="#95a5a6",
                         font=ctk.CTkFont(size=10)
                         ).grid(row=row*2, column=col, columnspan=colspan,
                                padx=10, pady=(8, 0), sticky="w")
            var = ctk.StringVar(value=default)
            ctk.CTkEntry(parent, textvariable=var, height=30
                         ).grid(row=row*2+1, column=col, columnspan=colspan,
                                padx=10, pady=(2, 4), sticky="ew")
            return var

        # Vendor row
        ctk.CTkLabel(meta, text="Vendor / Supplier", text_color="#95a5a6",
                     font=ctk.CTkFont(size=10)).grid(row=0, column=0, columnspan=3,
                                                      padx=10, pady=(8, 0), sticky="w")
        vendors = db.get_all_vendors()
        self._vendor_names = ["— No Vendor —"] + [v["name"] for v in vendors]
        self._vendor_map   = {v["name"]: v["id"] for v in vendors}
        self._vendor_var   = ctk.StringVar(value=self._vendor_names[0])
        vendor_row = ctk.CTkFrame(meta, fg_color="transparent")
        vendor_row.grid(row=1, column=0, columnspan=3, padx=10, pady=(2, 4), sticky="ew")
        self._vendor_cb = ctk.CTkComboBox(vendor_row, values=self._vendor_names,
                                          variable=self._vendor_var, width=260)
        self._vendor_cb.pack(side="left")
        ctk.CTkButton(vendor_row, text="+ Add", width=60, height=30,
                      fg_color="#8e44ad", hover_color="#6c3483",
                      command=self._add_vendor_inline).pack(side="left", padx=(6, 0))

        today = datetime.now().strftime("%Y-%m-%d")
        self._bill_number = lbl_field(meta, "Bill Number",   default="",    row=0, col=3)
        self._bill_date   = lbl_field(meta, "Bill Date *",   default=today, row=1, col=0)
        self._due_date    = lbl_field(meta, "Due Date",      default="",    row=1, col=1)

        # Supply type toggle
        ctk.CTkLabel(meta, text="Supply Type", text_color="#95a5a6",
                     font=ctk.CTkFont(size=10)).grid(row=2, column=0, padx=10, pady=(8, 0), sticky="w")
        self._supply_var = ctk.StringVar(value="intra")
        st_frame = ctk.CTkFrame(meta, fg_color="transparent")
        st_frame.grid(row=3, column=0, columnspan=2, padx=10, pady=(2, 4), sticky="w")
        for lbl, val in [("Intra-State (CGST+SGST)", "intra"), ("Inter-State (IGST)", "inter")]:
            ctk.CTkRadioButton(st_frame, text=lbl, variable=self._supply_var, value=val,
                               font=ctk.CTkFont(size=10),
                               command=self._recalc).pack(side="left", padx=(0, 12))

        # Payment mode
        ctk.CTkLabel(meta, text="Payment Mode", text_color="#95a5a6",
                     font=ctk.CTkFont(size=10)).grid(row=2, column=2, padx=10, pady=(8, 0), sticky="w")
        self._pay_mode_var = ctk.StringVar(value="Credit")
        ctk.CTkComboBox(meta, values=["Credit (Accounts Payable)", "Cash", "Bank / UPI"],
                        variable=self._pay_mode_var, width=180
                        ).grid(row=3, column=2, columnspan=2, padx=10, pady=(2, 4), sticky="w")

        ctk.CTkLabel(meta, text="Notes", text_color="#95a5a6",
                     font=ctk.CTkFont(size=10)).grid(row=4, column=0, columnspan=4,
                                                      padx=10, pady=(4, 0), sticky="w")
        self._notes_var = ctk.StringVar()
        ctk.CTkEntry(meta, textvariable=self._notes_var
                     ).grid(row=5, column=0, columnspan=4, padx=10, pady=(2, 10), sticky="ew")

        # ── Items table ───────────────────────────────────────────────────────
        items_outer = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=10)
        items_outer.pack(fill="both", expand=True, padx=20, pady=(0, 8))

        # Header row
        hdr = ctk.CTkFrame(items_outer, fg_color="#0f3460", corner_radius=0)
        hdr.pack(fill="x", padx=8, pady=(8, 0))
        for col, w in [("Description", 220), ("Qty", 60), ("Unit Price", 90),
                       ("GST %", 70), ("Amount", 90), ("", 32)]:
            ctk.CTkLabel(hdr, text=col, width=w, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#bdc3c7", anchor="w").pack(side="left", padx=4, pady=5)

        self._items_frame = ctk.CTkScrollableFrame(items_outer, fg_color="transparent", height=160)
        self._items_frame.pack(fill="both", expand=True, padx=8, pady=(2, 4))

        for _ in range(3):
            self._add_item_row()

        ctk.CTkButton(items_outer, text="+ Add Row", width=90, height=28,
                      fg_color="#16213e", hover_color="#0f3460",
                      border_width=1, border_color="#555",
                      font=ctk.CTkFont(size=10),
                      command=self._add_item_row).pack(side="left", padx=10, pady=(0, 8))

        # ── Totals ────────────────────────────────────────────────────────────
        tot = ctk.CTkFrame(self, fg_color="#0f3460", corner_radius=8)
        tot.pack(fill="x", padx=20, pady=(0, 8))
        self._subtotal_lbl = ctk.CTkLabel(tot, text="Subtotal: ₹ 0.00",
                                           font=ctk.CTkFont(size=11), text_color="#ecf0f1")
        self._subtotal_lbl.pack(side="left", padx=16, pady=8)
        self._gst_lbl = ctk.CTkLabel(tot, text="GST: ₹ 0.00",
                                      font=ctk.CTkFont(size=11), text_color="#3498db")
        self._gst_lbl.pack(side="left", padx=12)
        self._grand_lbl = ctk.CTkLabel(tot, text="Grand Total: ₹ 0.00",
                                        font=ctk.CTkFont(size=13, weight="bold"),
                                        text_color="#2ecc71")
        self._grand_lbl.pack(side="right", padx=16)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(btn_row, text="Cancel", fg_color="#2c3e50", hover_color="#34495e",
                      command=self.destroy).pack(side="right")
        ctk.CTkButton(btn_row, text="Save Purchase", width=140,
                      fg_color="#8e44ad", hover_color="#6c3483",
                      command=self._save).pack(side="right", padx=8)

    def _add_item_row(self):
        row = ctk.CTkFrame(self._items_frame, fg_color="transparent")
        row.pack(fill="x", pady=1)
        desc  = ctk.CTkEntry(row, width=220, height=28, placeholder_text="Description")
        qty   = ctk.CTkEntry(row, width=60,  height=28, placeholder_text="1")
        price = ctk.CTkEntry(row, width=90,  height=28, placeholder_text="0.00")
        gst_v = ctk.StringVar(value="18")
        gst   = ctk.CTkComboBox(row, values=self.GST_RATES, variable=gst_v, width=70, height=28)
        amt_l = ctk.CTkLabel(row, text="₹ 0.00", width=90, font=ctk.CTkFont(size=11),
                              text_color="#2ecc71", anchor="e")
        rem   = ctk.CTkButton(row, text="✕", width=30, height=28,
                               fg_color="transparent", hover_color="#7f1f1f",
                               font=ctk.CTkFont(size=10))

        for w in (desc, qty, price, gst, amt_l, rem):
            w.pack(side="left", padx=3)

        item = {"frame": row, "desc": desc, "qty": qty, "price": price,
                "gst_v": gst_v, "amt_l": amt_l}
        self.items.append(item)
        rem.configure(command=lambda it=item: self._remove_item_row(it))

        for w in (qty, price):
            w.bind("<KeyRelease>", lambda e: self._recalc())
        gst_v.trace_add("write", lambda *_: self._recalc())

    def _remove_item_row(self, item):
        item["frame"].destroy()
        self.items.remove(item)
        self._recalc()

    def _recalc(self):
        supply = self._supply_var.get()
        subtotal = 0.0
        gst_total = 0.0
        for it in self.items:
            try:
                qty   = float(it["qty"].get() or "1")
                price = float(it["price"].get() or "0")
                gst_r = float(it["gst_v"].get() or "0")
            except ValueError:
                continue
            taxable = round(qty * price, 2)
            if supply == "intra":
                gst_amt = round(taxable * gst_r / 100, 2)
            else:
                gst_amt = round(taxable * gst_r / 100, 2)
            total = taxable + gst_amt
            it["amt_l"].configure(text=f"₹ {total:,.2f}")
            subtotal  += taxable
            gst_total += gst_amt
        grand = subtotal + gst_total
        self._subtotal_lbl.configure(text=f"Subtotal: ₹ {subtotal:,.2f}")
        self._gst_lbl.configure(text=f"GST: ₹ {gst_total:,.2f}")
        self._grand_lbl.configure(text=f"Grand Total: ₹ {grand:,.2f}")

    def _add_vendor_inline(self):
        name = ctk.CTkInputDialog(text="Vendor Name:", title="Add Vendor").get_input()
        if not name or not name.strip():
            return
        gstin = ctk.CTkInputDialog(text="GSTIN (optional):", title="Add Vendor").get_input() or ""
        db.add_vendor(name.strip(), gstin.strip())
        vendors = db.get_all_vendors()
        self._vendor_names = ["— No Vendor —"] + [v["name"] for v in vendors]
        self._vendor_map   = {v["name"]: v["id"] for v in vendors}
        self._vendor_cb.configure(values=self._vendor_names)
        self._vendor_var.set(name.strip())

    def _save(self):
        bill_date = self._bill_date.get().strip()
        if not bill_date:
            messagebox.showerror("Error", "Bill date is required.")
            return

        # Collect items (skip empty rows)
        rows = []
        supply = self._supply_var.get()
        for it in self.items:
            desc  = it["desc"].get().strip()
            if not desc:
                continue
            try:
                qty   = float(it["qty"].get() or "1")
                price = float(it["price"].get() or "0")
                gst_r = float(it["gst_v"].get() or "0")
            except ValueError:
                messagebox.showerror("Error", f"Invalid number in item '{desc}'.")
                return
            taxable = round(qty * price, 2)
            gst_amt = round(taxable * gst_r / 100, 2)
            cgst = sgst = igst = 0.0
            if supply == "intra":
                cgst = sgst = round(gst_amt / 2, 2)
            else:
                igst = gst_amt
            rows.append({
                "description": desc, "quantity": qty, "unit_price": price,
                "gst_rate": gst_r, "taxable_value": taxable, "gst_amt": gst_amt,
                "cgst_amt": cgst, "sgst_amt": sgst, "igst_amt": igst,
                "total_amt": round(taxable + gst_amt, 2),
            })

        if not rows:
            messagebox.showerror("Error", "Add at least one item.")
            return

        vendor_name = self._vendor_var.get()
        vendor_id   = self._vendor_map.get(vendor_name) if vendor_name != "— No Vendor —" else None
        bill_number = self._bill_number.get().strip()
        due_date    = self._due_date.get().strip()
        notes       = self._notes_var.get().strip()
        pay_raw     = self._pay_mode_var.get()
        payment_mode = "Cash" if "Cash" in pay_raw else ("Bank" if "Bank" in pay_raw else "Credit")

        try:
            db.save_purchase(vendor_id, bill_number, bill_date, due_date, rows,
                             supply, notes, payment_mode)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        messagebox.showinfo("Saved", "Purchase bill saved successfully!")
        self.app.refresh_current()
        self.destroy()


class PurchasePaymentDialog(ctk.CTkToplevel):
    """Record a payment against an Unpaid purchase bill."""

    def __init__(self, parent, app, purchase):
        super().__init__(parent)
        self.app      = app
        self.purchase = purchase
        self.title(f"Pay Bill – {purchase.get('bill_number') or 'ID ' + str(purchase['id'])}")
        self.geometry("400x340")
        self.grab_set()
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Record Payment",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="#ecf0f1").pack(padx=20, pady=(14, 4), anchor="w")

        p = self.purchase
        banner = ctk.CTkFrame(self, fg_color="#0f3460", corner_radius=8)
        banner.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(banner, text=f"{p.get('vendor_name','—')}  ·  {p.get('bill_number','—')}",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#8e44ad").pack(side="left", padx=14, pady=10)
        ctk.CTkLabel(banner, text=f"₹ {p['grand_total']:,.2f}",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#2ecc71").pack(side="right", padx=14)

        frame = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=10)
        frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        def lbl(text, default=""):
            ctk.CTkLabel(frame, text=text, text_color="#95a5a6",
                         font=ctk.CTkFont(size=10)).pack(anchor="w", padx=16, pady=(10, 0))
            var = ctk.StringVar(value=default)
            ctk.CTkEntry(frame, textvariable=var).pack(fill="x", padx=16, pady=(2, 0))
            return var

        def combo(text, values):
            ctk.CTkLabel(frame, text=text, text_color="#95a5a6",
                         font=ctk.CTkFont(size=10)).pack(anchor="w", padx=16, pady=(10, 0))
            var = ctk.StringVar(value=values[0])
            ctk.CTkComboBox(frame, values=values, variable=var).pack(fill="x", padx=16, pady=(2, 0))
            return var

        today = datetime.now().strftime("%Y-%m-%d")
        self.pay_date  = lbl("Payment Date *", today)
        self.amount    = lbl("Amount (₹) *", f"{p['grand_total']:.2f}")
        self.pay_mode  = combo("Payment Mode *", ["Cash", "Bank / UPI"])
        self.reference = lbl("Reference (UTR / Cheque)")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(btn_row, text="Cancel", fg_color="#2c3e50", hover_color="#34495e",
                      command=self.destroy).pack(side="right")
        ctk.CTkButton(btn_row, text="Record Payment", width=140,
                      fg_color="#8e44ad", hover_color="#6c3483",
                      command=self._save).pack(side="right", padx=8)

    def _save(self):
        date  = self.pay_date.get().strip()
        amt_s = self.amount.get().strip()
        mode  = self.pay_mode.get()
        ref   = self.reference.get().strip()
        if not date or not amt_s:
            messagebox.showerror("Error", "Date and amount are required.")
            return
        try:
            amt = float(amt_s)
            if amt <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Enter a valid positive amount.")
            return
        try:
            pay_mode = "Cash" if "Cash" in mode else "Bank"
            db.record_purchase_payment(self.purchase["id"], amt, date, pay_mode, ref)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return
        messagebox.showinfo("Done", f"Payment of ₹{amt:,.2f} recorded. Bill marked Paid.")
        self.app.refresh_current()
        self.destroy()


class VendorsDialog(ctk.CTkToplevel):
    """View, add, and delete vendors."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("Vendors / Suppliers")
        self.geometry("560x480")
        self.grab_set()
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Vendors / Suppliers",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="#ecf0f1").pack(padx=20, pady=(14, 4), anchor="w")

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=20, pady=(0, 8))
        ctk.CTkButton(bar, text="+ Add Vendor", fg_color="#8e44ad", hover_color="#6c3483",
                      command=self._add_vendor).pack(side="left")

        tbl = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=10)
        tbl.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        hdr = ctk.CTkFrame(tbl, fg_color="#0f3460", corner_radius=0)
        hdr.pack(fill="x")
        for col, w in [("Name", 180), ("GSTIN", 150), ("Phone", 110), ("State", 80), ("", 36)]:
            ctk.CTkLabel(hdr, text=col, font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#bdc3c7", width=w, anchor="w"
                         ).pack(side="left", padx=8, pady=7)

        self._scroll = ctk.CTkScrollableFrame(tbl, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True)
        self._populate()

    def _populate(self):
        for w in self._scroll.winfo_children():
            w.destroy()
        vendors = db.get_all_vendors()
        if not vendors:
            ctk.CTkLabel(self._scroll, text="No vendors yet.",
                         text_color="#7f8c8d").pack(pady=20)
            return
        for v in vendors:
            row = ctk.CTkFrame(self._scroll, fg_color="#1a1a2e", corner_radius=4)
            row.pack(fill="x", pady=1)
            for val, w in [(v["name"][:22], 180), (v["gstin"] or "—", 150),
                           (v["phone"] or "—", 110), (v["state"] or "—", 80)]:
                ctk.CTkLabel(row, text=str(val), font=ctk.CTkFont(size=11),
                             text_color="#ecf0f1", width=w, anchor="w"
                             ).pack(side="left", padx=8, pady=7)
            ctk.CTkButton(row, text="🗑", width=34, height=28,
                          fg_color="transparent", hover_color="#7f1f1f",
                          command=lambda vid=v["id"], nm=v["name"]: self._delete(vid, nm)
                          ).pack(side="left", padx=4)

    def _add_vendor(self):
        name = ctk.CTkInputDialog(text="Vendor Name:", title="Add Vendor").get_input()
        if not name or not name.strip():
            return
        gstin = ctk.CTkInputDialog(text="GSTIN (optional):", title="Add Vendor").get_input() or ""
        phone = ctk.CTkInputDialog(text="Phone (optional):", title="Add Vendor").get_input() or ""
        state = ctk.CTkInputDialog(text="State (optional):", title="Add Vendor").get_input() or ""
        db.add_vendor(name.strip(), gstin.strip(), phone.strip(), "", "", state.strip())
        self._populate()

    def _delete(self, vid, name):
        if messagebox.askyesno("Delete Vendor", f"Delete vendor '{name}'?"):
            db.delete_vendor(vid)
            self._populate()


# ── TDS Page ──────────────────────────────────────────────────────────────────

class TDSPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._type_filter   = "All"
        self._status_filter = "All"
        self._section_filter = "All"

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._header("TDS / TCS Tracker",
                     "Track Tax Deducted / Collected at Source (194Q, 194C, 194J …)")

        summary = db.get_tds_summary()

        # ── KPI tiles ────────────────────────────────────────────────────────
        sc = ctk.CTkFrame(self, fg_color="transparent")
        sc.pack(fill="x", padx=24, pady=(0, 10))
        for i in range(4):
            sc.columnconfigure(i, weight=1)
        for i, (title, val, color) in enumerate([
            ("TDS Payable (Pending)",
             f"₹ {summary['payable_pending']:,.0f}", "#e74c3c"),
            ("TDS Payable (Paid)",
             f"₹ {summary['payable_paid']:,.0f}", "#2ecc71"),
            ("TDS Receivable (Pending)",
             f"₹ {summary['receivable_pending']:,.0f}", "#f39c12"),
            ("TDS Receivable (Credited)",
             f"₹ {summary['receivable_credited']:,.0f}", "#3498db"),
        ]):
            c = self._card(sc, title, val, color)
            c.grid(row=0, column=i, padx=6, sticky="ew")

        # ── Toolbar ───────────────────────────────────────────────────────────
        tb = ctk.CTkFrame(self, fg_color="transparent")
        tb.pack(fill="x", padx=24, pady=(0, 8))

        ctk.CTkButton(tb, text="+ Add TDS Entry", fg_color="#2ecc71",
                      hover_color="#27ae60", text_color="#000", height=32,
                      command=lambda: TDSEntryDialog(self, self.app, on_save=self.refresh)
                      ).pack(side="left")

        # Type filter
        for label in ["All", "Payable", "Receivable"]:
            active = label == self._type_filter
            ctk.CTkButton(
                tb, text=label, width=84, height=28,
                fg_color="#0f3460" if active else "transparent",
                hover_color="#16213e", border_width=1, border_color="#0f3460",
                font=ctk.CTkFont(size=11),
                command=lambda l=label: self._set_type(l),
            ).pack(side="left", padx=3)

        # Status filter
        for label in ["Pending", "Paid", "Credited"]:
            active = label == self._status_filter
            ctk.CTkButton(
                tb, text=label, width=74, height=28,
                fg_color="#8e44ad" if active else "transparent",
                hover_color="#16213e", border_width=1, border_color="#8e44ad",
                font=ctk.CTkFont(size=11),
                command=lambda l=label: self._set_status(l),
            ).pack(side="left", padx=2)

        # Export buttons
        ctk.CTkButton(tb, text="📊 Excel", width=80, height=28,
                      fg_color="#16213e", hover_color="#0f3460",
                      font=ctk.CTkFont(size=11),
                      command=self._export_excel).pack(side="right", padx=3)
        ctk.CTkButton(tb, text="📄 PDF", width=70, height=28,
                      fg_color="#16213e", hover_color="#0f3460",
                      font=ctk.CTkFont(size=11),
                      command=self._export_pdf).pack(side="right", padx=3)

        # ── Table ─────────────────────────────────────────────────────────────
        tbl = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=12)
        tbl.pack(fill="both", expand=True, padx=24, pady=(0, 24))

        hdr = ctk.CTkFrame(tbl, fg_color="#0f3460", corner_radius=6)
        hdr.pack(fill="x", padx=12, pady=(12, 2))
        for col, w in [("Date", 90), ("Type", 76), ("Section", 90),
                       ("Deductee", 170), ("PAN", 110),
                       ("Taxable Amt", 110), ("Rate%", 54),
                       ("TDS Amt", 90), ("Status", 80), ("Actions", 160)]:
            ctk.CTkLabel(hdr, text=col, width=w,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#95a5a6").pack(side="left", padx=4, pady=6)

        scroll = ctk.CTkScrollableFrame(tbl, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        entries = [dict(r) for r in db.get_all_tds_entries(
            tds_type=self._type_filter,
            status=self._status_filter if self._status_filter != "All" else "All",
        )]

        if not entries:
            ctk.CTkLabel(scroll, text="No TDS entries found.",
                         text_color="#95a5a6").pack(pady=30)
        else:
            sc_map = {"Pending": "#f39c12", "Paid": "#2ecc71",
                      "Credited": "#3498db", "Cancelled": "#e74c3c"}
            for e in entries:
                type_color = "#e74c3c" if e["tds_type"] == "Payable" else "#3498db"
                st_color   = sc_map.get(e["status"], "#95a5a6")
                row = ctk.CTkFrame(scroll, fg_color="#16213e", corner_radius=6)
                row.pack(fill="x", pady=2)
                for val, w, color in [
                    (e["entry_date"],                     90,  "#95a5a6"),
                    (e["tds_type"],                       76,  type_color),
                    (e["section"],                        90,  "#f39c12"),
                    ((e["deductee_name"] or "—")[:22],   170,  "#ecf0f1"),
                    (e["deductee_pan"] or "—",           110,  "#bdc3c7"),
                    (f"₹{e['taxable_amount']:,.0f}",     110,  "#ecf0f1"),
                    (f"{e['tds_rate']}%",                 54,  "#95a5a6"),
                    (f"₹{e['total_tds']:,.2f}",           90,  "#2ecc71"),
                ]:
                    ctk.CTkLabel(row, text=str(val), width=w,
                                 font=ctk.CTkFont(size=11),
                                 text_color=color).pack(side="left", padx=4, pady=6)
                ctk.CTkLabel(row, text=e["status"], width=80,
                             font=ctk.CTkFont(size=10, weight="bold"),
                             text_color=st_color).pack(side="left", padx=4)

                ctk.CTkButton(row, text="Edit", width=42, height=26,
                              fg_color="#1a3a5c", hover_color="#2355c2",
                              font=ctk.CTkFont(size=10),
                              command=lambda eid=e["id"]: TDSEntryDialog(
                                  self, self.app, entry_id=eid, on_save=self.refresh)
                              ).pack(side="left", padx=2)

                if e["status"] == "Pending" and e["tds_type"] == "Payable":
                    ctk.CTkButton(row, text="✓ Pay", width=50, height=26,
                                  fg_color="#1a5c1a", hover_color="#27ae60",
                                  font=ctk.CTkFont(size=10),
                                  command=lambda eid=e["id"]: TDSChallanDialog(
                                      self, self.app, eid, on_save=self.refresh)
                                  ).pack(side="left", padx=2)

                if e["status"] == "Pending" and e["tds_type"] == "Receivable":
                    ctk.CTkButton(row, text="✓ Credit", width=56, height=26,
                                  fg_color="#1a3a5c", hover_color="#2980b9",
                                  font=ctk.CTkFont(size=10),
                                  command=lambda eid=e["id"]: self._mark_credited(eid)
                                  ).pack(side="left", padx=2)

                ctk.CTkButton(row, text="Del", width=38, height=26,
                              fg_color="#7f1f1f", hover_color="#c0392b",
                              font=ctk.CTkFont(size=10),
                              command=lambda eid=e["id"]: self._delete(eid)
                              ).pack(side="left", padx=2)

    # ── actions ───────────────────────────────────────────────────────────────

    def _set_type(self, t):
        self._type_filter = t; self.refresh()

    def _set_status(self, s):
        self._status_filter = "All" if s == self._status_filter else s
        self.refresh()

    def _mark_credited(self, entry_id):
        from datetime import date as _date
        db.mark_tds_paid(entry_id,
                         payment_date=_date.today().isoformat(),
                         challan_no="", challan_date="")
        with db.get_connection() as conn:
            conn.execute("UPDATE tds_entries SET status='Credited' WHERE id=?", (entry_id,))
            conn.commit()
        self.refresh()

    def _delete(self, entry_id):
        if messagebox.askyesno("Delete", "Delete this TDS entry?"):
            db.delete_tds_entry(entry_id)
            self.refresh()

    def _export_pdf(self):
        from report_export import export_tds_pdf
        firm = db.get_firm_settings()
        entries = [dict(r) for r in db.get_all_tds_entries(
            tds_type=self._type_filter,
            status=self._status_filter if self._status_filter != "All" else "All",
        )]
        path = filedialog.asksaveasfilename(
            title="Save TDS Report PDF",
            defaultextension=".pdf",
            initialfile="TDS_Report.pdf",
            filetypes=[("PDF files","*.pdf"),("All files","*.*")],
        )
        if path:
            try:
                export_tds_pdf(entries, dict(firm), path)
                os.startfile(path)
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def _export_excel(self):
        from report_export import export_tds_excel
        firm = db.get_firm_settings()
        entries = [dict(r) for r in db.get_all_tds_entries(
            tds_type=self._type_filter,
            status=self._status_filter if self._status_filter != "All" else "All",
        )]
        path = filedialog.asksaveasfilename(
            title="Save TDS Report Excel",
            defaultextension=".xlsx",
            initialfile="TDS_Report.xlsx",
            filetypes=[("Excel files","*.xlsx"),("All files","*.*")],
        )
        if path:
            try:
                export_tds_excel(entries, dict(firm), path)
                os.startfile(path)
            except Exception as e:
                messagebox.showerror("Error", str(e))


# ── TDS Entry Dialog ───────────────────────────────────────────────────────────

class TDSEntryDialog(ctk.CTkToplevel):
    """Add or edit a TDS/TCS entry."""

    def __init__(self, parent, app, entry_id=None, on_save=None):
        super().__init__(parent)
        self.app      = app
        self.entry_id = entry_id
        self.on_save  = on_save
        self.title("Edit TDS Entry" if entry_id else "Add TDS Entry")
        self.geometry("560x700")
        self.resizable(False, False)
        self.grab_set()
        self.after(50, self.lift)

        existing = None
        if entry_id:
            rows = db.get_all_tds_entries()
            for r in rows:
                if r["id"] == entry_id:
                    existing = dict(r); break

        hdr = ctk.CTkFrame(self, fg_color="#0f3460", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="🧾  TDS / TCS Entry",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(padx=20, pady=10)

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=12)

        def _row(label, widget_fn):
            ctk.CTkLabel(body, text=label, text_color="#95a5a6",
                         font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(6, 0))
            return widget_fn()

        today = datetime.now().strftime("%Y-%m-%d")
        self._date_var    = ctk.StringVar(value=existing["entry_date"] if existing else today)
        self._type_var    = ctk.StringVar(value=existing["tds_type"] if existing else "Payable")
        self._section_var = ctk.StringVar(value=existing["section"] if existing else "194Q")
        self._name_var    = ctk.StringVar(value=existing["deductee_name"] if existing else "")
        self._pan_var     = ctk.StringVar(value=existing["deductee_pan"] if existing else "")
        self._desc_var    = ctk.StringVar(value=existing["description"] if existing else "")
        self._taxable_var = ctk.StringVar(value=str(existing["taxable_amount"]) if existing else "")
        self._rate_var    = ctk.StringVar(value=str(existing["tds_rate"]) if existing else "0.1")
        self._tds_var     = ctk.StringVar(value=str(existing["tds_amount"]) if existing else "")
        self._surcharge_var = ctk.StringVar(value=str(existing["surcharge"] or 0) if existing else "0")
        self._cess_var    = ctk.StringVar(value=str(existing["cess"] or 0) if existing else "0")
        self._status_var  = ctk.StringVar(value=existing["status"] if existing else "Pending")
        self._notes_var   = ctk.StringVar(value=existing["notes"] if existing else "")

        _row("Entry Date", lambda: ctk.CTkEntry(body, textvariable=self._date_var).pack(fill="x") or None)
        _row("Type", lambda: ctk.CTkComboBox(body, values=["Payable","Receivable"],
                                              variable=self._type_var,
                                              command=self._on_type_change).pack(fill="x") or None)

        ctk.CTkLabel(body, text="Section", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(6, 0))
        sections = list(db.TDS_SECTIONS.keys())
        self._section_combo = ctk.CTkComboBox(body, values=sections,
                                              variable=self._section_var,
                                              command=self._on_section_change)
        self._section_combo.pack(fill="x")

        # Section description hint
        self._sec_desc_lbl = ctk.CTkLabel(body, text="", text_color="#7f8c8d",
                                           font=ctk.CTkFont(size=10))
        self._sec_desc_lbl.pack(anchor="w")
        self._refresh_section_hint()

        _row("Deductee / Deductor Name", lambda: ctk.CTkEntry(body, textvariable=self._name_var).pack(fill="x") or None)
        _row("PAN", lambda: ctk.CTkEntry(body, textvariable=self._pan_var,
                                          placeholder_text="ABCDE1234F").pack(fill="x") or None)
        _row("Description / Narration", lambda: ctk.CTkEntry(body, textvariable=self._desc_var).pack(fill="x") or None)

        ctk.CTkLabel(body, text="Taxable Amount (₹)", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(6, 0))
        taxable_entry = ctk.CTkEntry(body, textvariable=self._taxable_var)
        taxable_entry.pack(fill="x")
        taxable_entry.bind("<FocusOut>", lambda e: self._recalc())

        ctk.CTkLabel(body, text="TDS Rate (%)", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(6, 0))
        rate_entry = ctk.CTkEntry(body, textvariable=self._rate_var)
        rate_entry.pack(fill="x")
        rate_entry.bind("<FocusOut>", lambda e: self._recalc())

        ctk.CTkLabel(body, text="TDS Amount (₹)  [auto-calculated]", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(6, 0))
        ctk.CTkEntry(body, textvariable=self._tds_var).pack(fill="x")

        _row("Surcharge (₹)", lambda: ctk.CTkEntry(body, textvariable=self._surcharge_var).pack(fill="x") or None)
        _row("Health & Education Cess (₹)", lambda: ctk.CTkEntry(body, textvariable=self._cess_var).pack(fill="x") or None)

        _row("Status", lambda: ctk.CTkComboBox(
            body, values=["Pending","Paid","Credited","Cancelled"],
            variable=self._status_var).pack(fill="x") or None)
        _row("Notes", lambda: ctk.CTkEntry(body, textvariable=self._notes_var).pack(fill="x") or None)

        ctk.CTkButton(body, text="💾  Save Entry", height=38,
                      fg_color="#2ecc71", hover_color="#27ae60", text_color="#000",
                      command=self._save).pack(fill="x", pady=(16, 0))

    def _refresh_section_hint(self):
        sec = self._section_var.get()
        info = db.TDS_SECTIONS.get(sec, {})
        desc = info.get("desc", "")
        rate = info.get("rate", 0)
        threshold = info.get("threshold", 0)
        hint = f"{desc}  |  Standard rate: {rate}%"
        if threshold:
            hint += f"  |  Threshold: ₹{threshold:,}"
        self._sec_desc_lbl.configure(text=hint)

    def _on_section_change(self, val):
        info = db.TDS_SECTIONS.get(val, {})
        self._rate_var.set(str(info.get("rate", 0)))
        self._refresh_section_hint()
        self._recalc()

    def _on_type_change(self, val):
        if val == "Receivable":
            self._status_var.set("Pending")

    def _recalc(self):
        try:
            taxable = float(self._taxable_var.get() or 0)
            rate    = float(self._rate_var.get() or 0)
            tds     = round(taxable * rate / 100, 2)
            self._tds_var.set(str(tds))
        except ValueError:
            pass

    def _save(self):
        name = self._name_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Deductee/Deductor name is required.")
            return
        try:
            taxable  = float(self._taxable_var.get() or 0)
            rate     = float(self._rate_var.get() or 0)
            tds_amt  = float(self._tds_var.get() or 0)
            surcharge = float(self._surcharge_var.get() or 0)
            cess     = float(self._cess_var.get() or 0)
        except ValueError:
            messagebox.showerror("Error", "Enter valid numbers for amounts.")
            return

        kwargs = dict(
            entry_date=self._date_var.get(),
            tds_type=self._type_var.get(),
            section=self._section_var.get(),
            deductee_name=name,
            deductee_pan=self._pan_var.get().strip().upper(),
            description=self._desc_var.get().strip(),
            taxable_amount=taxable, tds_rate=rate, tds_amount=tds_amt,
            surcharge=surcharge, cess=cess,
            status=self._status_var.get(),
            notes=self._notes_var.get().strip(),
        )
        if self.entry_id:
            db.update_tds_entry(self.entry_id, **kwargs)
        else:
            db.save_tds_entry(**kwargs)

        if self.on_save:
            self.on_save()
        self.destroy()


# ── TDS Challan / Payment Dialog ───────────────────────────────────────────────

class TDSChallanDialog(ctk.CTkToplevel):
    """Record challan details when TDS is deposited to government."""

    def __init__(self, parent, app, entry_id: int, on_save=None):
        super().__init__(parent)
        self.app      = app
        self.entry_id = entry_id
        self.on_save  = on_save
        self.title("Record TDS Payment / Challan")
        self.geometry("440x380")
        self.resizable(False, False)
        self.grab_set()
        self.after(50, self.lift)

        hdr = ctk.CTkFrame(self, fg_color="#0f3460", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="🏦  TDS Challan Details",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(padx=20, pady=10)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=16)

        today = datetime.now().strftime("%Y-%m-%d")
        self._pay_date_var    = ctk.StringVar(value=today)
        self._challan_no_var  = ctk.StringVar()
        self._challan_date_var = ctk.StringVar(value=today)
        self._bsr_var         = ctk.StringVar()

        for label, var, placeholder in [
            ("Payment Date (YYYY-MM-DD)", self._pay_date_var, ""),
            ("Challan Number / CIN",      self._challan_no_var, "e.g. 12345678"),
            ("Challan Date (YYYY-MM-DD)", self._challan_date_var, ""),
            ("BSR Code (optional)",       self._bsr_var, "7-digit BSR code"),
        ]:
            ctk.CTkLabel(body, text=label, text_color="#95a5a6",
                         font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(8, 0))
            ctk.CTkEntry(body, textvariable=var,
                         placeholder_text=placeholder).pack(fill="x")

        ctk.CTkButton(body, text="✓  Mark as Paid", height=38,
                      fg_color="#2ecc71", hover_color="#27ae60", text_color="#000",
                      command=self._save).pack(fill="x", pady=(20, 0))

    def _save(self):
        db.mark_tds_paid(
            self.entry_id,
            payment_date  = self._pay_date_var.get(),
            challan_no    = self._challan_no_var.get().strip(),
            challan_date  = self._challan_date_var.get(),
            bsr_code      = self._bsr_var.get().strip(),
        )
        if self.on_save:
            self.on_save()
        self.destroy()


# ── Ledger Page ───────────────────────────────────────────────────────────────

class LedgerPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._header("Ledger", "Chart of accounts and journal entries")

        tabs = ctk.CTkTabview(self, fg_color="#16213e")
        tabs.pack(fill="both", expand=True, padx=24, pady=(0, 24))
        tabs.add("Chart of Accounts")
        tabs.add("Journal Entries")

        self._build_coa(tabs.tab("Chart of Accounts"))
        self._build_journal(tabs.tab("Journal Entries"))

    def _build_coa(self, parent):
        accounts = db.get_account_balances()
        groups = {"Asset": [], "Liability": [], "Income": [], "Expense": [], "Equity": []}
        for a in accounts:
            if a["account_type"] in groups:
                groups[a["account_type"]].append(a)

        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=12, pady=12)

        type_colors = {
            "Asset": "#3498db", "Liability": "#e74c3c",
            "Income": "#2ecc71", "Expense": "#e67e22", "Equity": "#9b59b6",
        }
        for atype, color in type_colors.items():
            accts = groups.get(atype, [])
            total = sum(
                (a["total_debit"] - a["total_credit"]) if atype in ("Asset", "Expense")
                else (a["total_credit"] - a["total_debit"])
                for a in accts
            )
            sec = ctk.CTkFrame(scroll, fg_color="#0f3460", corner_radius=6)
            sec.pack(fill="x", pady=(8, 2))
            ctk.CTkLabel(sec, text=f"{atype} Accounts",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=color).pack(side="left", padx=12, pady=6)
            ctk.CTkLabel(sec, text=f"₹ {total:,.2f}",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=color).pack(side="right", padx=12, pady=6)
            for a in accts:
                bal = (a["total_debit"] - a["total_credit"]) if atype in ("Asset", "Expense") \
                      else (a["total_credit"] - a["total_debit"])
                bal_str = f"₹ {bal:,.2f}" if bal >= 0 else f"(₹ {abs(bal):,.2f})"
                row = ctk.CTkFrame(scroll, fg_color="#16213e", corner_radius=4)
                row.pack(fill="x", pady=1)
                ctk.CTkLabel(row, text=a["code"], width=55,
                             font=ctk.CTkFont(size=11), text_color="#95a5a6"
                             ).pack(side="left", padx=8, pady=5)
                ctk.CTkLabel(row, text=a["name"], width=200,
                             font=ctk.CTkFont(size=11), text_color="#ecf0f1",
                             anchor="w").pack(side="left", padx=4)
                ctk.CTkLabel(row, text=bal_str, width=130,
                             font=ctk.CTkFont(size=11), text_color=color,
                             anchor="e").pack(side="right", padx=8)
                ctk.CTkButton(row, text="View", width=50, height=24,
                              fg_color="#0f3460", hover_color="#1a4a8a",
                              font=ctk.CTkFont(size=11),
                              command=lambda aid=a["id"], an=a["name"]: AccountLedgerDialog(self, aid, an)
                              ).pack(side="right", padx=4)

    def _build_journal(self, parent):
        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(12, 4))
        ctk.CTkButton(btn_row, text="+ New Journal Entry",
                      fg_color="#0f3460", hover_color="#1a4a8a",
                      command=lambda: JournalEntryDialog(self, self.app)
                      ).pack(side="left")

        entries = db.get_all_journal_entries()
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        if not entries:
            ctk.CTkLabel(scroll, text="No journal entries yet.",
                         text_color="#95a5a6").pack(pady=20)
            return

        hdr = ctk.CTkFrame(scroll, fg_color="#0f3460", corner_radius=4)
        hdr.pack(fill="x", pady=(0, 2))
        for col, w in [("Date", 100), ("Narration", 300), ("Reference", 130), ("Lines", 60), ("Dr Total", 100)]:
            ctk.CTkLabel(hdr, text=col, width=w,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#95a5a6").pack(side="left", padx=6, pady=4)

        for e in entries:
            row = ctk.CTkFrame(scroll, fg_color="#16213e", corner_radius=4)
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=e["entry_date"], width=100,
                         font=ctk.CTkFont(size=11), text_color="#95a5a6"
                         ).pack(side="left", padx=6, pady=5)
            ctk.CTkLabel(row, text=(e["narration"] or "")[:45], width=300,
                         font=ctk.CTkFont(size=11), text_color="#ecf0f1"
                         ).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=e["reference"] or "—", width=130,
                         font=ctk.CTkFont(size=11), text_color="#3498db"
                         ).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=str(e["line_count"]), width=60,
                         font=ctk.CTkFont(size=11), text_color="#95a5a6"
                         ).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=f"₹{e['total_dr']:,.2f}", width=100,
                         font=ctk.CTkFont(size=11), text_color="#2ecc71"
                         ).pack(side="left", padx=4)


# ── Account Ledger Dialog ──────────────────────────────────────────────────────

class AccountLedgerDialog(ctk.CTkToplevel):
    def __init__(self, parent, account_id, account_name):
        super().__init__(parent)
        self.title(f"Ledger — {account_name}")
        self.geometry("720x480")
        self.grab_set()
        self._build(account_id, account_name)

    def _build(self, account_id, account_name):
        ctk.CTkLabel(self, text=account_name,
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#3498db").pack(padx=20, pady=(16, 4), anchor="w")

        frame = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=10)
        frame.pack(fill="both", expand=True, padx=20, pady=(4, 20))

        hdr = ctk.CTkFrame(frame, fg_color="#0f3460", corner_radius=4)
        hdr.pack(fill="x", padx=8, pady=(8, 2))
        for col, w in [("Date", 100), ("Narration", 240), ("Debit", 90), ("Credit", 90), ("Balance", 100)]:
            ctk.CTkLabel(hdr, text=col, width=w,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#95a5a6").pack(side="left", padx=4, pady=4)

        scroll = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        txns = db.get_account_transactions(account_id)
        if not txns:
            ctk.CTkLabel(scroll, text="No transactions for this account.",
                         text_color="#555").pack(pady=20)
            return

        running = 0.0
        for t in txns:
            running += t["debit"] - t["credit"]
            bal_str = f"₹{running:,.2f}" if running >= 0 else f"(₹{abs(running):,.2f})"
            row = ctk.CTkFrame(scroll, fg_color="#16213e", corner_radius=4)
            row.pack(fill="x", pady=1)
            vals = [
                (t["entry_date"],                             100, "#95a5a6"),
                ((t["narration"] or "")[:30],                 240, "#ecf0f1"),
                (f"₹{t['debit']:,.2f}" if t["debit"] else "—",  90, "#3498db"),
                (f"₹{t['credit']:,.2f}" if t["credit"] else "—", 90, "#e74c3c"),
                (bal_str,                                     100, "#2ecc71" if running >= 0 else "#e74c3c"),
            ]
            for text, w, color in vals:
                ctk.CTkLabel(row, text=str(text), width=w,
                             font=ctk.CTkFont(size=10), text_color=color
                             ).pack(side="left", padx=4, pady=4)


# ── Journal Entry Dialog ───────────────────────────────────────────────────────

class JournalEntryDialog(ctk.CTkToplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("New Journal Entry")
        self.geometry("680x580")
        self.grab_set()
        self.lines = []
        self.accounts = db.get_all_accounts()
        self.acct_names = [f"{a['code']} – {a['name']}" for a in self.accounts]
        self.acct_map   = {f"{a['code']} – {a['name']}": a for a in self.accounts}
        self._build()

    def _build(self):
        main = ctk.CTkScrollableFrame(self, fg_color="#0d1117")
        main.pack(fill="both", expand=True)

        ctk.CTkLabel(main, text="New Journal Entry",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#ecf0f1").pack(padx=20, pady=(16, 4), anchor="w")

        hdr_frame = ctk.CTkFrame(main, fg_color="#16213e", corner_radius=10)
        hdr_frame.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(hdr_frame, text="Entry Details",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#95a5a6").pack(padx=14, pady=(10, 2), anchor="w")

        def lbl_entry(par, label, default=""):
            ctk.CTkLabel(par, text=label, text_color="#95a5a6",
                         font=ctk.CTkFont(size=10)).pack(anchor="w", padx=14, pady=(6, 0))
            var = ctk.StringVar(value=default)
            ctk.CTkEntry(par, textvariable=var).pack(fill="x", padx=14, pady=(2, 0))
            return var

        today = datetime.now().strftime("%Y-%m-%d")
        self.je_date   = lbl_entry(hdr_frame, "Date *", today)
        self.narration = lbl_entry(hdr_frame, "Narration *")
        self.reference = lbl_entry(hdr_frame, "Reference")
        ctk.CTkFrame(hdr_frame, fg_color="transparent", height=8).pack()

        add_sec = ctk.CTkFrame(main, fg_color="#16213e", corner_radius=10)
        add_sec.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(add_sec, text="Add Line",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#95a5a6").pack(padx=14, pady=(10, 4), anchor="w")

        add_row = ctk.CTkFrame(add_sec, fg_color="transparent")
        add_row.pack(fill="x", padx=14, pady=(0, 10))
        ctk.CTkLabel(add_row, text="Account:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.line_acct = ctk.StringVar(value=self.acct_names[0] if self.acct_names else "")
        ctk.CTkComboBox(add_row, values=self.acct_names, variable=self.line_acct,
                        width=230).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(add_row, text="Dr:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 2))
        self.line_dr = ctk.CTkEntry(add_row, width=80, placeholder_text="0.00")
        self.line_dr.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(add_row, text="Cr:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 2))
        self.line_cr = ctk.CTkEntry(add_row, width=80, placeholder_text="0.00")
        self.line_cr.pack(side="left", padx=(0, 8))
        ctk.CTkButton(add_row, text="Add", width=70, height=30,
                      fg_color="#0f3460", hover_color="#1a4a8a",
                      command=self._add_line).pack(side="left")

        ctk.CTkLabel(main, text="Journal Lines",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#ecf0f1").pack(padx=20, pady=(4, 2), anchor="w")

        lines_frame = ctk.CTkFrame(main, fg_color="#16213e", corner_radius=10)
        lines_frame.pack(fill="x", padx=20, pady=(0, 8))
        hdr_row = ctk.CTkFrame(lines_frame, fg_color="#0f3460", corner_radius=4)
        hdr_row.pack(fill="x", padx=8, pady=(8, 2))
        for col, w in [("Account", 250), ("Debit", 100), ("Credit", 100)]:
            ctk.CTkLabel(hdr_row, text=col, width=w,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#95a5a6").pack(side="left", padx=4, pady=4)

        self._lines_scroll = ctk.CTkScrollableFrame(lines_frame, fg_color="transparent", height=110)
        self._lines_scroll.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkLabel(self._lines_scroll, text="No lines yet.", text_color="#555").pack(pady=10)

        self._totals_lbl = ctk.CTkLabel(main, text="Dr: ₹0.00  |  Cr: ₹0.00",
                                         text_color="#f39c12",
                                         font=ctk.CTkFont(size=12))
        self._totals_lbl.pack(anchor="e", padx=24, pady=(0, 6))

        btn_row = ctk.CTkFrame(main, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 20))
        ctk.CTkButton(btn_row, text="Cancel",
                      fg_color="#7f1f1f", hover_color="#c0392b",
                      command=self.destroy).pack(side="right")
        ctk.CTkButton(btn_row, text="Save Entry", width=120,
                      fg_color="#2ecc71", hover_color="#27ae60", text_color="#000",
                      command=self._save).pack(side="right", padx=8)

    def _add_line(self):
        name = self.line_acct.get()
        a = self.acct_map.get(name)
        if not a:
            return
        try:
            dr = float(self.line_dr.get() or 0)
            cr = float(self.line_cr.get() or 0)
        except ValueError:
            messagebox.showerror("Error", "Enter valid numeric values.")
            return
        if dr == 0 and cr == 0:
            messagebox.showerror("Error", "Enter either a Debit or Credit amount.")
            return
        self.lines.append({"account_id": a["id"], "account_name": a["name"], "debit": dr, "credit": cr})
        self.line_dr.delete(0, "end")
        self.line_cr.delete(0, "end")
        self._refresh_lines()

    def _refresh_lines(self):
        for w in self._lines_scroll.winfo_children():
            w.destroy()
        if not self.lines:
            ctk.CTkLabel(self._lines_scroll, text="No lines yet.", text_color="#555").pack(pady=10)
            self._totals_lbl.configure(text="Dr: ₹0.00  |  Cr: ₹0.00")
            return
        for idx, l in enumerate(self.lines):
            row = ctk.CTkFrame(self._lines_scroll, fg_color="#16213e", corner_radius=4)
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=l["account_name"][:35], width=250,
                         font=ctk.CTkFont(size=10), text_color="#ecf0f1"
                         ).pack(side="left", padx=4, pady=4)
            ctk.CTkLabel(row, text=f"₹{l['debit']:,.2f}" if l["debit"] else "—", width=100,
                         font=ctk.CTkFont(size=10), text_color="#3498db"
                         ).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=f"₹{l['credit']:,.2f}" if l["credit"] else "—", width=100,
                         font=ctk.CTkFont(size=10), text_color="#e74c3c"
                         ).pack(side="left", padx=4)
            ctk.CTkButton(row, text="✕", width=28, height=22,
                          fg_color="#7f1f1f", hover_color="#c0392b",
                          font=ctk.CTkFont(size=10),
                          command=lambda i=idx: self._remove_line(i)).pack(side="left", padx=2)
        total_dr = sum(l["debit"]  for l in self.lines)
        total_cr = sum(l["credit"] for l in self.lines)
        balanced = abs(total_dr - total_cr) < 0.01
        clr = "#2ecc71" if balanced else "#e74c3c"
        self._totals_lbl.configure(
            text=f"Dr: ₹{total_dr:,.2f}  |  Cr: ₹{total_cr:,.2f}  {'✓ Balanced' if balanced else '✗ Unbalanced'}",
            text_color=clr,
        )

    def _remove_line(self, idx):
        self.lines.pop(idx)
        self._refresh_lines()

    def _save(self):
        date = self.je_date.get().strip()
        narr = self.narration.get().strip()
        ref  = self.reference.get().strip()
        if not date or not narr:
            messagebox.showerror("Error", "Date and narration are required.")
            return
        if not self.lines:
            messagebox.showerror("Error", "Add at least one journal line.")
            return
        try:
            db.add_journal_entry(date, narr, ref, self.lines)
        except ValueError as e:
            messagebox.showerror("Not Balanced", str(e))
            return
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return
        messagebox.showinfo("Saved", "Journal entry saved successfully!")
        self.app.refresh_current()
        self.destroy()


# ── Sales Summary Page ────────────────────────────────────────────────────────

class SalesSummaryPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._group = "day"

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._header("Sales Summary", "Daily & Weekly Revenue Breakdown")

        ctrl = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=10)
        ctrl.pack(fill="x", padx=24, pady=(0, 4))
        inner = ctk.CTkFrame(ctrl, fg_color="transparent")
        inner.pack(padx=16, pady=(12, 4))

        today = datetime.now()
        from_def = (today - timedelta(days=29)).strftime("%Y-%m-%d")
        to_def   = today.strftime("%Y-%m-%d")

        ctk.CTkLabel(inner, text="From:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.from_date = ctk.CTkEntry(inner, width=120)
        self.from_date.insert(0, from_def)
        self.from_date.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(inner, text="To:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.to_date = ctk.CTkEntry(inner, width=120)
        self.to_date.insert(0, to_def)
        self.to_date.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(inner, text="Group:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self._group_var = ctk.StringVar(value=self._group)
        ctk.CTkSegmentedButton(inner, values=["day", "week"],
                               variable=self._group_var,
                               width=140).pack(side="left", padx=(0, 12))

        ctk.CTkButton(inner, text="Generate", width=120, height=36,
                      fg_color="#0f3460", hover_color="#1a4a8a",
                      command=self._generate).pack(side="left")
        _export_btns(inner, self._export_pdf, self._export_excel, self._export_csv)
        ctk.CTkFrame(inner, fg_color="#2c3e50", width=1, height=28
                     ).pack(side="left", padx=10, pady=4, fill="y")
        ctk.CTkButton(inner, text="🤖 AI Insights", width=104, height=34,
                      fg_color="#4a235a", hover_color="#6c3483",
                      font=ctk.CTkFont(size=11),
                      command=self._show_ai_insights).pack(side="left", padx=2)

        pr = ctk.CTkFrame(ctrl, fg_color="transparent")
        pr.pack(padx=16, pady=(0, 10), anchor="w")
        ctk.CTkLabel(pr, text="Quick:", text_color="#555",
                     font=ctk.CTkFont(size=10)).pack(side="left", padx=(0, 6))
        for lbl, cmd in [("Today",         self._preset_today),
                         ("This Week",     self._preset_this_week),
                         ("Last 7 Days",   self._preset_last7),
                         ("This Month",    self._preset_this_month),
                         ("Last 30 Days",  self._preset_last30),
                         ("This Year",     self._preset_this_year)]:
            ctk.CTkButton(pr, text=lbl, width=84, height=22,
                          fg_color="#1e3a5f", hover_color="#2a4a7f",
                          font=ctk.CTkFont(size=10),
                          command=cmd).pack(side="left", padx=(0, 4))

        self._area = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._area.pack(fill="both", expand=True, padx=24, pady=(0, 24))
        ctk.CTkLabel(self._area, text="Select a date range and click 'Generate'",
                     text_color="#555", font=ctk.CTkFont(size=13)).pack(pady=40)

    # ── Presets ──
    def _preset_today(self):
        t = datetime.now().strftime("%Y-%m-%d")
        self._set_dates(t, t)
        self._group_var.set("day")
        self._generate()

    def _preset_this_week(self):
        today = datetime.now()
        mon = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
        self._set_dates(mon, today.strftime("%Y-%m-%d"))
        self._group_var.set("day")
        self._generate()

    def _preset_last7(self):
        today = datetime.now()
        self._set_dates((today - timedelta(days=6)).strftime("%Y-%m-%d"),
                        today.strftime("%Y-%m-%d"))
        self._group_var.set("day")
        self._generate()

    def _preset_this_month(self):
        today = datetime.now()
        self._set_dates(today.replace(day=1).strftime("%Y-%m-%d"),
                        today.strftime("%Y-%m-%d"))
        self._group_var.set("day")
        self._generate()

    def _preset_last30(self):
        today = datetime.now()
        self._set_dates((today - timedelta(days=29)).strftime("%Y-%m-%d"),
                        today.strftime("%Y-%m-%d"))
        self._group_var.set("day")
        self._generate()

    def _preset_this_year(self):
        today = datetime.now()
        self._set_dates(f"{today.year}-01-01", today.strftime("%Y-%m-%d"))
        self._group_var.set("week")
        self._generate()

    def _set_dates(self, f, t):
        self.from_date.delete(0, "end"); self.from_date.insert(0, f)
        self.to_date.delete(0, "end");   self.to_date.insert(0, t)

    # ── Generate ──
    def _generate(self):
        for w in self._area.winfo_children():
            w.destroy()
        from_d = self.from_date.get().strip()
        to_d   = self.to_date.get().strip()
        if not from_d or not to_d:
            messagebox.showerror("Error", "Enter both dates.")
            return
        self._group = self._group_var.get()
        data = db.get_sales_summary(from_d, to_d, self._group)
        self._last_data = data

        if not data["rows"]:
            ctk.CTkLabel(self._area, text="No sales data for this period.",
                         text_color="#555", font=ctk.CTkFont(size=13)).pack(pady=40)
            return

        # KPI tiles
        kpi = ctk.CTkFrame(self._area, fg_color="transparent")
        kpi.pack(fill="x", pady=(0, 10))
        period_label = "day" if self._group == "day" else "week"
        for title, val, color in [
            ("Total Revenue",     f"₹{data['total_revenue']:,.0f}",    "#2ecc71"),
            ("Invoices",          str(data["total_invoices"]),           "#3498db"),
            (f"Avg / {period_label}",  f"₹{data['avg_per_period']:,.0f}", "#f39c12"),
            ("Peak Revenue",      f"₹{data['peak_revenue']:,.0f}",      "#9b59b6"),
            ("Peak Period",       data["peak_period"],                   "#1abc9c"),
        ]:
            tile = ctk.CTkFrame(kpi, fg_color="#16213e", corner_radius=8)
            tile.pack(side="left", padx=(0, 6), ipadx=12, ipady=6)
            ctk.CTkLabel(tile, text=title, text_color="#95a5a6",
                         font=ctk.CTkFont(size=10)).pack()
            ctk.CTkLabel(tile, text=val, text_color=color,
                         font=ctk.CTkFont(size=14, weight="bold")).pack()

        # Bar chart
        self._draw_chart(data["rows"])

        # Divider
        ctk.CTkFrame(self._area, fg_color="#0f3460", height=1).pack(fill="x", padx=0, pady=(8, 4))

        # Two-column layout: table left, breakdowns right
        body = ctk.CTkFrame(self._area, fg_color="transparent")
        body.pack(fill="x")
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)

        # Table
        tbl_wrap = ctk.CTkFrame(body, fg_color="transparent")
        tbl_wrap.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ctk.CTkLabel(tbl_wrap, text=f"{'Daily' if self._group == 'day' else 'Weekly'} Breakdown",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#ecf0f1").pack(anchor="w", pady=(0, 4))
        hdr = ctk.CTkFrame(tbl_wrap, fg_color="#0f3460", corner_radius=6)
        hdr.pack(fill="x", pady=(0, 2))
        for col, w in [("Period", 130), ("Invoices", 80), ("Revenue", 120), ("Avg Order", 110)]:
            ctk.CTkLabel(hdr, text=col, font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#ecf0f1", width=w, anchor="w").pack(side="left", padx=4, pady=5)
        max_rev = max((r["revenue"] for r in data["rows"]), default=1) or 1
        for r in data["rows"]:
            row_bg = "#1a1a2e" if data["rows"].index(r) % 2 == 0 else "#16213e"
            row = ctk.CTkFrame(tbl_wrap, fg_color=row_bg, corner_radius=4)
            row.pack(fill="x", pady=1)
            is_peak = r["period"] == data["peak_period"]
            ctk.CTkLabel(row, text=r["period"], width=130, anchor="w",
                         font=ctk.CTkFont(size=11),
                         text_color="#f39c12" if is_peak else "#ecf0f1").pack(side="left", padx=4, pady=4)
            ctk.CTkLabel(row, text=str(r["invoice_count"]), width=80, anchor="center",
                         font=ctk.CTkFont(size=11)).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=f"₹{r['revenue']:,.0f}", width=120, anchor="e",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#2ecc71").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=f"₹{r['avg_order']:,.0f}", width=110, anchor="e",
                         font=ctk.CTkFont(size=11),
                         text_color="#95a5a6").pack(side="left", padx=4)
        # Totals
        tot = ctk.CTkFrame(tbl_wrap, fg_color="#0f3460", corner_radius=4)
        tot.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(tot, text="TOTAL", width=130, anchor="w",
                     font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=4, pady=5)
        ctk.CTkLabel(tot, text=str(data["total_invoices"]), width=80, anchor="center",
                     font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=4)
        ctk.CTkLabel(tot, text=f"₹{data['total_revenue']:,.0f}", width=120, anchor="e",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color="#2ecc71").pack(side="left", padx=4)

        # Breakdowns panel
        brk = ctk.CTkFrame(body, fg_color="transparent")
        brk.grid(row=0, column=1, sticky="nsew")
        self._render_top5(brk, "Top Clients", data["top_clients"],
                          name_key="name", rev_key="revenue", count_key="cnt")
        self._render_top5(brk, "Top Products", data["top_products"],
                          name_key="description", rev_key="revenue", count_key="qty")

    def _draw_chart(self, rows):
        if not rows:
            return
        chart_wrap = ctk.CTkFrame(self._area, fg_color="#16213e", corner_radius=10)
        chart_wrap.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(chart_wrap, text="Revenue Chart",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#95a5a6").pack(anchor="w", padx=12, pady=(8, 4))

        max_rev = max((r["revenue"] for r in rows), default=1) or 1
        chart_h = 100  # bar area height px
        bar_area = ctk.CTkFrame(chart_wrap, fg_color="transparent", height=chart_h + 24)
        bar_area.pack(fill="x", padx=12, pady=(0, 8))
        bar_area.pack_propagate(False)

        # Show up to 60 bars; skip labels if too many
        display = rows if len(rows) <= 60 else rows
        bar_w = max(4, min(28, (bar_area.winfo_reqwidth() or 900) // max(len(display), 1) - 2))

        for r in display:
            pct = r["revenue"] / max_rev
            bar_h = max(2, int(pct * chart_h))
            col = ("#2ecc71" if pct > 0.7 else "#f39c12" if pct > 0.3 else "#3498db")
            col_frame = ctk.CTkFrame(bar_area, fg_color="transparent")
            col_frame.pack(side="left", padx=1, fill="y", anchor="s")
            # spacer at top
            ctk.CTkFrame(col_frame, fg_color="transparent",
                         height=chart_h - bar_h).pack()
            ctk.CTkFrame(col_frame, fg_color=col,
                         width=bar_w, height=bar_h,
                         corner_radius=2).pack()
            if len(rows) <= 14:
                ctk.CTkLabel(col_frame, text=r["period"][-5:],
                             text_color="#555", font=ctk.CTkFont(size=8),
                             width=bar_w).pack()

    def _render_top5(self, parent, title, items, name_key, rev_key, count_key):
        ctk.CTkLabel(parent, text=title,
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#ecf0f1").pack(anchor="w", pady=(8, 4))
        if not items:
            ctk.CTkLabel(parent, text="No data.", text_color="#555",
                         font=ctk.CTkFont(size=11)).pack(anchor="w")
            return
        max_rev = items[0][rev_key] or 1
        for it in items:
            row = ctk.CTkFrame(parent, fg_color="#16213e", corner_radius=6)
            row.pack(fill="x", pady=2)
            pct = it[rev_key] / max_rev
            bar_bg = ctk.CTkFrame(row, fg_color="#0d1b2a", corner_radius=4,
                                  height=28)
            bar_bg.pack(fill="x", padx=6, pady=4)
            bar_bg.pack_propagate(False)
            fill_w = max(4, int(pct * 200))
            ctk.CTkFrame(bar_bg, fg_color="#1a4a8a", width=fill_w,
                         corner_radius=4).place(x=0, y=0, relheight=1.0)
            ctk.CTkLabel(bar_bg, text=f"{it[name_key][:20]}",
                         font=ctk.CTkFont(size=10), anchor="w",
                         text_color="#ecf0f1").place(x=6, rely=0.5, anchor="w")
            ctk.CTkLabel(bar_bg, text=f"₹{it[rev_key]:,.0f}",
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#2ecc71").place(relx=1.0, x=-6, rely=0.5, anchor="e")

    def _show_ai_insights(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("AI Insights", "Generate the report first.")
            return
        d = self._last_data
        rows_txt = "\n".join(
            f"  {r['period']}: ₹{r['revenue']:,.0f} ({r['invoice_count']} invoices)"
            for r in d["rows"][:14]
        )
        clients_txt = "\n".join(
            f"  {c['name']}: ₹{c['revenue']:,.0f} ({c['cnt']} invoices)"
            for c in d["top_clients"]
        )
        products_txt = "\n".join(
            f"  {p['description']}: ₹{p['revenue']:,.0f} (qty {p['qty']})"
            for p in d["top_products"]
        )
        prompt = (
            f"You are a sales analyst for an Indian business.\n\n"
            f"Sales Summary: {d['from_date']} to {d['to_date']} (grouped by {d['group_by']})\n"
            f"Total Revenue: ₹{d['total_revenue']:,.0f}  |  Invoices: {d['total_invoices']}\n"
            f"Avg per {d['group_by']}: ₹{d['avg_per_period']:,.0f}  |  "
            f"Peak: {d['peak_period']} (₹{d['peak_revenue']:,.0f})\n\n"
            f"Revenue by {d['group_by']}:\n{rows_txt}\n\n"
            f"Top clients:\n{clients_txt or '  (none)'}\n\n"
            f"Top products:\n{products_txt or '  (none)'}\n\n"
            "Provide 5 specific insights numbered 1–5 on: revenue trends, peak vs trough analysis, "
            "client concentration risk, product performance, and growth recommendations."
        )
        AIInsightsDialog(self, "Sales Summary", prompt)

    def _export_pdf(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("Export", "Generate the report first.")
            return
        import tkinter.filedialog as fd
        fp = fd.asksaveasfilename(defaultextension=".pdf",
                                  filetypes=[("PDF", "*.pdf")],
                                  initialfile="sales_summary.pdf")
        if not fp:
            return
        import report_export as rex
        rex.export_sales_summary_pdf(self._last_data, db.get_firm_settings(), fp)
        messagebox.showinfo("Exported", f"PDF saved:\n{fp}")

    def _export_excel(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("Export", "Generate the report first.")
            return
        import tkinter.filedialog as fd
        fp = fd.asksaveasfilename(defaultextension=".xlsx",
                                  filetypes=[("Excel", "*.xlsx")],
                                  initialfile="sales_summary.xlsx")
        if not fp:
            return
        import report_export as rex
        rex.export_sales_summary_excel(self._last_data, db.get_firm_settings(), fp)
        messagebox.showinfo("Exported", f"Excel saved:\n{fp}")

    def _export_csv(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("Export", "Generate the report first.")
            return
        import tkinter.filedialog as fd
        fp = fd.asksaveasfilename(defaultextension=".csv",
                                  filetypes=[("CSV", "*.csv")],
                                  initialfile="sales_summary.csv")
        if not fp:
            return
        import report_export as rex
        rex.export_sales_summary_csv(self._last_data, fp)
        messagebox.showinfo("Exported", f"CSV saved:\n{fp}")


# ── P&L Report Page ────────────────────────────────────────────────────────────

class PLReportPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._header("P&L Report", "Profit & Loss Statement")

        ctrl = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=10)
        ctrl.pack(fill="x", padx=24, pady=(0, 4))
        inner = ctk.CTkFrame(ctrl, fg_color="transparent")
        inner.pack(padx=16, pady=(12, 4))

        today = datetime.now()
        from_def = today.replace(day=1).strftime("%Y-%m-%d")
        to_def   = today.strftime("%Y-%m-%d")

        ctk.CTkLabel(inner, text="From:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.from_date = ctk.CTkEntry(inner, width=120)
        self.from_date.insert(0, from_def)
        self.from_date.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(inner, text="To:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.to_date = ctk.CTkEntry(inner, width=120)
        self.to_date.insert(0, to_def)
        self.to_date.pack(side="left", padx=(0, 16))

        ctk.CTkButton(inner, text="Generate Report", width=150, height=36,
                      fg_color="#0f3460", hover_color="#1a4a8a",
                      command=self._generate).pack(side="left")
        _export_btns(inner, self._export_pdf, self._export_excel, self._export_csv)
        ctk.CTkFrame(inner, fg_color="#2c3e50", width=1, height=28
                     ).pack(side="left", padx=10, pady=4, fill="y")
        ctk.CTkButton(inner, text="✨ AI Insights", width=112, height=34,
                      fg_color="#6c3483", hover_color="#8e44ad",
                      font=ctk.CTkFont(size=11),
                      command=self._show_ai_insights).pack(side="left", padx=2)

        pr = ctk.CTkFrame(ctrl, fg_color="transparent")
        pr.pack(padx=16, pady=(0, 10), anchor="w")
        ctk.CTkLabel(pr, text="Quick:", text_color="#555",
                     font=ctk.CTkFont(size=10)).pack(side="left", padx=(0, 6))
        for lbl, cmd in [("This Month",   self._preset_this_month),
                         ("Last Month",   self._preset_last_month),
                         ("This Quarter", self._preset_this_qtr),
                         ("This Year",    self._preset_this_year)]:
            ctk.CTkButton(pr, text=lbl, width=88, height=22,
                          fg_color="#1e3a5f", hover_color="#2a4a7f",
                          font=ctk.CTkFont(size=10),
                          command=cmd).pack(side="left", padx=(0, 4))

        self._report_area = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._report_area.pack(fill="both", expand=True, padx=24, pady=(0, 24))
        ctk.CTkLabel(self._report_area,
                     text="Select a date range and click 'Generate Report'",
                     text_color="#555", font=ctk.CTkFont(size=13)).pack(pady=40)

    def _generate(self):
        for w in self._report_area.winfo_children():
            w.destroy()
        from_d = self.from_date.get().strip()
        to_d   = self.to_date.get().strip()
        if not from_d or not to_d:
            messagebox.showerror("Error", "Enter both From and To dates.")
            return
        data = db.get_pl_report(from_d, to_d)
        self._last_data, self._last_from, self._last_to = data, from_d, to_d

        # KPI summary strip
        kpi = ctk.CTkFrame(self._report_area, fg_color="transparent")
        kpi.pack(fill="x", pady=(4, 8))
        profit = data["net_profit"]
        margin = (profit / data["total_income"] * 100) if data["total_income"] else 0
        p_col  = "#2ecc71" if profit >= 0 else "#e74c3c"
        for title, val, col in [
            ("Total Income",   f"₹ {data['total_income']:,.0f}",   "#2ecc71"),
            ("Total Expenses", f"₹ {data['total_expenses']:,.0f}", "#e74c3c"),
            ("Net " + ("Profit" if profit >= 0 else "Loss"),
                               f"₹ {abs(profit):,.0f}",             p_col),
            ("Profit Margin",  f"{margin:.1f} %",                   p_col),
        ]:
            c = self._card(kpi, title, val, col, "")
            c.pack(side="left", padx=(0, 8), fill="x", expand=True)

        ctk.CTkLabel(self._report_area, text="PROFIT & LOSS STATEMENT",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#ecf0f1").pack(pady=(12, 2))
        ctk.CTkLabel(self._report_area, text=f"Period: {from_d}  to  {to_d}",
                     text_color="#95a5a6", font=ctk.CTkFont(size=11)).pack()
        firm = db.get_firm_settings()
        if firm and firm["firm_name"]:
            ctk.CTkLabel(self._report_area, text=firm["firm_name"],
                         text_color="#3498db",
                         font=ctk.CTkFont(size=13)).pack(pady=(2, 12))

        def divider():
            ctk.CTkFrame(self._report_area, fg_color="#0f3460", height=1).pack(fill="x", padx=20, pady=4)

        def sec_hdr(text, color):
            f = ctk.CTkFrame(self._report_area, fg_color="#0f3460", corner_radius=4)
            f.pack(fill="x", padx=20, pady=(10, 2))
            ctk.CTkLabel(f, text=text,
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=color).pack(padx=14, pady=6, anchor="w")

        def line_row(name, amount, color="#ecf0f1", bold=False, indent=True):
            row = ctk.CTkFrame(self._report_area, fg_color="transparent")
            row.pack(fill="x", padx=(40 if indent else 20), pady=1)
            ctk.CTkLabel(row, text=name,
                         font=ctk.CTkFont(size=11, weight="bold" if bold else "normal"),
                         text_color=color).pack(side="left")
            ctk.CTkLabel(row, text=f"₹ {amount:,.2f}",
                         font=ctk.CTkFont(size=11, weight="bold" if bold else "normal"),
                         text_color=color).pack(side="right")

        sec_hdr("INCOME", "#2ecc71")
        for name, amt in data["income"]:
            if amt != 0:
                line_row(name, amt)
        divider()
        line_row("Total Income", data["total_income"], "#2ecc71", bold=True, indent=False)

        sec_hdr("EXPENSES", "#e74c3c")
        for name, amt in data["expenses"]:
            if amt != 0:
                line_row(name, amt)
        divider()
        line_row("Total Expenses", data["total_expenses"], "#e74c3c", bold=True, indent=False)

        profit = data["net_profit"]
        p_color = "#2ecc71" if profit >= 0 else "#e74c3c"
        p_label = "NET PROFIT" if profit >= 0 else "NET LOSS"
        banner = ctk.CTkFrame(self._report_area, fg_color="#0f3460", corner_radius=8)
        banner.pack(fill="x", padx=20, pady=12)
        ctk.CTkLabel(banner, text=p_label,
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=p_color).pack(side="left", padx=16, pady=12)
        ctk.CTkLabel(banner, text=f"₹ {abs(profit):,.2f}",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=p_color).pack(side="right", padx=16, pady=12)

        # ── Visual income vs expense bar ──────────────────────────────────────
        self._render_pl_chart(data)

        # ── Monthly trend table ───────────────────────────────────────────────
        monthly = db.get_pl_monthly(from_d, to_d)
        if len(monthly) > 1:
            sec_hdr("MONTHLY TREND", "#3498db")
            hdr_row = ctk.CTkFrame(self._report_area, fg_color="#0f3460", corner_radius=0)
            hdr_row.pack(fill="x", padx=20)
            for txt, w, anch in [("Month",120,"w"),("Income ₹",130,"e"),
                                  ("Expenses ₹",130,"e"),("Net ₹",120,"e")]:
                ctk.CTkLabel(hdr_row, text=txt, width=w, anchor=anch,
                             font=ctk.CTkFont(size=10, weight="bold"),
                             text_color="#95a5a6").pack(side="left", padx=8, pady=5)
            for i, r in enumerate(monthly):
                bg = "#1a1a2e" if i % 2 == 0 else "#16213e"
                net = r["income"] - r["expense"]
                net_clr = "#2ecc71" if net >= 0 else "#e74c3c"
                rw = ctk.CTkFrame(self._report_area, fg_color=bg, corner_radius=0)
                rw.pack(fill="x", padx=20)
                for txt, w, anch, clr in [
                    (r["month"], 120, "w", "#ecf0f1"),
                    (f"₹ {r['income']:,.0f}", 130, "e", "#2ecc71"),
                    (f"₹ {r['expense']:,.0f}", 130, "e", "#e74c3c"),
                    (f"₹ {abs(net):,.0f} {'▲' if net >= 0 else '▼'}", 120, "e", net_clr),
                ]:
                    ctk.CTkLabel(rw, text=txt, width=w, anchor=anch,
                                 font=ctk.CTkFont(size=11), text_color=clr
                                 ).pack(side="left", padx=8, pady=5)


    def _set_range(self, from_d, to_d):
        self.from_date.delete(0, "end"); self.from_date.insert(0, from_d)
        self.to_date.delete(0, "end");   self.to_date.insert(0, to_d)
        self._generate()

    def _preset_this_month(self):
        t = datetime.now()
        self._set_range(t.replace(day=1).strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d"))

    def _preset_last_month(self):
        t = datetime.now().replace(day=1) - timedelta(days=1)
        self._set_range(t.replace(day=1).strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d"))

    def _preset_this_qtr(self):
        t = datetime.now()
        q = ((t.month - 1) // 3) * 3 + 1
        self._set_range(t.replace(month=q, day=1).strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d"))

    def _preset_this_year(self):
        t = datetime.now()
        self._set_range(t.replace(month=1, day=1).strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d"))

    def _render_pl_chart(self, data):
        """Draw a horizontal bar chart comparing income vs expenses."""
        import tkinter as tk
        total_inc = data["total_income"]
        total_exp = data["total_expenses"]
        if total_inc == 0 and total_exp == 0:
            return
        max_val = max(total_inc, total_exp) or 1
        sec = ctk.CTkFrame(self._report_area, fg_color="#16213e", corner_radius=8)
        sec.pack(fill="x", padx=20, pady=(4, 8))
        ctk.CTkLabel(sec, text="INCOME vs EXPENSES",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#3498db").pack(anchor="w", padx=12, pady=(8, 4))
        canvas_w, bar_h, label_w = 540, 26, 100
        canvas_h = bar_h * 2 + 50
        cv = tk.Canvas(sec, width=canvas_w, height=canvas_h,
                       bg="#16213e", highlightthickness=0)
        cv.pack(padx=12, pady=(0, 10))
        for idx, (label, val, color) in enumerate([
            ("Income",   total_inc, "#2ecc71"),
            ("Expenses", total_exp, "#e74c3c"),
        ]):
            y = 10 + idx * (bar_h + 14)
            bar_max_w = canvas_w - label_w - 110
            bar_fill = int(val / max_val * bar_max_w)
            cv.create_text(label_w - 6, y + bar_h // 2, text=label,
                           fill="#bdc3c7", font=("Helvetica", 9), anchor="e")
            cv.create_rectangle(label_w, y, label_w + bar_max_w, y + bar_h,
                                 fill="#0f1b2d", outline="")
            if bar_fill > 0:
                cv.create_rectangle(label_w, y, label_w + bar_fill, y + bar_h,
                                     fill=color, outline="")
            cv.create_text(label_w + bar_max_w + 8, y + bar_h // 2,
                           text=f"₹ {val:,.0f}",
                           fill=color, font=("Helvetica", 9, "bold"), anchor="w")
        margin = data["net_profit"]
        margin_pct = (margin / total_inc * 100) if total_inc else 0
        m_clr = "#2ecc71" if margin >= 0 else "#e74c3c"
        cv.create_text(canvas_w // 2, canvas_h - 10,
                       text=f"Net {'Profit' if margin >= 0 else 'Loss'}: "
                            f"₹ {abs(margin):,.0f}  ({margin_pct:.1f}%)",
                       fill=m_clr, font=("Helvetica", 9, "bold"), anchor="center")

    def _export_pdf(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("Export", "Generate the report first."); return
        firm = (db.get_firm_settings() or {}).get("firm_name", "")
        _run_export(rex.export_pl_pdf, "PL_Report.pdf",
                    self._last_data, self._last_from, self._last_to, firm)

    def _export_excel(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("Export", "Generate the report first."); return
        firm = (db.get_firm_settings() or {}).get("firm_name", "")
        _run_export(rex.export_pl_excel, "PL_Report.xlsx",
                    self._last_data, self._last_from, self._last_to, firm)

    def _export_csv(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("Export", "Generate the report first."); return
        _run_export(rex.export_pl_csv, "PL_Report.csv",
                    self._last_data, self._last_from, self._last_to)
    def _show_ai_insights(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("AI Insights", "Generate the report first.")
            return
        d = self._last_data
        from_d, to_d = self._last_from, self._last_to
        profit = d["net_profit"]
        margin = (profit / d["total_income"] * 100) if d["total_income"] else 0
        inc = "\n".join(f"  • {n}: ₹{a:,.0f}" for n, a in d["income"] if a)
        exp = "\n".join(f"  • {n}: ₹{a:,.0f}" for n, a in d["expenses"] if a)
        prompt = (
            f"You are a financial advisor for an Indian business.\n\n"
            f"Profit & Loss — Period: {from_d} to {to_d}\n"
            f"Total Income:   ₹{d['total_income']:,.0f}\n"
            f"Total Expenses: ₹{d['total_expenses']:,.0f}\n"
            f"Net {'Profit' if profit >= 0 else 'Loss'}: ₹{abs(profit):,.0f}\n"
            f"Profit Margin:  {margin:.1f}%\n\n"
            f"Income:\n{inc or '  (none)'}\n\nExpenses:\n{exp or '  (none)'}\n\n"
            "Provide 5 specific, actionable insights numbered 1–5. Focus on: financial health, "
            "major expense drivers, revenue opportunities, profitability improvements, and any red flags."
        )
        AIInsightsDialog(self, "Profit & Loss", prompt)



# ── Balance Sheet Page ────────────────────────────────────────────────────────

class BalanceSheetPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._header("Balance Sheet", "Financial Position Statement")

        ctrl = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=10)
        ctrl.pack(fill="x", padx=24, pady=(0, 4))
        inner = ctk.CTkFrame(ctrl, fg_color="transparent")
        inner.pack(padx=16, pady=(12, 4))

        today = datetime.now().strftime("%Y-%m-%d")
        ctk.CTkLabel(inner, text="As of Date:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.as_of = ctk.CTkEntry(inner, width=120)
        self.as_of.insert(0, today)
        self.as_of.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(inner, text="Compare with:", text_color="#555",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.compare_date = ctk.CTkEntry(inner, width=120, placeholder_text="optional")
        self.compare_date.pack(side="left", padx=(0, 12))

        ctk.CTkButton(inner, text="Generate", width=110, height=36,
                      fg_color="#0f3460", hover_color="#1a4a8a",
                      command=self._generate).pack(side="left")
        _export_btns(inner, self._export_pdf, self._export_excel, self._export_csv)
        ctk.CTkFrame(inner, fg_color="#2c3e50", width=1, height=28
                     ).pack(side="left", padx=10, pady=4, fill="y")
        ctk.CTkButton(inner, text="✨ AI Insights", width=112, height=34,
                      fg_color="#6c3483", hover_color="#8e44ad",
                      font=ctk.CTkFont(size=11),
                      command=self._show_ai_insights).pack(side="left", padx=2)

        pr = ctk.CTkFrame(ctrl, fg_color="transparent")
        pr.pack(padx=16, pady=(0, 10), anchor="w")
        ctk.CTkLabel(pr, text="Quick:", text_color="#555",
                     font=ctk.CTkFont(size=10)).pack(side="left", padx=(0, 6))
        for lbl, cmd in [("Today",          self._preset_today),
                         ("End Last Month",  self._preset_end_last_month),
                         ("End Last Qtr",   self._preset_end_last_qtr),
                         ("YoY Compare",    self._preset_yoy)]:
            ctk.CTkButton(pr, text=lbl, width=105, height=22,
                          fg_color="#1e3a5f", hover_color="#2a4a7f",
                          font=ctk.CTkFont(size=10),
                          command=cmd).pack(side="left", padx=(0, 4))

        self._area = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._area.pack(fill="both", expand=True, padx=24, pady=(0, 24))
        ctk.CTkLabel(self._area,
                     text="Enter a date and click 'Generate'",
                     text_color="#555", font=ctk.CTkFont(size=13)).pack(pady=40)

    def _generate(self):
        for w in self._area.winfo_children():
            w.destroy()
        as_of = self.as_of.get().strip()
        if not as_of:
            messagebox.showerror("Error", "Enter a date.")
            return
        cmp = self.compare_date.get().strip() or None

        data = db.get_balance_sheet(as_of)
        cdata = db.get_balance_sheet(cmp) if cmp else None
        self._last_data, self._last_as_of = data, as_of

        # ── KPI summary strip ──────────────────────────────────────────────────
        kpi = ctk.CTkFrame(self._area, fg_color="transparent")
        kpi.pack(fill="x", pady=(4, 8))
        kpi_items = [
            ("Total Assets",      data["total_assets"], cdata["total_assets"] if cdata else None, "#3498db"),
            ("Total Liabilities", data["total_liab"],   cdata["total_liab"]   if cdata else None, "#e74c3c"),
            ("Total Equity",      data["total_equity"], cdata["total_equity"] if cdata else None, "#2ecc71"),
            ("Net Income",        data["net_income"],   cdata["net_income"]   if cdata else None,
             "#2ecc71" if data["net_income"] >= 0 else "#e74c3c"),
        ]
        for title, val, prev, col in kpi_items:
            tile = ctk.CTkFrame(kpi, fg_color="#16213e", corner_radius=8)
            tile.pack(side="left", padx=(0, 8), fill="x", expand=True, ipady=4, ipadx=6)
            ctk.CTkLabel(tile, text=title, font=ctk.CTkFont(size=10),
                         text_color="#95a5a6").pack(pady=(6, 0))
            ctk.CTkLabel(tile, text=f"₹ {val:,.0f}",
                         font=ctk.CTkFont(size=14, weight="bold"),
                         text_color=col).pack()
            if prev is not None:
                chg = val - prev
                pct = (chg / abs(prev) * 100) if prev else 0
                chg_col = "#2ecc71" if chg >= 0 else "#e74c3c"
                sign = "▲" if chg >= 0 else "▼"
                ctk.CTkLabel(tile,
                             text=f"{sign} ₹{abs(chg):,.0f}  ({pct:+.1f}%)",
                             font=ctk.CTkFont(size=9), text_color=chg_col).pack(pady=(0, 4))
            else:
                ctk.CTkLabel(tile, text=" ", font=ctk.CTkFont(size=9)).pack(pady=(0, 4))

        # ── Title ──────────────────────────────────────────────────────────────
        firm = db.get_firm_settings()
        if firm and firm["firm_name"]:
            ctk.CTkLabel(self._area, text=firm["firm_name"],
                         text_color="#3498db",
                         font=ctk.CTkFont(size=13)).pack(pady=(10, 0))
        ctk.CTkLabel(self._area, text="BALANCE SHEET",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#ecf0f1").pack(pady=(2, 0))
        date_line = f"As at  {as_of}"
        if cmp:
            date_line += f"  vs  {cmp}"
        ctk.CTkLabel(self._area, text=date_line,
                     text_color="#95a5a6", font=ctk.CTkFont(size=11)).pack(pady=(0, 10))

        # ── Column header (comparative) ───────────────────────────────────────
        if cmp:
            col_hdr = ctk.CTkFrame(self._area, fg_color="transparent")
            col_hdr.pack(fill="x", padx=20, pady=(0, 2))
            ctk.CTkLabel(col_hdr, text="", width=240).pack(side="left")
            ctk.CTkLabel(col_hdr, text=as_of, width=140, anchor="e",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#ecf0f1").pack(side="left")
            ctk.CTkLabel(col_hdr, text=cmp, width=140, anchor="e",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#95a5a6").pack(side="left")
            ctk.CTkLabel(col_hdr, text="Change", width=120, anchor="e",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#f39c12").pack(side="left")

        def divider():
            ctk.CTkFrame(self._area, fg_color="#0f3460", height=1).pack(fill="x", padx=20, pady=3)

        def sec_hdr(text, color):
            f = ctk.CTkFrame(self._area, fg_color="#0f3460", corner_radius=4)
            f.pack(fill="x", padx=20, pady=(10, 2))
            ctk.CTkLabel(f, text=text,
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=color).pack(padx=14, pady=6, anchor="w")

        def line_row(name, amount, compare_amt=None, color="#ecf0f1", bold=False, indent=True):
            row = ctk.CTkFrame(self._area, fg_color="transparent")
            row.pack(fill="x", padx=(40 if indent else 20), pady=1)
            w = "bold" if bold else "normal"
            ctk.CTkLabel(row, text=name, width=240, anchor="w",
                         font=ctk.CTkFont(size=11, weight=w),
                         text_color=color).pack(side="left")
            ctk.CTkLabel(row, text=f"₹ {amount:,.2f}", width=140, anchor="e",
                         font=ctk.CTkFont(size=11, weight=w),
                         text_color=color).pack(side="left")
            if cmp:
                if compare_amt is not None:
                    ctk.CTkLabel(row, text=f"₹ {compare_amt:,.2f}", width=140, anchor="e",
                                 font=ctk.CTkFont(size=11, weight=w),
                                 text_color="#95a5a6").pack(side="left")
                    chg = amount - compare_amt
                    chg_col = "#2ecc71" if chg >= 0 else "#e74c3c"
                    sign = "▲" if chg > 0 else ("▼" if chg < 0 else "")
                    ctk.CTkLabel(row, text=f"{sign} ₹ {abs(chg):,.2f}", width=120, anchor="e",
                                 font=ctk.CTkFont(size=11, weight=w),
                                 text_color=chg_col).pack(side="left")
                else:
                    ctk.CTkLabel(row, text="—", width=140, anchor="e",
                                 text_color="#555").pack(side="left")
                    ctk.CTkLabel(row, text="—", width=120, anchor="e",
                                 text_color="#555").pack(side="left")

        def find_cmp(cmp_list, name):
            if not cmp_list:
                return None
            for x in cmp_list:
                if x["name"] == name:
                    return x["balance"]
            return None

        # ── ASSETS ────────────────────────────────────────────────────────────
        sec_hdr("ASSETS", "#3498db")
        for a in data["assets"]:
            line_row(a["name"], a["balance"],
                     find_cmp(cdata["assets"] if cdata else None, a["name"]))
        divider()
        line_row("Total Assets", data["total_assets"],
                 cdata["total_assets"] if cdata else None,
                 "#3498db", bold=True, indent=False)

        # ── LIABILITIES ───────────────────────────────────────────────────────
        sec_hdr("LIABILITIES", "#e74c3c")
        for a in data["liabilities"]:
            line_row(a["name"], a["balance"],
                     find_cmp(cdata["liabilities"] if cdata else None, a["name"]))
        divider()
        line_row("Total Liabilities", data["total_liab"],
                 cdata["total_liab"] if cdata else None,
                 "#e74c3c", bold=True, indent=False)

        # ── EQUITY ────────────────────────────────────────────────────────────
        sec_hdr("EQUITY", "#2ecc71")
        for a in data["equity"]:
            line_row(a["name"], a["balance"],
                     find_cmp(cdata["equity"] if cdata else None, a["name"]))
        ni = data["net_income"]
        ni_cmp = cdata["net_income"] if cdata else None
        ni_color = "#2ecc71" if ni >= 0 else "#e74c3c"
        line_row("Net Profit / (Loss)", ni, ni_cmp, ni_color)
        divider()
        line_row("Total Equity", data["total_equity"],
                 cdata["total_equity"] if cdata else None,
                 "#2ecc71", bold=True, indent=False)

        # ── Balance check ─────────────────────────────────────────────────────
        balanced = abs(data["total_assets"] - (data["total_liab"] + data["total_equity"])) < 0.01
        chk_color = "#2ecc71" if balanced else "#e74c3c"
        chk_text  = "✓  Balance Sheet is in agreement" if balanced else "✗  Out of balance!"
        banner = ctk.CTkFrame(self._area, fg_color="#0f3460", corner_radius=8)
        banner.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(banner, text=chk_text,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=chk_color).pack(side="left", padx=16, pady=10)
        ctk.CTkLabel(banner,
                     text=f"Assets  ₹{data['total_assets']:,.2f}  =  "
                          f"Liabilities ₹{data['total_liab']:,.2f}  +  Equity ₹{data['total_equity']:,.2f}",
                     font=ctk.CTkFont(size=11), text_color="#95a5a6",
                     ).pack(side="right", padx=16)

        # ── Financial Ratios ──────────────────────────────────────────────────
        self._render_ratios(data, cdata)


    def _set_as_of(self, d):
        self.as_of.delete(0, "end"); self.as_of.insert(0, d)
        self._generate()

    def _preset_today(self):
        self._set_as_of(datetime.now().strftime("%Y-%m-%d"))

    def _preset_end_last_month(self):
        d = datetime.now().replace(day=1) - timedelta(days=1)
        self._set_as_of(d.strftime("%Y-%m-%d"))

    def _preset_end_last_qtr(self):
        t = datetime.now()
        q = ((t.month - 1) // 3) * 3 + 1
        d = t.replace(month=q, day=1) - timedelta(days=1)
        self._set_as_of(d.strftime("%Y-%m-%d"))

    def _preset_yoy(self):
        today = datetime.now().strftime("%Y-%m-%d")
        last_yr = datetime.now().replace(year=datetime.now().year - 1).strftime("%Y-%m-%d")
        self.as_of.delete(0, "end"); self.as_of.insert(0, today)
        self.compare_date.delete(0, "end"); self.compare_date.insert(0, last_yr)
        self._generate()

    def _render_ratios(self, data, cdata=None):
        ta   = data["total_assets"]  or 1
        tl   = data["total_liab"]
        te   = data["total_equity"] or 1
        ni   = data["net_income"]

        current_assets = sum(a["balance"] for a in data["assets"]
                             if any(k in a["name"].lower()
                                    for k in ("cash", "bank", "receivable", "stock", "inventory", "current")))
        current_liab   = sum(a["balance"] for a in data["liabilities"]
                             if any(k in a["name"].lower()
                                    for k in ("payable", "current", "short", "overdraft")))

        de_ratio  = tl / te if te != 0 else float("inf")
        eq_ratio  = te / ta
        debt_ratio = tl / ta
        roa       = ni / ta
        wc        = current_assets - current_liab

        ctk.CTkLabel(self._area, text="FINANCIAL RATIOS",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#f39c12").pack(pady=(18, 4))
        ctk.CTkFrame(self._area, fg_color="#f39c12", height=1).pack(fill="x", padx=20, pady=(0, 8))

        ratios_frame = ctk.CTkFrame(self._area, fg_color="transparent")
        ratios_frame.pack(fill="x", padx=20, pady=(0, 10))

        ratio_items = [
            ("Debt-to-Equity",  f"{de_ratio:.2f}x",  "< 2.0 is healthy",  "#e74c3c" if de_ratio > 2 else "#2ecc71"),
            ("Equity Ratio",    f"{eq_ratio:.1%}",    "> 50% is strong",   "#2ecc71" if eq_ratio > 0.5 else "#e67e22"),
            ("Debt Ratio",      f"{debt_ratio:.1%}",  "< 50% preferred",   "#2ecc71" if debt_ratio < 0.5 else "#e74c3c"),
            ("Return on Assets",f"{roa:.1%}",         "> 5% is good",      "#2ecc71" if roa > 0.05 else "#e67e22"),
            ("Working Capital",
             f"₹ {wc:,.0f}",
             "Positive = liquid",
             "#2ecc71" if wc >= 0 else "#e74c3c"),
        ]

        for i, (label, value, hint, col) in enumerate(ratio_items):
            tile = ctk.CTkFrame(ratios_frame, fg_color="#16213e", corner_radius=8)
            tile.grid(row=i // 3, column=i % 3, padx=6, pady=6, sticky="ew")
            ratios_frame.columnconfigure(i % 3, weight=1)
            ctk.CTkLabel(tile, text=label, font=ctk.CTkFont(size=10),
                         text_color="#95a5a6").pack(pady=(8, 0))
            ctk.CTkLabel(tile, text=value,
                         font=ctk.CTkFont(size=15, weight="bold"),
                         text_color=col).pack()
            ctk.CTkLabel(tile, text=hint, font=ctk.CTkFont(size=9),
                         text_color="#555").pack(pady=(0, 8))

        if cdata:
            cta  = cdata["total_assets"] or 1
            ctl  = cdata["total_liab"]
            cte  = cdata["total_equity"] or 1
            cde  = ctl / cte if cte != 0 else float("inf")
            ceq  = cte / cta
            cdbt = ctl / cta
            croa = cdata["net_income"] / cta

            cmp_items = [
                ("Debt-to-Equity",  de_ratio,   cde,  "x"),
                ("Equity Ratio",    eq_ratio,   ceq,  "%"),
                ("Debt Ratio",      debt_ratio, cdbt, "%"),
                ("Return on Assets",roa,        croa, "%"),
            ]
            ctk.CTkLabel(self._area, text="Year-over-Year Ratio Comparison",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#95a5a6").pack(pady=(6, 4))
            for label, cur, prev, fmt in cmp_items:
                row = ctk.CTkFrame(self._area, fg_color="transparent")
                row.pack(fill="x", padx=40, pady=1)
                chg = cur - prev
                chg_col = "#2ecc71" if chg >= 0 else "#e74c3c"
                sign = "▲" if chg > 0 else ("▼" if chg < 0 else "")
                cur_txt  = f"{cur:.2f}x"  if fmt == "x" else f"{cur:.1%}"
                prev_txt = f"{prev:.2f}x" if fmt == "x" else f"{prev:.1%}"
                chg_txt  = f"{sign} {abs(chg):.2f}x" if fmt == "x" else f"{sign} {abs(chg):.1%}"
                ctk.CTkLabel(row, text=label, width=180, anchor="w",
                             font=ctk.CTkFont(size=11), text_color="#ecf0f1").pack(side="left")
                ctk.CTkLabel(row, text=cur_txt, width=100, anchor="e",
                             font=ctk.CTkFont(size=11, weight="bold"),
                             text_color="#ecf0f1").pack(side="left")
                ctk.CTkLabel(row, text=prev_txt, width=100, anchor="e",
                             font=ctk.CTkFont(size=11), text_color="#95a5a6").pack(side="left")
                ctk.CTkLabel(row, text=chg_txt, width=100, anchor="e",
                             font=ctk.CTkFont(size=11), text_color=chg_col).pack(side="left")

    def _export_pdf(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("Export", "Generate the report first."); return
        firm = (db.get_firm_settings() or {}).get("firm_name", "")
        _run_export(rex.export_bs_pdf, "Balance_Sheet.pdf",
                    self._last_data, self._last_as_of, firm)

    def _export_excel(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("Export", "Generate the report first."); return
        firm = (db.get_firm_settings() or {}).get("firm_name", "")
        _run_export(rex.export_bs_excel, "Balance_Sheet.xlsx",
                    self._last_data, self._last_as_of, firm)

    def _export_csv(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("Export", "Generate the report first."); return
        _run_export(rex.export_bs_csv, "Balance_Sheet.csv",
                    self._last_data, self._last_as_of)
    def _show_ai_insights(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("AI Insights", "Generate the report first.")
            return
        d = self._last_data
        assets = "\n".join(f"  • {x['name']}: ₹{x['balance']:,.0f}" for x in d["assets"] if x["balance"])
        liabs  = "\n".join(f"  • {x['name']}: ₹{x['balance']:,.0f}" for x in d["liabilities"] if x["balance"])
        eq     = "\n".join(f"  • {x['name']}: ₹{x['balance']:,.0f}" for x in d["equity"] if x["balance"])
        prompt = (
            f"You are a financial advisor for an Indian business.\n\n"
            f"Balance Sheet — As at: {self._last_as_of}\n"
            f"Total Assets:      ₹{d['total_assets']:,.0f}\n"
            f"Total Liabilities: ₹{d['total_liab']:,.0f}\n"
            f"Total Equity:      ₹{d['total_equity']:,.0f}\n"
            f"Net Income (YTD):  ₹{d['net_income']:,.0f}\n\n"
            f"Assets:\n{assets or '  (none)'}\n\nLiabilities:\n{liabs or '  (none)'}\n\n"
            f"Equity:\n{eq or '  (none)'}\n\n"
            "Provide 5 specific insights numbered 1–5 on: financial position, leverage, "
            "liquidity, working capital, and recommendations."
        )
        AIInsightsDialog(self, "Balance Sheet", prompt)



# ── Trial Balance Page ────────────────────────────────────────────────────────

ACCT_TYPE_COLORS = {
    "Asset":     "#3498db",
    "Liability": "#e74c3c",
    "Equity":    "#2ecc71",
    "Income":    "#27ae60",
    "Expense":   "#e67e22",
}

class TrialBalancePage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._tb_filter = "All"

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._header("Trial Balance", "All Accounts – Debit / Credit Summary")

        ctrl = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=10)
        ctrl.pack(fill="x", padx=24, pady=(0, 4))
        inner = ctk.CTkFrame(ctrl, fg_color="transparent")
        inner.pack(padx=16, pady=(12, 4))

        today = datetime.now().strftime("%Y-%m-%d")
        ctk.CTkLabel(inner, text="As of Date:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.as_of = ctk.CTkEntry(inner, width=130)
        self.as_of.insert(0, today)
        self.as_of.pack(side="left", padx=(0, 16))
        ctk.CTkButton(inner, text="Generate", width=130, height=36,
                      fg_color="#0f3460", hover_color="#1a4a8a",
                      command=self._generate).pack(side="left")
        _export_btns(inner, self._export_pdf, self._export_excel, self._export_csv)
        ctk.CTkFrame(inner, fg_color="#2c3e50", width=1, height=28
                     ).pack(side="left", padx=10, pady=4, fill="y")
        ctk.CTkButton(inner, text="✨ AI Insights", width=112, height=34,
                      fg_color="#6c3483", hover_color="#8e44ad",
                      font=ctk.CTkFont(size=11),
                      command=self._show_ai_insights).pack(side="left", padx=2)

        # Date presets + account type filters
        bot = ctk.CTkFrame(ctrl, fg_color="transparent")
        bot.pack(padx=16, pady=(0, 10), anchor="w")
        ctk.CTkLabel(bot, text="Quick:", text_color="#555",
                     font=ctk.CTkFont(size=10)).pack(side="left", padx=(0, 6))
        for lbl, cmd in [("Today",         self._preset_today),
                         ("End Last Month", self._preset_end_last_month),
                         ("End Last Qtr",  self._preset_end_last_qtr)]:
            ctk.CTkButton(bot, text=lbl, width=100, height=22,
                          fg_color="#1e3a5f", hover_color="#2a4a7f",
                          font=ctk.CTkFont(size=10),
                          command=cmd).pack(side="left", padx=(0, 4))
        ctk.CTkFrame(bot, fg_color="#2c3e50", width=1, height=20).pack(
            side="left", padx=10, pady=2, fill="y")
        ctk.CTkLabel(bot, text="Filter:", text_color="#555",
                     font=ctk.CTkFont(size=10)).pack(side="left", padx=(0, 6))
        for atype in ["All", "Asset", "Liability", "Equity", "Income", "Expense"]:
            col = ACCT_TYPE_COLORS.get(atype, "#ecf0f1")
            is_active = self._tb_filter == atype
            ctk.CTkButton(bot, text=atype, width=68, height=22,
                          fg_color=col if is_active else "#1e3a5f",
                          hover_color=col,
                          font=ctk.CTkFont(size=10),
                          command=lambda a=atype: self._set_filter(a)
                          ).pack(side="left", padx=(0, 3))

        self._area = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._area.pack(fill="both", expand=True, padx=24, pady=(0, 24))
        ctk.CTkLabel(self._area,
                     text="Enter a date and click 'Generate'",
                     text_color="#555", font=ctk.CTkFont(size=13)).pack(pady=40)

    def _generate(self):
        for w in self._area.winfo_children():
            w.destroy()
        as_of = self.as_of.get().strip()
        if not as_of:
            messagebox.showerror("Error", "Enter a date.")
            return
        data = db.get_trial_balance(as_of)
        self._last_data, self._last_as_of = data, as_of

        # Apply account type filter
        rows = data["rows"]
        if self._tb_filter != "All":
            rows = [r for r in rows if r["account_type"] == self._tb_filter]

        # KPI summary strip
        total_dr = sum(r["debit"]  or 0 for r in rows)
        total_cr = sum(r["credit"] or 0 for r in rows)
        kpi = ctk.CTkFrame(self._area, fg_color="transparent")
        kpi.pack(fill="x", pady=(4, 8))
        for title, val, col in [
            ("Accounts Shown", str(len(rows)),           "#3498db"),
            ("Total Debit",    f"₹ {total_dr:,.0f}",    "#3498db"),
            ("Total Credit",   f"₹ {total_cr:,.0f}",    "#e74c3c"),
        ]:
            c = self._card(kpi, title, val, col, "")
            c.pack(side="left", padx=(0, 8), fill="x", expand=True)

        # ── Title
        ctk.CTkLabel(self._area, text="TRIAL BALANCE",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#ecf0f1").pack(pady=(12, 2))
        ctk.CTkLabel(self._area, text=f"As at  {as_of}",
                     text_color="#95a5a6", font=ctk.CTkFont(size=11)).pack()
        firm = db.get_firm_settings()
        if firm and firm["firm_name"]:
            ctk.CTkLabel(self._area, text=firm["firm_name"],
                         text_color="#3498db",
                         font=ctk.CTkFont(size=13)).pack(pady=(2, 10))

        # ── Table header
        hdr = ctk.CTkFrame(self._area, fg_color="#0f3460", corner_radius=6)
        hdr.pack(fill="x", padx=20, pady=(4, 0))
        for col, w, anchor in [("Code", 60, "w"), ("Account Name", 0, "w"),
                                ("Type", 90, "w"), ("Debit (₹)", 110, "e"),
                                ("Credit (₹)", 110, "e")]:
            ctk.CTkLabel(hdr, text=col,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#ecf0f1",
                         width=w, anchor=anchor
                         ).pack(side="left", padx=(10 if anchor == "w" else 4), pady=8)

        # ── Rows
        for i, row in enumerate(rows):
            bg = "#1a1a2e" if i % 2 == 0 else "#16213e"
            r = ctk.CTkFrame(self._area, fg_color=bg, corner_radius=0)
            r.pack(fill="x", padx=20)
            acolor = ACCT_TYPE_COLORS.get(row["account_type"], "#ecf0f1")

            ctk.CTkLabel(r, text=row["code"],
                         font=ctk.CTkFont(size=11), text_color="#95a5a6",
                         width=60, anchor="w").pack(side="left", padx=(10, 4), pady=5)
            ctk.CTkLabel(r, text=row["name"],
                         font=ctk.CTkFont(size=11), text_color="#ecf0f1",
                         anchor="w").pack(side="left", padx=4, fill="x", expand=True)
            ctk.CTkLabel(r, text=row["account_type"],
                         font=ctk.CTkFont(size=10), text_color=acolor,
                         width=90, anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(r, text=f"{row['debit']:,.2f}" if row["debit"] else "—",
                         font=ctk.CTkFont(size=11),
                         text_color="#ecf0f1" if row["debit"] else "#555",
                         width=110, anchor="e").pack(side="left", padx=4)
            ctk.CTkLabel(r, text=f"{row['credit']:,.2f}" if row["credit"] else "—",
                         font=ctk.CTkFont(size=11),
                         text_color="#ecf0f1" if row["credit"] else "#555",
                         width=110, anchor="e").pack(side="left", padx=(4, 10))

        # ── Totals row
        ctk.CTkFrame(self._area, fg_color="#0f3460", height=1).pack(fill="x", padx=20, pady=2)
        tot = ctk.CTkFrame(self._area, fg_color="#0f3460", corner_radius=6)
        tot.pack(fill="x", padx=20, pady=(0, 4))
        ctk.CTkLabel(tot, text="TOTALS",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#ecf0f1").pack(side="left", padx=14, pady=8, fill="x", expand=True)
        ctk.CTkLabel(tot, text=f"₹ {total_dr:,.2f}",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#3498db",
                     width=110, anchor="e").pack(side="left", padx=4)
        ctk.CTkLabel(tot, text=f"₹ {total_cr:,.2f}",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#e74c3c",
                     width=110, anchor="e").pack(side="left", padx=(4, 14))

        # ── Balance check (uses full dataset totals for correctness)
        balanced = abs(data["total_dr"] - data["total_cr"]) < 0.01
        chk_color = "#2ecc71" if balanced else "#e74c3c"
        chk_text  = "✓  Trial Balance is in agreement" if balanced else "✗  Totals do not agree!"
        if self._tb_filter != "All":
            chk_text = f"Showing {self._tb_filter} accounts  |  Full TB: {chk_text}"
        banner = ctk.CTkFrame(self._area, fg_color="#16213e", corner_radius=8)
        banner.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(banner, text=chk_text,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=chk_color).pack(padx=16, pady=10)

    def _set_as_of(self, d):
        self.as_of.delete(0, "end"); self.as_of.insert(0, d)
        self._generate()

    def _preset_today(self):
        self._set_as_of(datetime.now().strftime("%Y-%m-%d"))

    def _preset_end_last_month(self):
        d = datetime.now().replace(day=1) - timedelta(days=1)
        self._set_as_of(d.strftime("%Y-%m-%d"))

    def _preset_end_last_qtr(self):
        t = datetime.now()
        q = ((t.month - 1) // 3) * 3 + 1
        d = t.replace(month=q, day=1) - timedelta(days=1)
        self._set_as_of(d.strftime("%Y-%m-%d"))

    def _set_filter(self, atype):
        self._tb_filter = atype
        self.refresh()
        if getattr(self, "_last_as_of", None):
            self.as_of.delete(0, "end")
            self.as_of.insert(0, self._last_as_of)
            self._generate()

    def _export_pdf(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("Export", "Generate the report first."); return
        firm = (db.get_firm_settings() or {}).get("firm_name", "")
        _run_export(rex.export_tb_pdf, "Trial_Balance.pdf",
                    self._last_data, self._last_as_of, firm)

    def _export_excel(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("Export", "Generate the report first."); return
        firm = (db.get_firm_settings() or {}).get("firm_name", "")
        _run_export(rex.export_tb_excel, "Trial_Balance.xlsx",
                    self._last_data, self._last_as_of, firm)

    def _export_csv(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("Export", "Generate the report first."); return
        _run_export(rex.export_tb_csv, "Trial_Balance.csv",
                    self._last_data, self._last_as_of)
    def _show_ai_insights(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("AI Insights", "Generate the report first.")
            return
        d = self._last_data
        top = sorted(d["rows"], key=lambda r: max(r["debit"], r["credit"]), reverse=True)[:10]
        rows_txt = "\n".join(
            f"  • [{r['account_type']}] {r['name']}: Dr ₹{r['debit']:,.0f} / Cr ₹{r['credit']:,.0f}"
            for r in top
        )
        balanced = abs(d["total_dr"] - d["total_cr"]) < 0.01
        prompt = (
            f"You are a financial advisor for an Indian business.\n\n"
            f"Trial Balance — As at: {self._last_as_of}\n"
            f"Total Debits:  ₹{d['total_dr']:,.0f}\n"
            f"Total Credits: ₹{d['total_cr']:,.0f}\n"
            f"Balanced: {'✓ Yes' if balanced else '⚠ NO — DISCREPANCY DETECTED'}\n\n"
            f"Top accounts by balance:\n{rows_txt or '  (none)'}\n\n"
            "Provide 5 insights numbered 1–5 on: accounting health, high-balance accounts, "
            "balance status, and recommendations."
        )
        AIInsightsDialog(self, "Trial Balance", prompt)



# ── Cash Flow Page ────────────────────────────────────────────────────────────

class CashFlowPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._header("Cash Flow Statement", "Direct Method – Cash & Bank Movements")

        ctrl = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=10)
        ctrl.pack(fill="x", padx=24, pady=(0, 4))
        inner = ctk.CTkFrame(ctrl, fg_color="transparent")
        inner.pack(padx=16, pady=(12, 4))

        today = datetime.now()
        from_def = today.replace(day=1).strftime("%Y-%m-%d")
        to_def   = today.strftime("%Y-%m-%d")

        ctk.CTkLabel(inner, text="From:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.from_date = ctk.CTkEntry(inner, width=120)
        self.from_date.insert(0, from_def)
        self.from_date.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(inner, text="To:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.to_date = ctk.CTkEntry(inner, width=120)
        self.to_date.insert(0, to_def)
        self.to_date.pack(side="left", padx=(0, 16))

        ctk.CTkButton(inner, text="Generate Report", width=150, height=36,
                      fg_color="#0f3460", hover_color="#1a4a8a",
                      command=self._generate).pack(side="left")
        _export_btns(inner, self._export_pdf, self._export_excel, self._export_csv)
        ctk.CTkFrame(inner, fg_color="#2c3e50", width=1, height=28
                     ).pack(side="left", padx=10, pady=4, fill="y")
        ctk.CTkButton(inner, text="✨ AI Insights", width=112, height=34,
                      fg_color="#6c3483", hover_color="#8e44ad",
                      font=ctk.CTkFont(size=11),
                      command=self._show_ai_insights).pack(side="left", padx=2)

        pr = ctk.CTkFrame(ctrl, fg_color="transparent")
        pr.pack(padx=16, pady=(0, 10), anchor="w")
        ctk.CTkLabel(pr, text="Quick:", text_color="#555",
                     font=ctk.CTkFont(size=10)).pack(side="left", padx=(0, 6))
        for lbl, cmd in [("This Month",   self._preset_this_month),
                         ("Last Month",   self._preset_last_month),
                         ("This Quarter", self._preset_this_qtr),
                         ("This Year",    self._preset_this_year)]:
            ctk.CTkButton(pr, text=lbl, width=88, height=22,
                          fg_color="#1e3a5f", hover_color="#2a4a7f",
                          font=ctk.CTkFont(size=10),
                          command=cmd).pack(side="left", padx=(0, 4))

        self._area = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._area.pack(fill="both", expand=True, padx=24, pady=(0, 24))
        ctk.CTkLabel(self._area,
                     text="Select a date range and click 'Generate Report'",
                     text_color="#555", font=ctk.CTkFont(size=13)).pack(pady=40)

    def _generate(self):
        for w in self._area.winfo_children():
            w.destroy()
        from_d = self.from_date.get().strip()
        to_d   = self.to_date.get().strip()
        if not from_d or not to_d:
            messagebox.showerror("Error", "Enter both From and To dates.")
            return
        data = db.get_cash_flow(from_d, to_d)
        self._last_data, self._last_from, self._last_to = data, from_d, to_d

        # KPI section summary
        kpi = ctk.CTkFrame(self._area, fg_color="transparent")
        kpi.pack(fill="x", pady=(4, 8))
        net = data["net"]
        net_col = "#2ecc71" if net >= 0 else "#e74c3c"
        for title, val, col in [
            ("Operating",  f"₹ {data['op_total']:,.0f}",  "#3498db"),
            ("Investing",  f"₹ {data['inv_total']:,.0f}", "#9b59b6"),
            ("Financing",  f"₹ {data['fin_total']:,.0f}", "#e67e22"),
            ("Net Change", f"₹ {net:,.0f}",               net_col),
        ]:
            c = self._card(kpi, title, val, col, "")
            c.pack(side="left", padx=(0, 8), fill="x", expand=True)

        # ── Title
        ctk.CTkLabel(self._area, text="CASH FLOW STATEMENT",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#ecf0f1").pack(pady=(12, 2))
        ctk.CTkLabel(self._area, text=f"Period: {from_d}  to  {to_d}",
                     text_color="#95a5a6", font=ctk.CTkFont(size=11)).pack()
        firm = db.get_firm_settings()
        if firm and firm["firm_name"]:
            ctk.CTkLabel(self._area, text=firm["firm_name"],
                         text_color="#3498db",
                         font=ctk.CTkFont(size=13)).pack(pady=(2, 10))

        def divider():
            ctk.CTkFrame(self._area, fg_color="#0f3460", height=1).pack(fill="x", padx=20, pady=3)

        def sec_hdr(letter, title, color):
            f = ctk.CTkFrame(self._area, fg_color="#0f3460", corner_radius=4)
            f.pack(fill="x", padx=20, pady=(12, 2))
            ctk.CTkLabel(f, text=f"{letter}.  {title}",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=color).pack(padx=14, pady=7, anchor="w")

        def tx_row(narration, amount):
            color = "#2ecc71" if amount >= 0 else "#e74c3c"
            amt_str = f"₹ {amount:,.2f}" if amount >= 0 else f"(₹ {abs(amount):,.2f})"
            row = ctk.CTkFrame(self._area, fg_color="transparent")
            row.pack(fill="x", padx=40, pady=1)
            ctk.CTkLabel(row, text=narration,
                         font=ctk.CTkFont(size=11), text_color="#ecf0f1",
                         anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(row, text=amt_str,
                         font=ctk.CTkFont(size=11), text_color=color,
                         width=130, anchor="e").pack(side="right")

        def subtotal_row(label, amount):
            color = "#2ecc71" if amount >= 0 else "#e74c3c"
            amt_str = f"₹ {amount:,.2f}" if amount >= 0 else f"(₹ {abs(amount):,.2f})"
            row = ctk.CTkFrame(self._area, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=2)
            ctk.CTkLabel(row, text=label,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=color).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=amt_str,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=color, width=130, anchor="e").pack(side="right")

        def balance_banner(label, amount):
            color = "#2ecc71" if amount >= 0 else "#e74c3c"
            amt_str = f"₹ {amount:,.2f}" if amount >= 0 else f"(₹ {abs(amount):,.2f})"
            f = ctk.CTkFrame(self._area, fg_color="#0f3460", corner_radius=8)
            f.pack(fill="x", padx=20, pady=5)
            ctk.CTkLabel(f, text=label,
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color="#ecf0f1").pack(side="left", padx=16, pady=10)
            ctk.CTkLabel(f, text=amt_str,
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=color).pack(side="right", padx=16)

        # ── Opening balance
        balance_banner("Opening Cash & Bank Balance", data["opening"])

        # ── A. Operating
        sec_hdr("A", "OPERATING ACTIVITIES", "#3498db")
        if data["operating"]:
            for item in data["operating"]:
                tx_row(item["narration"], item["amount"])
        else:
            ctk.CTkLabel(self._area, text="  No operating cash transactions",
                         text_color="#555", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=40)
        divider()
        subtotal_row("Net Cash from Operating Activities", data["op_total"])

        # ── B. Investing
        sec_hdr("B", "INVESTING ACTIVITIES", "#9b59b6")
        if data["investing"]:
            for item in data["investing"]:
                tx_row(item["narration"], item["amount"])
        else:
            ctk.CTkLabel(self._area, text="  No investing cash transactions",
                         text_color="#555", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=40)
        divider()
        subtotal_row("Net Cash from Investing Activities", data["inv_total"])

        # ── C. Financing
        sec_hdr("C", "FINANCING ACTIVITIES", "#e67e22")
        if data["financing"]:
            for item in data["financing"]:
                tx_row(item["narration"], item["amount"])
        else:
            ctk.CTkLabel(self._area, text="  No financing cash transactions",
                         text_color="#555", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=40)
        divider()
        subtotal_row("Net Cash from Financing Activities", data["fin_total"])

        # ── Net change + closing
        net = data["net"]
        net_label = "NET INCREASE IN CASH" if net >= 0 else "NET DECREASE IN CASH"
        balance_banner(net_label, net)
        balance_banner("Closing Cash & Bank Balance", data["closing"])


    def _set_range(self, from_d, to_d):
        self.from_date.delete(0, "end"); self.from_date.insert(0, from_d)
        self.to_date.delete(0, "end");   self.to_date.insert(0, to_d)
        self._generate()

    def _preset_this_month(self):
        t = datetime.now()
        self._set_range(t.replace(day=1).strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d"))

    def _preset_last_month(self):
        t = datetime.now().replace(day=1) - timedelta(days=1)
        self._set_range(t.replace(day=1).strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d"))

    def _preset_this_qtr(self):
        t = datetime.now()
        q = ((t.month - 1) // 3) * 3 + 1
        self._set_range(t.replace(month=q, day=1).strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d"))

    def _preset_this_year(self):
        t = datetime.now()
        self._set_range(t.replace(month=1, day=1).strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d"))

    def _export_pdf(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("Export", "Generate the report first."); return
        firm = (db.get_firm_settings() or {}).get("firm_name", "")
        _run_export(rex.export_cf_pdf, "Cash_Flow.pdf",
                    self._last_data, self._last_from, self._last_to, firm)

    def _export_excel(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("Export", "Generate the report first."); return
        firm = (db.get_firm_settings() or {}).get("firm_name", "")
        _run_export(rex.export_cf_excel, "Cash_Flow.xlsx",
                    self._last_data, self._last_from, self._last_to, firm)

    def _export_csv(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("Export", "Generate the report first."); return
        _run_export(rex.export_cf_csv, "Cash_Flow.csv",
                    self._last_data, self._last_from, self._last_to)
    def _show_ai_insights(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("AI Insights", "Generate the report first.")
            return
        d = self._last_data
        from_d, to_d = self._last_from, self._last_to
        op  = "\n".join(f"  • {i['date']} {i['narration']}: ₹{i['amount']:,.0f}" for i in d["operating"][:8])
        fin = "\n".join(f"  • {i['date']} {i['narration']}: ₹{i['amount']:,.0f}" for i in d["financing"][:5])
        prompt = (
            f"You are a financial advisor for an Indian business.\n\n"
            f"Cash Flow Statement — Period: {from_d} to {to_d}\n"
            f"Opening Cash:         ₹{d['opening']:,.0f}\n"
            f"Operating Activities: ₹{d['op_total']:,.0f}\n"
            f"Investing Activities: ₹{d['inv_total']:,.0f}\n"
            f"Financing Activities: ₹{d['fin_total']:,.0f}\n"
            f"Net Cash Change:      ₹{d['net']:,.0f}\n"
            f"Closing Cash:         ₹{d['closing']:,.0f}\n\n"
            f"Key operating items:\n{op or '  (none)'}\n\n"
            f"Financing items:\n{fin or '  (none)'}\n\n"
            "Provide 5 insights numbered 1–5 on: cash generation, liquidity, burn rate, "
            "and cash management recommendations."
        )
        AIInsightsDialog(self, "Cash Flow", prompt)



# ── Stock Valuation Page ─────────────────────────────────────────────────────

class StockValuationPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._show_zero = False

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._header("Stock Valuation", "Inventory Value at Cost & Sale Price")

        ctrl = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=10)
        ctrl.pack(fill="x", padx=24, pady=(0, 4))
        inner = ctk.CTkFrame(ctrl, fg_color="transparent")
        inner.pack(padx=16, pady=10, anchor="w")

        self._zero_var = ctk.BooleanVar(value=self._show_zero)
        ctk.CTkCheckBox(inner, text="Show zero-stock items", variable=self._zero_var,
                        font=ctk.CTkFont(size=11),
                        command=self._toggle_zero).pack(side="left", padx=(0, 16))
        ctk.CTkButton(inner, text="↻ Refresh", width=80, height=30,
                      fg_color="#2c3e50", hover_color="#3d5166",
                      font=ctk.CTkFont(size=11),
                      command=self.refresh).pack(side="left", padx=(0, 8))
        _export_btns(inner, self._export_pdf, self._export_excel, self._export_csv)
        ctk.CTkFrame(inner, fg_color="#2c3e50", width=1, height=28
                     ).pack(side="left", padx=10, pady=4, fill="y")
        ctk.CTkButton(inner, text="🤖 AI Insights", width=100, height=34,
                      fg_color="#4a235a", hover_color="#6c3483",
                      font=ctk.CTkFont(size=11),
                      command=self._show_ai_insights).pack(side="left", padx=2)

        self._area = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._area.pack(fill="both", expand=True, padx=24, pady=(0, 24))
        self._render()

    def _toggle_zero(self):
        self._show_zero = self._zero_var.get()
        self._render()

    def _render(self):
        for w in self._area.winfo_children():
            w.destroy()
        data = db.get_stock_valuation(include_zero_stock=self._show_zero)
        self._last_data = data
        items = data["items"]

        # KPI tiles
        kpi_row = ctk.CTkFrame(self._area, fg_color="transparent")
        kpi_row.pack(fill="x", pady=(0, 10))
        for title, val, color in [
            ("Cost Value",    f"₹{data['total_cost_value']:,.0f}",  "#3498db"),
            ("Sale Value",    f"₹{data['total_sale_value']:,.0f}",  "#2ecc71"),
            ("Gross Margin",  f"₹{data['total_margin']:,.0f}",      "#f39c12"),
            ("Margin %",      f"{data['total_margin_pct']:.1f}%",   "#9b59b6"),
            ("Products",      str(data["item_count"]),               "#1abc9c"),
            ("Low Stock",     str(data["low_stock_count"]),          "#e74c3c"),
        ]:
            tile = ctk.CTkFrame(kpi_row, fg_color="#16213e", corner_radius=8)
            tile.pack(side="left", padx=(0, 6), ipadx=12, ipady=6)
            ctk.CTkLabel(tile, text=title, text_color="#95a5a6",
                         font=ctk.CTkFont(size=10)).pack()
            ctk.CTkLabel(tile, text=val, text_color=color,
                         font=ctk.CTkFont(size=15, weight="bold")).pack()

        if not items:
            ctk.CTkLabel(self._area, text="No products in stock.",
                         text_color="#555", font=ctk.CTkFont(size=13)).pack(pady=40)
            return

        # Table header
        hdr = ctk.CTkFrame(self._area, fg_color="#0f3460", corner_radius=6)
        hdr.pack(fill="x", pady=(0, 2))
        for col, w in [("SKU", 100), ("Product Name", 200), ("HSN", 80), ("Unit", 60),
                       ("Qty", 60), ("Cost ₹", 90), ("Sale ₹", 90),
                       ("Cost Value", 110), ("Sale Value", 110), ("Margin %", 80)]:
            ctk.CTkLabel(hdr, text=col, font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#ecf0f1", width=w, anchor="w").pack(side="left", padx=4, pady=6)

        for item in items:
            qty = item["stock_quantity"]
            low = qty <= item["low_stock_threshold"]
            zero = qty == 0
            row_bg = "#1c0a0a" if zero else ("#2c1a0a" if low else "#1a1a2e")
            row = ctk.CTkFrame(self._area, fg_color=row_bg, corner_radius=4)
            row.pack(fill="x", pady=1)

            margin_color = ("#e74c3c" if item["margin_pct"] < 0
                            else "#f39c12" if item["margin_pct"] < 15
                            else "#2ecc71")

            ctk.CTkLabel(row, text=item["sku"][:14], width=100, anchor="w",
                         font=ctk.CTkFont(size=10), text_color="#7f8c8d").pack(side="left", padx=4, pady=5)
            ctk.CTkLabel(row, text=item["name"][:28], width=200, anchor="w",
                         font=ctk.CTkFont(size=11)).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=item.get("hsn_code") or "—", width=80, anchor="w",
                         font=ctk.CTkFont(size=10), text_color="#7f8c8d").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=item.get("unit") or "pcs", width=60, anchor="w",
                         font=ctk.CTkFont(size=10)).pack(side="left", padx=4)
            qty_color = "#e74c3c" if zero else ("#f39c12" if low else "#ecf0f1")
            ctk.CTkLabel(row, text=str(qty), width=60, anchor="center",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=qty_color).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=f"{item['cost']:,.2f}", width=90, anchor="e",
                         font=ctk.CTkFont(size=11)).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=f"{item['unit_price']:,.2f}", width=90, anchor="e",
                         font=ctk.CTkFont(size=11)).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=f"₹{item['cost_value']:,.0f}", width=110, anchor="e",
                         font=ctk.CTkFont(size=11), text_color="#3498db").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=f"₹{item['sale_value']:,.0f}", width=110, anchor="e",
                         font=ctk.CTkFont(size=11), text_color="#2ecc71").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=f"{item['margin_pct']:.1f}%", width=80, anchor="center",
                         font=ctk.CTkFont(size=11), text_color=margin_color).pack(side="left", padx=4)

        # Totals row
        tot = ctk.CTkFrame(self._area, fg_color="#0f3460", corner_radius=4)
        tot.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(tot, text="TOTAL", width=100+200+80+60+60+90+90, anchor="w",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color="#ecf0f1").pack(side="left", padx=4, pady=5)
        ctk.CTkLabel(tot, text=f"₹{data['total_cost_value']:,.0f}", width=110, anchor="e",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color="#3498db").pack(side="left", padx=4)
        ctk.CTkLabel(tot, text=f"₹{data['total_sale_value']:,.0f}", width=110, anchor="e",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color="#2ecc71").pack(side="left", padx=4)
        ctk.CTkLabel(tot, text=f"{data['total_margin_pct']:.1f}%", width=80, anchor="center",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color="#f39c12").pack(side="left", padx=4)

    def _show_ai_insights(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("AI Insights", "Load the report first.")
            return
        d = self._last_data
        top5 = sorted(d["items"], key=lambda x: x["sale_value"], reverse=True)[:5]
        top5_txt = "\n".join(f"  • {i['name']}: ₹{i['sale_value']:,.0f} (margin {i['margin_pct']:.1f}%)"
                             for i in top5)
        low_txt = "\n".join(f"  • {i['name']}: {i['stock_quantity']} {i['unit']} left"
                            for i in d["items"] if i["stock_quantity"] <= i["low_stock_threshold"])[:800]
        prompt = (
            f"You are a stock management advisor for an Indian business.\n\n"
            f"Stock Valuation Summary:\n"
            f"  Total cost value: ₹{d['total_cost_value']:,.0f}\n"
            f"  Total sale value: ₹{d['total_sale_value']:,.0f}\n"
            f"  Gross margin: ₹{d['total_margin']:,.0f} ({d['total_margin_pct']:.1f}%)\n"
            f"  Products: {d['item_count']}, Low-stock items: {d['low_stock_count']}\n\n"
            f"Top 5 by sale value:\n{top5_txt}\n\n"
            f"Low stock items:\n{low_txt or '  (none)'}\n\n"
            "Provide 5 specific insights numbered 1–5 on: inventory risk, "
            "margin optimization, restocking priorities, dead stock, and cash tied up in inventory."
        )
        AIInsightsDialog(self, "Stock Valuation", prompt)

    def _export_pdf(self):
        import tkinter.filedialog as fd
        fp = fd.asksaveasfilename(defaultextension=".pdf",
                                  filetypes=[("PDF", "*.pdf")],
                                  initialfile="stock_valuation.pdf")
        if not fp:
            return
        import report_export as rex
        rex.export_stock_valuation_pdf(self._last_data, db.get_firm_settings(), fp)
        messagebox.showinfo("Exported", f"PDF saved:\n{fp}")

    def _export_excel(self):
        import tkinter.filedialog as fd
        fp = fd.asksaveasfilename(defaultextension=".xlsx",
                                  filetypes=[("Excel", "*.xlsx")],
                                  initialfile="stock_valuation.xlsx")
        if not fp:
            return
        import report_export as rex
        rex.export_stock_valuation_excel(self._last_data, db.get_firm_settings(), fp)
        messagebox.showinfo("Exported", f"Excel saved:\n{fp}")

    def _export_csv(self):
        import tkinter.filedialog as fd
        fp = fd.asksaveasfilename(defaultextension=".csv",
                                  filetypes=[("CSV", "*.csv")],
                                  initialfile="stock_valuation.csv")
        if not fp:
            return
        import report_export as rex
        rex.export_stock_valuation_csv(self._last_data, fp)
        messagebox.showinfo("Exported", f"CSV saved:\n{fp}")


# ── Payment Reminders Page ───────────────────────────────────────────────────

class PaymentRemindersPage(BasePage):
    FILTERS = [("All Outstanding", "all"), ("Overdue Only", "overdue"), ("Due This Week", "due_soon")]

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._filter = "all"

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._header("Payment Reminders", "Track & Send Outstanding Invoice Reminders")

        ctrl = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=10)
        ctrl.pack(fill="x", padx=24, pady=(0, 4))
        inner = ctk.CTkFrame(ctrl, fg_color="transparent")
        inner.pack(padx=16, pady=10, anchor="w")

        ctk.CTkLabel(inner, text="Filter:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 6))
        for label, key in self.FILTERS:
            fg = "#0f3460" if self._filter != key else "#1a6a3a"
            ctk.CTkButton(inner, text=label, width=130, height=30,
                          fg_color=fg, hover_color="#1a4a8a",
                          font=ctk.CTkFont(size=11),
                          command=lambda k=key: self._set_filter(k)).pack(side="left", padx=(0, 4))

        ctk.CTkFrame(inner, fg_color="#2c3e50", width=1, height=28
                     ).pack(side="left", padx=10, pady=4, fill="y")
        ctk.CTkButton(inner, text="↻ Refresh", width=80, height=30,
                      fg_color="#2c3e50", hover_color="#3d5166",
                      font=ctk.CTkFont(size=11),
                      command=self.refresh).pack(side="left")

        self._area = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._area.pack(fill="both", expand=True, padx=24, pady=(0, 24))
        self._load_table()

    def _set_filter(self, key):
        self._filter = key
        self.refresh()

    def _load_table(self):
        for w in self._area.winfo_children():
            w.destroy()

        invoices = db.get_outstanding_invoices_for_reminders(self._filter)
        if not invoices:
            ctk.CTkLabel(self._area, text="No outstanding invoices found.",
                         text_color="#555", font=ctk.CTkFont(size=13)).pack(pady=40)
            return

        # Summary KPIs
        total_bal = sum(r["balance_due"] for r in invoices)
        overdue_cnt = sum(1 for r in invoices if r["days_overdue"] > 0)
        kpi_row = ctk.CTkFrame(self._area, fg_color="transparent")
        kpi_row.pack(fill="x", pady=(0, 10))
        for title, val, color in [
            ("Total Outstanding", f"₹{total_bal:,.0f}", "#2ecc71"),
            ("Invoices", str(len(invoices)), "#3498db"),
            ("Overdue", str(overdue_cnt), "#e74c3c"),
        ]:
            tile = ctk.CTkFrame(kpi_row, fg_color="#16213e", corner_radius=8)
            tile.pack(side="left", padx=(0, 8), ipadx=14, ipady=8)
            ctk.CTkLabel(tile, text=title, text_color="#95a5a6",
                         font=ctk.CTkFont(size=10)).pack()
            ctk.CTkLabel(tile, text=val, text_color=color,
                         font=ctk.CTkFont(size=16, weight="bold")).pack()

        # Table header
        hdr = ctk.CTkFrame(self._area, fg_color="#0f3460", corner_radius=6)
        hdr.pack(fill="x", pady=(0, 2))
        for col, w in [("Client", 180), ("Invoice #", 110), ("Invoice Date", 100),
                       ("Due Date", 100), ("Balance Due", 110), ("Overdue", 80),
                       ("Reminders", 80), ("Last Sent", 100), ("Actions", 160)]:
            ctk.CTkLabel(hdr, text=col, font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#ecf0f1", width=w, anchor="w").pack(side="left", padx=4, pady=6)

        # Rows
        for inv in invoices:
            days = inv["days_overdue"]
            if days > 30:
                row_bg = "#2c1010"
            elif days > 0:
                row_bg = "#2c2010"
            else:
                row_bg = "#1a2a1a"
            row = ctk.CTkFrame(self._area, fg_color=row_bg, corner_radius=4)
            row.pack(fill="x", pady=1)

            overdue_color = "#e74c3c" if days > 30 else ("#f39c12" if days > 0 else "#2ecc71")
            overdue_txt = f"{days}d" if days > 0 else ("Due today" if days == 0 else f"In {-days}d")

            last_sent = inv.get("last_reminder_date") or "—"
            rem_count = inv.get("reminder_count", 0)

            ctk.CTkLabel(row, text=inv["client_name"][:22], width=180, anchor="w",
                         font=ctk.CTkFont(size=11)).pack(side="left", padx=4, pady=5)
            ctk.CTkLabel(row, text=inv["invoice_number"], width=110, anchor="w",
                         font=ctk.CTkFont(size=11)).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=inv["invoice_date"] or "—", width=100, anchor="w",
                         font=ctk.CTkFont(size=11), text_color="#95a5a6").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=inv["due_date"] or "—", width=100, anchor="w",
                         font=ctk.CTkFont(size=11), text_color="#95a5a6").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=f"₹{inv['balance_due']:,.0f}", width=110, anchor="w",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#2ecc71").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=overdue_txt, width=80, anchor="w",
                         font=ctk.CTkFont(size=11), text_color=overdue_color).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=str(rem_count), width=80, anchor="center",
                         font=ctk.CTkFont(size=11)).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=last_sent, width=100, anchor="w",
                         font=ctk.CTkFont(size=10), text_color="#7f8c8d").pack(side="left", padx=4)

            ctk.CTkButton(row, text="📨 Remind", width=90, height=26,
                          fg_color="#1a4a8a", hover_color="#2255a0",
                          font=ctk.CTkFont(size=10),
                          command=lambda i=inv: self._open_reminder_dialog(i)).pack(side="left", padx=2, pady=4)
            ctk.CTkButton(row, text="📜 History", width=64, height=26,
                          fg_color="#2c3e50", hover_color="#3d5166",
                          font=ctk.CTkFont(size=10),
                          command=lambda i=inv: self._show_history(i)).pack(side="left", padx=2)

    def _open_reminder_dialog(self, inv):
        ReminderSendDialog(self, inv, on_sent=self.refresh)

    def _show_history(self, inv):
        history = db.get_reminder_history(inv["id"])
        dlg = ctk.CTkToplevel(self)
        dlg.title(f"Reminder History — {inv['invoice_number']}")
        dlg.geometry("500x400")
        dlg.grab_set()
        ctk.CTkLabel(dlg, text=f"Reminder History: {inv['invoice_number']}",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(16, 4))
        ctk.CTkLabel(dlg, text=inv["client_name"], text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack()
        area = ctk.CTkScrollableFrame(dlg, fg_color="transparent")
        area.pack(fill="both", expand=True, padx=16, pady=12)
        if not history:
            ctk.CTkLabel(area, text="No reminders sent yet.",
                         text_color="#555").pack(pady=20)
        else:
            for h in history:
                row = ctk.CTkFrame(area, fg_color="#16213e", corner_radius=6)
                row.pack(fill="x", pady=2, padx=4)
                ctk.CTkLabel(row, text=h["reminder_date"], text_color="#2ecc71",
                             font=ctk.CTkFont(size=11, weight="bold"), width=110).pack(side="left", padx=8, pady=6)
                ctk.CTkLabel(row, text=h["method"], text_color="#3498db",
                             font=ctk.CTkFont(size=11), width=90).pack(side="left")
                ctk.CTkLabel(row, text=h.get("notes") or "—", text_color="#aaa",
                             font=ctk.CTkFont(size=10), anchor="w").pack(side="left", padx=4)
        ctk.CTkButton(dlg, text="Close", width=100,
                      command=dlg.destroy).pack(pady=(0, 12))


class ReminderSendDialog(ctk.CTkToplevel):
    METHODS = ["WhatsApp", "Email", "Phone Call", "SMS", "In Person", "Other"]

    def __init__(self, parent, inv, on_sent=None):
        super().__init__(parent)
        self.inv = inv
        self.on_sent = on_sent
        self.title(f"Send Reminder — {inv['invoice_number']}")
        self.geometry("560x600")
        self.grab_set()
        self._build()

    def _build(self):
        inv = self.inv
        ctk.CTkLabel(self, text="📨  Payment Reminder",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(16, 2))

        info = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=8)
        info.pack(fill="x", padx=20, pady=(0, 10))
        for label, val in [("Client", inv["client_name"]),
                           ("Invoice", inv["invoice_number"]),
                           ("Due Date", inv.get("due_date") or "—"),
                           ("Balance Due", f"₹{inv['balance_due']:,.0f}"),
                           ("Days Overdue", f"{inv['days_overdue']}d" if inv['days_overdue'] > 0 else "Not yet due")]:
            r = ctk.CTkFrame(info, fg_color="transparent")
            r.pack(fill="x", padx=12, pady=1)
            ctk.CTkLabel(r, text=f"{label}:", text_color="#95a5a6",
                         font=ctk.CTkFont(size=11), width=100, anchor="w").pack(side="left")
            ctk.CTkLabel(r, text=val, font=ctk.CTkFont(size=11, weight="bold"),
                         anchor="w").pack(side="left")

        ctk.CTkLabel(self, text="Method:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=20)
        self.method_var = ctk.StringVar(value="WhatsApp")
        ctk.CTkOptionMenu(self, values=self.METHODS, variable=self.method_var,
                          width=200, command=self._update_template).pack(anchor="w", padx=20, pady=(2, 8))

        ctk.CTkLabel(self, text="Message (editable):", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=20)
        self.msg_box = ctk.CTkTextbox(self, height=160, font=ctk.CTkFont(size=11))
        self.msg_box.pack(fill="x", padx=20, pady=(2, 8))
        self._update_template()

        ctk.CTkLabel(self, text="Notes (optional):", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=20)
        self.notes_entry = ctk.CTkEntry(self, width=500)
        self.notes_entry.pack(padx=20, pady=(2, 10))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=(0, 16))
        ctk.CTkButton(btns, text="📋 Copy Message", width=130,
                      fg_color="#2c3e50", hover_color="#3d5166",
                      command=self._copy_msg).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="✔ Mark as Sent", width=130,
                      fg_color="#1a6a3a", hover_color="#238a4f",
                      command=self._mark_sent).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="Cancel", width=90,
                      fg_color="#2c3e50", hover_color="#3d5166",
                      command=self.destroy).pack(side="left", padx=4)

    def _update_template(self, *_):
        inv = self.inv
        method = self.method_var.get()
        firm = db.get_firm_settings()
        firm_name = firm.get("firm_name", "Our Company") if firm else "Our Company"
        due = inv.get("due_date") or "—"
        bal = f"₹{inv['balance_due']:,.2f}"
        inv_no = inv["invoice_number"]
        client = inv["client_name"]
        days = inv["days_overdue"]
        overdue_note = f" (overdue by {days} days)" if days > 0 else ""

        if method == "Email":
            msg = (f"Subject: Payment Reminder — Invoice {inv_no}\n\n"
                   f"Dear {client},\n\n"
                   f"This is a friendly reminder that Invoice {inv_no} for {bal}{overdue_note} "
                   f"was due on {due}.\n\n"
                   f"Kindly arrange payment at the earliest to avoid any inconvenience.\n\n"
                   f"If you have already made the payment, please disregard this message "
                   f"or share the payment confirmation.\n\n"
                   f"Warm regards,\n{firm_name}")
        else:
            msg = (f"Dear {client},\n\n"
                   f"This is a gentle reminder for Invoice *{inv_no}*{overdue_note}.\n"
                   f"Amount due: *{bal}*\n"
                   f"Due date: {due}\n\n"
                   f"Please arrange payment at your earliest convenience. "
                   f"For any queries, feel free to reach out.\n\n"
                   f"Thank you,\n{firm_name}")

        self.msg_box.delete("1.0", "end")
        self.msg_box.insert("1.0", msg)

    def _copy_msg(self):
        msg = self.msg_box.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(msg)
        messagebox.showinfo("Copied", "Message copied to clipboard.")

    def _mark_sent(self):
        today = datetime.now().strftime("%Y-%m-%d")
        method = self.method_var.get()
        notes = self.notes_entry.get().strip()
        db.add_payment_reminder(self.inv["id"], today, method, notes)
        messagebox.showinfo("Recorded", f"Reminder logged for {self.inv['invoice_number']}.")
        if self.on_sent:
            self.on_sent()
        self.destroy()


# ── Client Ledger Page ───────────────────────────────────────────────────────

class ClientLedgerPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._header("Client Ledger", "Account statement per client with running balance")

        ctrl = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=10)
        ctrl.pack(fill="x", padx=24, pady=(0, 4))
        row1 = ctk.CTkFrame(ctrl, fg_color="transparent")
        row1.pack(padx=16, pady=(12, 4))

        # Client selector
        clients = db.get_all_clients()
        self._clients = {c["name"]: c["id"] for c in clients}
        names = list(self._clients.keys())

        ctk.CTkLabel(row1, text="Client:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.client_var = ctk.StringVar(value=names[0] if names else "")
        self.client_combo = ctk.CTkOptionMenu(row1, values=names, width=200,
                                              variable=self.client_var)
        self.client_combo.pack(side="left", padx=(0, 16))

        today = datetime.now().strftime("%Y-%m-%d")
        fy_start = datetime.now().replace(month=4, day=1).strftime("%Y-%m-%d")
        if datetime.now().month < 4:
            fy_start = datetime.now().replace(year=datetime.now().year - 1,
                                               month=4, day=1).strftime("%Y-%m-%d")

        ctk.CTkLabel(row1, text="From:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.from_date = ctk.CTkEntry(row1, width=120)
        self.from_date.insert(0, fy_start)
        self.from_date.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(row1, text="To:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.to_date = ctk.CTkEntry(row1, width=120)
        self.to_date.insert(0, today)
        self.to_date.pack(side="left", padx=(0, 16))

        ctk.CTkButton(row1, text="Generate", width=120, height=36,
                      fg_color="#0f3460", hover_color="#1a4a8a",
                      command=self._generate).pack(side="left")
        _export_btns(row1, self._export_pdf, self._export_excel, self._export_csv)
        ctk.CTkFrame(row1, fg_color="#2c3e50", width=1, height=28
                     ).pack(side="left", padx=10, pady=4, fill="y")
        ctk.CTkButton(row1, text="🤖 AI Insights", width=100, height=34,
                      fg_color="#4a235a", hover_color="#6c3483",
                      font=ctk.CTkFont(size=11),
                      command=self._show_ai_insights).pack(side="left", padx=2)

        # Presets row
        pr = ctk.CTkFrame(ctrl, fg_color="transparent")
        pr.pack(padx=16, pady=(0, 10), anchor="w")
        ctk.CTkLabel(pr, text="Quick:", text_color="#555",
                     font=ctk.CTkFont(size=10)).pack(side="left", padx=(0, 6))
        for lbl, cmd in [("This FY",    self._preset_this_fy),
                         ("This Month", self._preset_this_month),
                         ("Last Month", self._preset_last_month),
                         ("All Time",   self._preset_all_time)]:
            ctk.CTkButton(pr, text=lbl, width=90, height=22,
                          fg_color="#1e3a5f", hover_color="#2a4a7f",
                          font=ctk.CTkFont(size=10),
                          command=cmd).pack(side="left", padx=(0, 4))

        self._area = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._area.pack(fill="both", expand=True, padx=24, pady=(0, 24))
        ctk.CTkLabel(self._area, text="Select a client and click 'Generate'",
                     text_color="#555", font=ctk.CTkFont(size=13)).pack(pady=40)

    def _generate(self):
        for w in self._area.winfo_children():
            w.destroy()
        from_d = self.from_date.get().strip()
        to_d   = self.to_date.get().strip()
        name   = self.client_var.get()
        if not from_d or not to_d or not name:
            messagebox.showerror("Error", "Select a client and enter date range.")
            return
        client_id = self._clients.get(name)
        if not client_id:
            messagebox.showerror("Error", "Client not found.")
            return

        data = db.get_client_ledger(client_id, from_d, to_d)
        self._last_data = data

        firm = db.get_firm_settings()
        # ── Title
        if firm and firm["firm_name"]:
            ctk.CTkLabel(self._area, text=firm["firm_name"],
                         text_color="#3498db",
                         font=ctk.CTkFont(size=13)).pack(pady=(10, 0))
        ctk.CTkLabel(self._area, text="CLIENT LEDGER STATEMENT",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#ecf0f1").pack(pady=(2, 0))
        ctk.CTkLabel(self._area, text=f"{from_d}  to  {to_d}",
                     text_color="#95a5a6", font=ctk.CTkFont(size=11)).pack(pady=(0, 6))

        # ── Client info card
        c = data["client"]
        info = ctk.CTkFrame(self._area, fg_color="#16213e", corner_radius=8)
        info.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkLabel(info, text=c.get("name", ""), font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#3498db").pack(side="left", padx=14, pady=8)
        details = []
        if c.get("phone"): details.append(f"📞 {c['phone']}")
        if c.get("email"): details.append(f"✉ {c['email']}")
        if c.get("gstin"): details.append(f"GSTIN: {c['gstin']}")
        if details:
            ctk.CTkLabel(info, text="   ".join(details),
                         font=ctk.CTkFont(size=10), text_color="#95a5a6"
                         ).pack(side="left", padx=8)

        # ── KPI tiles
        kpi = ctk.CTkFrame(self._area, fg_color="transparent")
        kpi.pack(fill="x", padx=20, pady=(0, 10))
        kpi_items = [
            ("Opening Balance", data["opening"], "#f39c12"),
            ("Total Invoiced",  data["total_debit"],  "#3498db"),
            ("Total Received",  data["total_credit"], "#2ecc71"),
            ("Closing Balance", data["closing"],
             "#e74c3c" if data["closing"] > 0 else "#2ecc71"),
        ]
        for title, val, col in kpi_items:
            tile = ctk.CTkFrame(kpi, fg_color="#16213e", corner_radius=8)
            tile.pack(side="left", fill="x", expand=True, padx=(0, 8))
            ctk.CTkLabel(tile, text=title, font=ctk.CTkFont(size=10),
                         text_color="#95a5a6").pack(pady=(6, 0))
            ctk.CTkLabel(tile, text=f"₹ {val:,.2f}",
                         font=ctk.CTkFont(size=14, weight="bold"),
                         text_color=col).pack(pady=(0, 6))

        # ── Table header
        hdr = ctk.CTkFrame(self._area, fg_color="#0f3460", corner_radius=6)
        hdr.pack(fill="x", padx=20, pady=(4, 0))
        for col_txt, w, anc in [("Date", 100, "w"), ("Reference", 0, "w"),
                                  ("Type", 90, "w"),
                                  ("Debit (₹)", 130, "e"), ("Credit (₹)", 130, "e"),
                                  ("Balance (₹)", 140, "e")]:
            ctk.CTkLabel(hdr, text=col_txt, width=w, anchor=anc,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#ecf0f1"
                         ).pack(side="left", padx=(12 if anc == "w" and col_txt == "Date" else 4),
                                pady=6)

        # ── Opening balance row
        ob_row = ctk.CTkFrame(self._area, fg_color="#0a0a1e", corner_radius=0)
        ob_row.pack(fill="x", padx=20)
        ctk.CTkLabel(ob_row, text=from_d, width=100, anchor="w",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#f39c12").pack(side="left", padx=12, pady=4)
        ctk.CTkLabel(ob_row, text="Opening Balance", anchor="w",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#f39c12").pack(side="left", padx=4, fill="x", expand=True)
        ctk.CTkLabel(ob_row, text="B/F", width=90, anchor="w",
                     font=ctk.CTkFont(size=11), text_color="#f39c12").pack(side="left", padx=4)
        ctk.CTkLabel(ob_row, text="—", width=130, anchor="e",
                     text_color="#555").pack(side="left", padx=4)
        ctk.CTkLabel(ob_row, text="—", width=130, anchor="e",
                     text_color="#555").pack(side="left", padx=4)
        ctk.CTkLabel(ob_row, text=f"{data['opening']:,.2f}", width=140, anchor="e",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#f39c12").pack(side="left", padx=(4, 12))

        if not data["rows"]:
            ctk.CTkLabel(self._area, text="No transactions in this period.",
                         text_color="#555", font=ctk.CTkFont(size=12)).pack(pady=16)
        else:
            for i, r in enumerate(data["rows"]):
                bg = "#1a1a2e" if i % 2 == 0 else "#16213e"
                drow = ctk.CTkFrame(self._area, fg_color=bg, corner_radius=0)
                drow.pack(fill="x", padx=20)
                is_inv = r["txn_type"] == "Invoice"
                type_col = "#3498db" if is_inv else "#2ecc71"
                bal_col = "#e74c3c" if r["balance"] > 0 else "#2ecc71"

                ctk.CTkLabel(drow, text=r["txn_date"], width=100, anchor="w",
                             font=ctk.CTkFont(size=11),
                             text_color="#95a5a6").pack(side="left", padx=12, pady=4)
                ctk.CTkLabel(drow, text=r["ref"], anchor="w",
                             font=ctk.CTkFont(size=11),
                             text_color="#ecf0f1" if is_inv else "#2ecc71"
                             ).pack(side="left", padx=4, fill="x", expand=True)
                ctk.CTkLabel(drow, text=r["txn_type"], width=90, anchor="w",
                             font=ctk.CTkFont(size=10),
                             text_color=type_col).pack(side="left", padx=4)
                dr_txt = f"{r['debit']:,.2f}" if r["debit"] else "—"
                cr_txt = f"{r['credit']:,.2f}" if r["credit"] else "—"
                ctk.CTkLabel(drow, text=dr_txt, width=130, anchor="e",
                             font=ctk.CTkFont(size=11),
                             text_color="#3498db" if r["debit"] else "#555"
                             ).pack(side="left", padx=4)
                ctk.CTkLabel(drow, text=cr_txt, width=130, anchor="e",
                             font=ctk.CTkFont(size=11),
                             text_color="#2ecc71" if r["credit"] else "#555"
                             ).pack(side="left", padx=4)
                ctk.CTkLabel(drow, text=f"{r['balance']:,.2f}", width=140, anchor="e",
                             font=ctk.CTkFont(size=11, weight="bold"),
                             text_color=bal_col).pack(side="left", padx=(4, 12))

        # ── Totals row
        ctk.CTkFrame(self._area, fg_color="#0f3460", height=1).pack(fill="x", padx=20, pady=2)
        tot = ctk.CTkFrame(self._area, fg_color="#0f3460", corner_radius=6)
        tot.pack(fill="x", padx=20)
        ctk.CTkLabel(tot, text="", width=100).pack(side="left", padx=12)
        ctk.CTkLabel(tot, text="TOTALS", anchor="w",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#ecf0f1").pack(side="left", padx=4, fill="x", expand=True)
        ctk.CTkLabel(tot, text="", width=90).pack(side="left")
        ctk.CTkLabel(tot, text=f"{data['total_debit']:,.2f}", width=130, anchor="e",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#3498db").pack(side="left", padx=4, pady=8)
        ctk.CTkLabel(tot, text=f"{data['total_credit']:,.2f}", width=130, anchor="e",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#2ecc71").pack(side="left", padx=4)
        close_col = "#e74c3c" if data["closing"] > 0 else "#2ecc71"
        ctk.CTkLabel(tot, text=f"{data['closing']:,.2f}", width=140, anchor="e",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=close_col).pack(side="left", padx=(4, 12))

        # ── Closing balance status
        status_txt = (f"Closing Balance: ₹{data['closing']:,.2f} "
                      f"{'(Amount Receivable)' if data['closing'] > 0 else '(Fully Paid / Credit)'}")
        banner = ctk.CTkFrame(self._area, fg_color="#0f3460", corner_radius=8)
        banner.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(banner, text=status_txt,
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=close_col).pack(padx=16, pady=10)

    def _set_range(self, f, t):
        self.from_date.delete(0, "end"); self.from_date.insert(0, f)
        self.to_date.delete(0, "end");   self.to_date.insert(0, t)
        self._generate()

    def _preset_this_fy(self):
        t = datetime.now()
        fy = t.year if t.month >= 4 else t.year - 1
        self._set_range(f"{fy}-04-01", t.strftime("%Y-%m-%d"))

    def _preset_this_month(self):
        t = datetime.now()
        self._set_range(t.replace(day=1).strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d"))

    def _preset_last_month(self):
        t = datetime.now().replace(day=1) - timedelta(days=1)
        self._set_range(t.replace(day=1).strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d"))

    def _preset_all_time(self):
        self._set_range("2000-01-01", datetime.now().strftime("%Y-%m-%d"))

    def _show_ai_insights(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("AI Insights", "Generate the report first.")
            return
        d = self._last_data
        rows_txt = "\n".join(
            f"  {r['txn_date']}  {r['txn_type']:8s}  {r['ref']:20s}  "
            f"Dr:{r['debit']:,.0f}  Cr:{r['credit']:,.0f}  Bal:{r['balance']:,.0f}"
            for r in d["rows"][:15]
        )
        prompt = (
            f"You are a credit control advisor for an Indian business.\n\n"
            f"Client Ledger — {d['client'].get('name', '')}\n"
            f"Period: {d['from_date']} to {d['to_date']}\n"
            f"Opening Balance: ₹{d['opening']:,.0f}\n"
            f"Total Invoiced:  ₹{d['total_debit']:,.0f}\n"
            f"Total Received:  ₹{d['total_credit']:,.0f}\n"
            f"Closing Balance: ₹{d['closing']:,.0f}\n\n"
            f"Recent transactions (up to 15):\n{rows_txt or '  (none)'}\n\n"
            "Provide 5 specific insights numbered 1–5 on: payment behaviour, "
            "credit risk, collection actions, relationship health, and recommendations."
        )
        AIInsightsDialog(self, "Client Ledger", prompt)

    def _export_pdf(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("Export", "Generate the report first."); return
        firm = (db.get_firm_settings() or {}).get("firm_name", "")
        client_name = self._last_data["client"].get("name", "Client").replace(" ", "_")
        _run_export(rex.export_client_ledger_pdf, f"Client_Ledger_{client_name}.pdf",
                    self._last_data, firm)

    def _export_excel(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("Export", "Generate the report first."); return
        firm = (db.get_firm_settings() or {}).get("firm_name", "")
        client_name = self._last_data["client"].get("name", "Client").replace(" ", "_")
        _run_export(rex.export_client_ledger_excel, f"Client_Ledger_{client_name}.xlsx",
                    self._last_data, firm)

    def _export_csv(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("Export", "Generate the report first."); return
        client_name = self._last_data["client"].get("name", "Client").replace(" ", "_")
        _run_export(rex.export_client_ledger_csv, f"Client_Ledger_{client_name}.csv",
                    self._last_data)


# ── Debtors Aging Page ────────────────────────────────────────────────────────

AGING_COLORS = ["#2ecc71", "#f39c12", "#e67e22", "#e74c3c", "#8e44ad"]

class DebtorsAgingPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._header("Debtors Aging", "Outstanding Receivables by Age")

        ctrl = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=10)
        ctrl.pack(fill="x", padx=24, pady=(0, 4))
        inner = ctk.CTkFrame(ctrl, fg_color="transparent")
        inner.pack(padx=16, pady=(12, 4))

        today = datetime.now().strftime("%Y-%m-%d")
        ctk.CTkLabel(inner, text="As of Date:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.as_of = ctk.CTkEntry(inner, width=130)
        self.as_of.insert(0, today)
        self.as_of.pack(side="left", padx=(0, 16))
        ctk.CTkButton(inner, text="Generate", width=130, height=36,
                      fg_color="#0f3460", hover_color="#1a4a8a",
                      command=self._generate).pack(side="left")
        _export_btns(inner, self._export_pdf, self._export_excel, self._export_csv)
        ctk.CTkFrame(inner, fg_color="#2c3e50", width=1, height=28
                     ).pack(side="left", padx=10, pady=4, fill="y")
        ctk.CTkButton(inner, text="🤖 AI Insights", width=100, height=34,
                      fg_color="#4a235a", hover_color="#6c3483",
                      font=ctk.CTkFont(size=11),
                      command=self._show_ai_insights).pack(side="left", padx=2)

        pr = ctk.CTkFrame(ctrl, fg_color="transparent")
        pr.pack(padx=16, pady=(0, 10), anchor="w")
        ctk.CTkLabel(pr, text="Quick:", text_color="#555",
                     font=ctk.CTkFont(size=10)).pack(side="left", padx=(0, 6))
        for lbl, cmd in [("Today",         self._preset_today),
                         ("End Last Month", self._preset_end_last_month),
                         ("End Last Qtr",  self._preset_end_last_qtr)]:
            ctk.CTkButton(pr, text=lbl, width=100, height=22,
                          fg_color="#1e3a5f", hover_color="#2a4a7f",
                          font=ctk.CTkFont(size=10),
                          command=cmd).pack(side="left", padx=(0, 4))

        self._area = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._area.pack(fill="both", expand=True, padx=24, pady=(0, 24))
        ctk.CTkLabel(self._area,
                     text="Enter a date and click 'Generate'",
                     text_color="#555", font=ctk.CTkFont(size=13)).pack(pady=40)

    def _generate(self):
        for w in self._area.winfo_children():
            w.destroy()
        as_of = self.as_of.get().strip()
        if not as_of:
            messagebox.showerror("Error", "Enter a date.")
            return
        data = db.get_debtors_aging(as_of)
        self._last_data, self._last_as_of = data, as_of

        # ── Title
        ctk.CTkLabel(self._area, text="DEBTORS AGING REPORT",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#ecf0f1").pack(pady=(12, 2))
        ctk.CTkLabel(self._area, text=f"As at  {as_of}",
                     text_color="#95a5a6", font=ctk.CTkFont(size=11)).pack()
        firm = db.get_firm_settings()
        if firm and firm["firm_name"]:
            ctk.CTkLabel(self._area, text=firm["firm_name"],
                         text_color="#3498db",
                         font=ctk.CTkFont(size=13)).pack(pady=(2, 10))

        if not data["clients"]:
            ctk.CTkLabel(self._area, text="No outstanding debtors — all invoices paid!",
                         text_color="#2ecc71",
                         font=ctk.CTkFont(size=13)).pack(pady=30)
            return

        labels = data["labels"]
        COL_W  = 110    # bucket column width

        # ── Summary table header
        def tbl_hdr():
            hdr = ctk.CTkFrame(self._area, fg_color="#0f3460", corner_radius=6)
            hdr.pack(fill="x", padx=20, pady=(8, 0))
            ctk.CTkLabel(hdr, text="Client",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#ecf0f1", anchor="w").pack(
                             side="left", padx=14, pady=8, fill="x", expand=True)
            for lbl, col in zip(labels, AGING_COLORS):
                ctk.CTkLabel(hdr, text=lbl,
                             font=ctk.CTkFont(size=10, weight="bold"),
                             text_color=col, width=COL_W, anchor="e").pack(side="left", padx=3)
            ctk.CTkLabel(hdr, text="Total",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#ecf0f1", width=COL_W, anchor="e").pack(side="left", padx=(3, 14))

        tbl_hdr()

        for i, client in enumerate(data["clients"]):
            bg = "#1a1a2e" if i % 2 == 0 else "#16213e"
            row = ctk.CTkFrame(self._area, fg_color=bg, corner_radius=0)
            row.pack(fill="x", padx=20)
            ctk.CTkLabel(row, text=client["name"],
                         font=ctk.CTkFont(size=11), text_color="#ecf0f1",
                         anchor="w").pack(side="left", padx=14, pady=5, fill="x", expand=True)
            for val, col in zip(client["buckets"], AGING_COLORS):
                txt   = f"{val:,.2f}" if val else "—"
                tcolor = col if val else "#555"
                ctk.CTkLabel(row, text=txt,
                             font=ctk.CTkFont(size=11), text_color=tcolor,
                             width=COL_W, anchor="e").pack(side="left", padx=3)
            ctk.CTkLabel(row, text=f"{client['total']:,.2f}",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#ecf0f1", width=COL_W, anchor="e"
                         ).pack(side="left", padx=(3, 14))

        # ── Grand totals row
        ctk.CTkFrame(self._area, fg_color="#0f3460", height=1).pack(fill="x", padx=20, pady=2)
        tot = ctk.CTkFrame(self._area, fg_color="#0f3460", corner_radius=6)
        tot.pack(fill="x", padx=20)
        ctk.CTkLabel(tot, text="TOTAL",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#ecf0f1", anchor="w").pack(
                         side="left", padx=14, pady=8, fill="x", expand=True)
        for val, col in zip(data["grand_buckets"], AGING_COLORS):
            txt    = f"{val:,.2f}" if val else "—"
            tcolor = col if val else "#555"
            ctk.CTkLabel(tot, text=txt,
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=tcolor, width=COL_W, anchor="e").pack(side="left", padx=3)
        ctk.CTkLabel(tot, text=f"{data['grand_total']:,.2f}",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#2ecc71", width=COL_W, anchor="e"
                     ).pack(side="left", padx=(3, 14))

        # ── Invoice detail list
        ctk.CTkFrame(self._area, fg_color="transparent", height=12).pack()
        ctk.CTkLabel(self._area, text="Invoice Detail",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#ecf0f1").pack(anchor="w", padx=20, pady=(4, 2))

        # detail header
        dhdr = ctk.CTkFrame(self._area, fg_color="#0f3460", corner_radius=6)
        dhdr.pack(fill="x", padx=20, pady=(2, 0))
        for col, w, anc in [("Invoice #", 110, "w"), ("Client", 0, "w"),
                             ("Inv Date", 100, "w"), ("Due Date", 100, "w"),
                             ("Days", 60, "e"), ("Amount (₹)", 120, "e"), ("Status", 80, "w")]:
            ctk.CTkLabel(dhdr, text=col,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#ecf0f1", width=w, anchor=anc
                         ).pack(side="left", padx=(10 if anc == "w" and col == "Invoice #" else 4), pady=6)

        all_invoices = []
        for client in data["clients"]:
            for inv in client["invoices"]:
                inv["client_name"] = client["name"]
                all_invoices.append(inv)
        all_invoices.sort(key=lambda x: x["days_overdue"], reverse=True)

        for j, inv in enumerate(all_invoices):
            bg = "#1a1a2e" if j % 2 == 0 else "#16213e"
            days = inv["days_overdue"]
            if days <= 30:
                age_col = AGING_COLORS[0]
            elif days <= 60:
                age_col = AGING_COLORS[1]
            elif days <= 90:
                age_col = AGING_COLORS[2]
            elif days <= 120:
                age_col = AGING_COLORS[3]
            else:
                age_col = AGING_COLORS[4]
            drow = ctk.CTkFrame(self._area, fg_color=bg, corner_radius=0)
            drow.pack(fill="x", padx=20)
            ctk.CTkLabel(drow, text=inv["invoice_number"],
                         font=ctk.CTkFont(size=11), text_color="#3498db",
                         width=110, anchor="w").pack(side="left", padx=10, pady=4)
            ctk.CTkLabel(drow, text=inv["client_name"],
                         font=ctk.CTkFont(size=11), text_color="#ecf0f1",
                         anchor="w").pack(side="left", padx=4, fill="x", expand=True)
            ctk.CTkLabel(drow, text=inv["invoice_date"],
                         font=ctk.CTkFont(size=11), text_color="#95a5a6",
                         width=100, anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(drow, text=inv["due_date"],
                         font=ctk.CTkFont(size=11), text_color="#95a5a6",
                         width=100, anchor="w").pack(side="left", padx=4)
            days_txt = f"{days}d" if days >= 0 else f"({abs(days)}d)"
            ctk.CTkLabel(drow, text=days_txt,
                         font=ctk.CTkFont(size=11), text_color=age_col,
                         width=60, anchor="e").pack(side="left", padx=4)
            ctk.CTkLabel(drow, text=f"{inv['amount']:,.2f}",
                         font=ctk.CTkFont(size=11), text_color="#ecf0f1",
                         width=120, anchor="e").pack(side="left", padx=4)
            status_color = "#f39c12" if inv["status"] == "Sent" else "#95a5a6"
            ctk.CTkLabel(drow, text=inv["status"],
                         font=ctk.CTkFont(size=10), text_color=status_color,
                         width=80, anchor="w").pack(side="left", padx=(4, 10))


    def _set_as_of(self, d):
        self.as_of.delete(0, "end"); self.as_of.insert(0, d)
        self._generate()

    def _preset_today(self):
        self._set_as_of(datetime.now().strftime("%Y-%m-%d"))

    def _preset_end_last_month(self):
        d = datetime.now().replace(day=1) - timedelta(days=1)
        self._set_as_of(d.strftime("%Y-%m-%d"))

    def _preset_end_last_qtr(self):
        t = datetime.now()
        q = ((t.month - 1) // 3) * 3 + 1
        d = t.replace(month=q, day=1) - timedelta(days=1)
        self._set_as_of(d.strftime("%Y-%m-%d"))

    def _show_ai_insights(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("AI Insights", "Generate the report first.")
            return
        d = self._last_data
        grand = d["grand_total"]
        buckets = dict(zip(d["labels"], d["grand_buckets"]))
        overdue_30 = sum(v for lbl, v in buckets.items() if lbl != "0–30 days")
        clients_txt = "\n".join(
            f"  • {c['name']}: ₹{c['total']:,.0f}" for c in d["clients"][:10]
        )
        bucket_txt = "\n".join(
            f"  {lbl}: ₹{val:,.0f}" for lbl, val in buckets.items()
        )
        prompt = (
            f"You are a credit control advisor for an Indian business.\n\n"
            f"Debtors Aging Report — As at: {self._last_as_of}\n"
            f"Total Outstanding: ₹{grand:,.0f}\n"
            f"Overdue > 30 days: ₹{overdue_30:,.0f}\n\n"
            f"Aging Buckets:\n{bucket_txt}\n\n"
            f"Top clients by outstanding:\n{clients_txt or '  (none)'}\n\n"
            "Provide 5 specific insights numbered 1–5 on: collection risk, "
            "overdue concentration, recommended follow-up actions, credit policy, "
            "and cash flow impact."
        )
        AIInsightsDialog(self, "Debtors Aging", prompt)

    def _export_pdf(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("Export", "Generate the report first."); return
        firm = (db.get_firm_settings() or {}).get("firm_name", "")
        _run_export(rex.export_aging_pdf, "Debtors_Aging.pdf",
                    self._last_data, self._last_as_of, firm)

    def _export_excel(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("Export", "Generate the report first."); return
        firm = (db.get_firm_settings() or {}).get("firm_name", "")
        _run_export(rex.export_aging_excel, "Debtors_Aging.xlsx",
                    self._last_data, self._last_as_of, firm)

    def _export_csv(self):
        if not getattr(self, "_last_data", None):
            messagebox.showinfo("Export", "Generate the report first."); return
        _run_export(rex.export_aging_csv, "Debtors_Aging.csv",
                    self._last_data, self._last_as_of)



# ── GST Reports Page ──────────────────────────────────────────────────────────

class GSTReportsPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._active_tab    = "gstr1"
        self._last_data_gstr1   = None
        self._last_data_gstr3b  = None
        self._last_data_summary = None
        self._last_from = ""
        self._last_to   = ""

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._header("GST Reports", "GSTR-1 Outward Supplies  &  GSTR-3B Monthly Summary")

        ctrl  = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=10)
        ctrl.pack(fill="x", padx=24, pady=(0, 4))
        inner = ctk.CTkFrame(ctrl, fg_color="transparent")
        inner.pack(padx=16, pady=(12, 4))

        from_dt  = datetime.now().replace(day=1)
        from_def = from_dt.strftime("%Y-%m-%d")
        to_def   = datetime.now().strftime("%Y-%m-%d")

        ctk.CTkLabel(inner, text="From:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.from_date = ctk.CTkEntry(inner, width=120)
        self.from_date.insert(0, from_def)
        self.from_date.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(inner, text="To:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self.to_date = ctk.CTkEntry(inner, width=120)
        self.to_date.insert(0, to_def)
        self.to_date.pack(side="left", padx=(0, 16))

        ctk.CTkFrame(inner, fg_color="#2c3e50", width=1, height=28).pack(
            side="left", padx=8, pady=4, fill="y")
        ctk.CTkButton(inner, text="GSTR-1",  width=90, height=36,
                      fg_color="#0f3460", hover_color="#1a4a8a",
                      command=lambda: self._switch("gstr1")).pack(side="left", padx=(0, 4))
        ctk.CTkButton(inner, text="GSTR-3B", width=90, height=36,
                      fg_color="#16213e", hover_color="#1a4a8a",
                      command=lambda: self._switch("gstr3b")).pack(side="left", padx=(0, 4))
        ctk.CTkButton(inner, text="📊 Summary", width=100, height=36,
                      fg_color="#16213e", hover_color="#1a4a8a",
                      command=lambda: self._switch("summary")).pack(side="left", padx=(0, 4))

        _export_btns(inner, self._export_pdf, self._export_excel, self._export_csv)
        ctk.CTkFrame(inner, fg_color="#2c3e50", width=1, height=28
                     ).pack(side="left", padx=10, pady=4, fill="y")
        ctk.CTkButton(inner, text="✨ AI Insights", width=112, height=34,
                      fg_color="#6c3483", hover_color="#8e44ad",
                      font=ctk.CTkFont(size=11),
                      command=self._show_ai_insights).pack(side="left", padx=2)

        pr = ctk.CTkFrame(ctrl, fg_color="transparent")
        pr.pack(padx=16, pady=(0, 10), anchor="w")
        ctk.CTkLabel(pr, text="Quick:", text_color="#555",
                     font=ctk.CTkFont(size=10)).pack(side="left", padx=(0, 6))
        for lbl, cmd in [("This Month",   self._gst_this_month),
                         ("Last Month",   self._gst_last_month),
                         ("Last Quarter", self._gst_last_qtr)]:
            ctk.CTkButton(pr, text=lbl, width=90, height=22,
                          fg_color="#1e3a5f", hover_color="#2a4a7f",
                          font=ctk.CTkFont(size=10),
                          command=cmd).pack(side="left", padx=(0, 4))

        self._area = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._area.pack(fill="both", expand=True, padx=24, pady=(0, 24))
        ctk.CTkLabel(self._area,
                     text="Select a date range and click GSTR-1 or GSTR-3B",
                     text_color="#555", font=ctk.CTkFont(size=13)).pack(pady=40)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _gst_set_range(self, from_d, to_d):
        self.from_date.delete(0, "end"); self.from_date.insert(0, from_d)
        self.to_date.delete(0, "end");   self.to_date.insert(0, to_d)

    def _gst_this_month(self):
        t = datetime.now()
        self._gst_set_range(t.replace(day=1).strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d"))

    def _gst_last_month(self):
        t = datetime.now().replace(day=1) - timedelta(days=1)
        self._gst_set_range(t.replace(day=1).strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d"))

    def _gst_last_qtr(self):
        t = datetime.now()
        q = ((t.month - 1) // 3) * 3 + 1
        end = t.replace(month=q, day=1) - timedelta(days=1)
        start_q = ((end.month - 1) // 3) * 3 + 1
        self._gst_set_range(end.replace(month=start_q, day=1).strftime("%Y-%m-%d"),
                            end.strftime("%Y-%m-%d"))

    def _switch(self, tab):
        self._active_tab = tab
        self._generate()

    def _generate(self):
        for w in self._area.winfo_children():
            w.destroy()
        from_d = self.from_date.get().strip()
        to_d   = self.to_date.get().strip()
        if not from_d or not to_d:
            messagebox.showerror("Error", "Enter both dates.")
            return
        self._last_from, self._last_to = from_d, to_d
        if self._active_tab == "gstr1":
            data = db.get_gstr1(from_d, to_d)
            self._last_data_gstr1 = data
            self._render_gstr1(data, from_d, to_d)
        elif self._active_tab == "summary":
            data = db.get_gst_summary(from_d, to_d)
            self._last_data_summary = data
            self._render_gst_summary(data, from_d, to_d)
        else:
            data = db.get_gstr3b(from_d, to_d)
            self._last_data_gstr3b = data
            self._render_gstr3b(data, from_d, to_d)

    # ── GSTR-1 ────────────────────────────────────────────────────────────────

    def _render_gstr1(self, data, from_d, to_d):
        firm = db.get_firm_settings()
        firm_name = (firm["firm_name"] if firm and firm["firm_name"] else "")
        ctk.CTkLabel(self._area, text="GSTR-1  OUTWARD SUPPLY DETAILS",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#ecf0f1").pack(pady=(12, 2))
        ctk.CTkLabel(self._area, text=f"Period: {from_d}  to  {to_d}",
                     text_color="#95a5a6", font=ctk.CTkFont(size=11)).pack()
        if firm_name:
            ctk.CTkLabel(self._area, text=firm_name,
                         text_color="#3498db", font=ctk.CTkFont(size=11)).pack()

        def sec_title(text):
            f = ctk.CTkFrame(self._area, fg_color="#16213e", corner_radius=6)
            f.pack(fill="x", padx=20, pady=(12, 2))
            ctk.CTkLabel(f, text=text,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#3498db").pack(anchor="w", padx=12, pady=6)

        def col_row(texts, widths, bold=False, bg="transparent", num_start=5):
            row = ctk.CTkFrame(self._area, fg_color=bg, corner_radius=0)
            row.pack(fill="x", padx=20)
            for i, (t, w) in enumerate(zip(texts, widths)):
                tc = "#95a5a6" if bold else ("#2ecc71" if i >= num_start else "#ecf0f1")
                ctk.CTkLabel(row, text=str(t),
                             font=ctk.CTkFont(size=10, weight="bold" if bold else "normal"),
                             text_color=tc, width=w,
                             anchor="e" if i >= num_start else "w"
                             ).pack(side="left", padx=2, pady=3)

        B2B_W = [100, 88, 120, 130, 55, 85, 75, 75, 75, 90]
        B2C_W = [100, 88, 160, 60, 90, 80, 80, 80, 90]
        HSN_W = [80,  150, 50, 70, 100, 80, 80, 80, 90]

        # B2B
        sec_title(f"4A  B2B Invoices (Registered Buyers)  —  {len(data['b2b'])} invoice(s)")
        col_row(["Invoice #", "Date", "Client", "GSTIN", "Type",
                 "Taxable ₹", "CGST ₹", "SGST ₹", "IGST ₹", "Total ₹"],
                B2B_W, bold=True)
        for i, r in enumerate(data["b2b"]):
            col_row([r["invoice_number"], r["invoice_date"], r["client_name"],
                     r["client_gstin"] or "—", r["supply_type"].upper(),
                     f"{r['subtotal']:,.2f}", f"{r['cgst_total']:,.2f}",
                     f"{r['sgst_total']:,.2f}", f"{r['igst_total']:,.2f}",
                     f"{r['grand_total']:,.2f}"],
                    B2B_W, bg="#1a1a2e" if i % 2 == 0 else "#16213e")
        if not data["b2b"]:
            ctk.CTkLabel(self._area, text="  No B2B invoices in this period.",
                         text_color="#555", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=40)
        t = data["b2b_total"]
        col_row(["Total B2B", "", "", "", "",
                 f"{t['taxable']:,.2f}", f"{t['cgst']:,.2f}",
                 f"{t['sgst']:,.2f}", f"{t['igst']:,.2f}", f"{t['grand']:,.2f}"],
                B2B_W, bold=True, bg="#0f3460")

        # B2C
        sec_title(f"B2C Invoices (Unregistered Buyers)  —  {len(data['b2c'])} invoice(s)")
        col_row(["Invoice #", "Date", "Client", "Type",
                 "Taxable ₹", "CGST ₹", "SGST ₹", "IGST ₹", "Total ₹"],
                B2C_W, bold=True, num_start=4)
        for i, r in enumerate(data["b2c"]):
            col_row([r["invoice_number"], r["invoice_date"], r["client_name"],
                     r["supply_type"].upper(),
                     f"{r['subtotal']:,.2f}", f"{r['cgst_total']:,.2f}",
                     f"{r['sgst_total']:,.2f}", f"{r['igst_total']:,.2f}",
                     f"{r['grand_total']:,.2f}"],
                    B2C_W, bg="#1a1a2e" if i % 2 == 0 else "#16213e", num_start=4)
        if not data["b2c"]:
            ctk.CTkLabel(self._area, text="  No B2C invoices in this period.",
                         text_color="#555", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=40)
        t = data["b2c_total"]
        col_row(["Total B2C", "", "", "",
                 f"{t['taxable']:,.2f}", f"{t['cgst']:,.2f}",
                 f"{t['sgst']:,.2f}", f"{t['igst']:,.2f}", f"{t['grand']:,.2f}"],
                B2C_W, bold=True, bg="#0f3460", num_start=4)

        # HSN
        sec_title("12  HSN / SAC Summary")
        col_row(["HSN Code", "Description", "UQC", "Qty",
                 "Taxable ₹", "CGST ₹", "SGST ₹", "IGST ₹", "Total Tax ₹"],
                HSN_W, bold=True, num_start=4)
        for i, r in enumerate(data["hsn"]):
            col_row([r["hsn_code"] or "—", (r["description"] or "")[:22],
                     r["unit"] or "", f"{r['total_qty']:.2f}",
                     f"{r['taxable_value']:,.2f}", f"{r['cgst']:,.2f}",
                     f"{r['sgst']:,.2f}", f"{r['igst']:,.2f}", f"{r['total_tax']:,.2f}"],
                    HSN_W, bg="#1a1a2e" if i % 2 == 0 else "#16213e", num_start=4)
        if not data["hsn"]:
            ctk.CTkLabel(self._area, text="  No HSN data in this period.",
                         text_color="#555", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=40)

        # Grand total
        g = data["grand"]
        ctk.CTkFrame(self._area, fg_color="#2c3e50", height=1
                     ).pack(fill="x", padx=20, pady=8)
        col_row(["GRAND TOTAL", "", "", "", "",
                 f"{g['taxable']:,.2f}", f"{g['cgst']:,.2f}",
                 f"{g['sgst']:,.2f}", f"{g['igst']:,.2f}", f"{g['grand']:,.2f}"],
                B2B_W, bold=True, bg="#1a3a5c")

    # ── GST Summary ───────────────────────────────────────────────────────────

    def _render_gst_summary(self, data, from_d, to_d):
        import tkinter as tk
        firm = db.get_firm_settings()
        firm_name = (firm["firm_name"] if firm and firm["firm_name"] else "")
        ctk.CTkLabel(self._area, text="GST SUMMARY DASHBOARD",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#ecf0f1").pack(pady=(12, 2))
        ctk.CTkLabel(self._area, text=f"Period: {from_d}  to  {to_d}",
                     text_color="#95a5a6", font=ctk.CTkFont(size=11)).pack()
        if firm_name:
            ctk.CTkLabel(self._area, text=firm_name,
                         text_color="#3498db", font=ctk.CTkFont(size=11)).pack(pady=(0,8))

        # ── KPI tiles ────────────────────────────────────────────────────────
        kpi = ctk.CTkFrame(self._area, fg_color="transparent")
        kpi.pack(fill="x", padx=20, pady=(4, 12))
        for i in range(5):
            kpi.columnconfigure(i, weight=1)
        kpi_data = [
            ("Invoices",       str(data["invoice_count"]),   "#3498db"),
            ("Taxable Value",  f"₹{data['taxable_value']:,.0f}", "#ecf0f1"),
            ("CGST Collected", f"₹{data['cgst']:,.0f}",      "#f39c12"),
            ("SGST Collected", f"₹{data['sgst']:,.0f}",      "#f39c12"),
            ("IGST Collected", f"₹{data['igst']:,.0f}",      "#9b59b6"),
        ]
        for i, (title, val, color) in enumerate(kpi_data):
            c = self._card(kpi, title, val, color, "")
            c.grid(row=0, column=i, padx=5, sticky="ew")

        # Net GST banner
        net = data["total_tax"]
        nb = ctk.CTkFrame(self._area, fg_color="#0f3460", corner_radius=8)
        nb.pack(fill="x", padx=20, pady=(0, 12))
        ctk.CTkLabel(nb, text="NET GST COLLECTED",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#2ecc71").pack(side="left", padx=16, pady=10)
        ctk.CTkLabel(nb, text=f"₹ {net:,.2f}",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#2ecc71").pack(side="right", padx=16, pady=10)

        # ── Tax Rate-wise Breakdown ───────────────────────────────────────────
        sec1 = ctk.CTkFrame(self._area, fg_color="#16213e", corner_radius=6)
        sec1.pack(fill="x", padx=20, pady=(0, 8))
        ctk.CTkLabel(sec1, text="TAX RATE-WISE BREAKDOWN",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#3498db").pack(anchor="w", padx=12, pady=(8, 4))

        hdr_r = ctk.CTkFrame(sec1, fg_color="#0f3460", corner_radius=0)
        hdr_r.pack(fill="x", padx=8)
        for txt, w, anch in [("GST Rate",80,"w"),("Invoices",80,"e"),
                              ("Taxable ₹",120,"e"),("CGST ₹",100,"e"),
                              ("SGST ₹",100,"e"),("IGST ₹",100,"e"),("Total Tax ₹",110,"e")]:
            ctk.CTkLabel(hdr_r, text=txt, width=w, anchor=anch,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#95a5a6").pack(side="left", padx=6, pady=5)

        if not data["rate_rows"]:
            ctk.CTkLabel(sec1, text="  No invoice data for this period.",
                         text_color="#555").pack(pady=8)
        else:
            for i, r in enumerate(data["rate_rows"]):
                bg = "#1a1a2e" if i % 2 == 0 else "#16213e"
                rw = ctk.CTkFrame(sec1, fg_color=bg, corner_radius=0)
                rw.pack(fill="x", padx=8)
                rate_lbl = f"{r['gst_rate']:.0f}%" if r["gst_rate"] == int(r["gst_rate"]) else f"{r['gst_rate']}%"
                for txt, w, anch, clr in [
                    (rate_lbl,                     80,"w","#3498db"),
                    (str(r["invoice_count"]),       80,"e","#ecf0f1"),
                    (f"{r['taxable_value']:,.2f}",  120,"e","#ecf0f1"),
                    (f"{r['cgst']:,.2f}",           100,"e","#f39c12"),
                    (f"{r['sgst']:,.2f}",           100,"e","#f39c12"),
                    (f"{r['igst']:,.2f}",           100,"e","#9b59b6"),
                    (f"{r['total_tax']:,.2f}",      110,"e","#2ecc71"),
                ]:
                    ctk.CTkLabel(rw, text=txt, width=w, anchor=anch,
                                 font=ctk.CTkFont(size=11), text_color=clr
                                 ).pack(side="left", padx=6, pady=5)

        # ── Tax Mix Bar ───────────────────────────────────────────────────────
        if data["total_tax"] > 0:
            mix = ctk.CTkFrame(self._area, fg_color="#16213e", corner_radius=6)
            mix.pack(fill="x", padx=20, pady=(0, 8))
            ctk.CTkLabel(mix, text="TAX COMPOSITION (CGST / SGST / IGST)",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#3498db").pack(anchor="w", padx=12, pady=(8, 4))
            canvas_w, bar_h = 540, 24
            cv = tk.Canvas(mix, width=canvas_w, height=bar_h * 3 + 36,
                           bg="#16213e", highlightthickness=0)
            cv.pack(padx=12, pady=(0, 10))
            max_tax = max(data["cgst"], data["sgst"], data["igst"]) or 1
            bar_max_w = canvas_w - 110 - 12
            for idx, (label, val, color) in enumerate([
                ("CGST", data["cgst"], "#f39c12"),
                ("SGST", data["sgst"], "#e67e22"),
                ("IGST", data["igst"], "#9b59b6"),
            ]):
                y = 8 + idx * (bar_h + 10)
                fill_w = int(val / max_tax * bar_max_w)
                cv.create_text(100, y + bar_h // 2, text=label,
                               fill="#bdc3c7", font=("Helvetica", 9), anchor="e")
                cv.create_rectangle(104, y, 104 + bar_max_w, y + bar_h,
                                     fill="#0f1b2d", outline="")
                if fill_w > 0:
                    cv.create_rectangle(104, y, 104 + fill_w, y + bar_h,
                                         fill=color, outline="")
                cv.create_text(104 + bar_max_w + 8, y + bar_h // 2,
                               text=f"₹ {val:,.0f}", fill=color,
                               font=("Helvetica", 9, "bold"), anchor="w")

        # ── Monthly GST Trend ─────────────────────────────────────────────────
        if len(data["monthly"]) > 1:
            sec2 = ctk.CTkFrame(self._area, fg_color="#16213e", corner_radius=6)
            sec2.pack(fill="x", padx=20, pady=(0, 8))
            ctk.CTkLabel(sec2, text="MONTHLY GST TREND",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#3498db").pack(anchor="w", padx=12, pady=(8, 4))
            mhdr = ctk.CTkFrame(sec2, fg_color="#0f3460", corner_radius=0)
            mhdr.pack(fill="x", padx=8)
            for txt, w, anch in [("Month",100,"w"),("Invoices",80,"e"),
                                   ("Taxable ₹",120,"e"),("Tax ₹",100,"e"),("Total ₹",110,"e")]:
                ctk.CTkLabel(mhdr, text=txt, width=w, anchor=anch,
                             font=ctk.CTkFont(size=10, weight="bold"),
                             text_color="#95a5a6").pack(side="left", padx=6, pady=5)
            for i, r in enumerate(data["monthly"]):
                bg = "#1a1a2e" if i % 2 == 0 else "#16213e"
                tax = r["cgst"] + r["sgst"] + r["igst"]
                rw = ctk.CTkFrame(sec2, fg_color=bg, corner_radius=0)
                rw.pack(fill="x", padx=8)
                for txt, w, anch, clr in [
                    (r["month"],                100,"w","#ecf0f1"),
                    (str(r["invoice_count"]),    80,"e","#3498db"),
                    (f"{r['taxable_value']:,.0f}",120,"e","#ecf0f1"),
                    (f"{tax:,.0f}",             100,"e","#f39c12"),
                    (f"{r['grand_total']:,.0f}", 110,"e","#2ecc71"),
                ]:
                    ctk.CTkLabel(rw, text=txt, width=w, anchor=anch,
                                 font=ctk.CTkFont(size=11), text_color=clr
                                 ).pack(side="left", padx=6, pady=5)

    # ── GSTR-3B ───────────────────────────────────────────────────────────────

    def _render_gstr3b(self, data, from_d, to_d):
        firm = db.get_firm_settings()
        firm_name = (firm["firm_name"] if firm and firm["firm_name"] else "")
        ctk.CTkLabel(self._area, text="GSTR-3B  MONTHLY SUMMARY RETURN",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#ecf0f1").pack(pady=(12, 2))
        ctk.CTkLabel(self._area, text=f"Period: {from_d}  to  {to_d}",
                     text_color="#95a5a6", font=ctk.CTkFont(size=11)).pack()
        if firm_name:
            ctk.CTkLabel(self._area, text=firm_name,
                         text_color="#3498db", font=ctk.CTkFont(size=11)).pack()

        def sec_hdr(text):
            f = ctk.CTkFrame(self._area, fg_color="#16213e", corner_radius=6)
            f.pack(fill="x", padx=20, pady=(12, 4))
            ctk.CTkLabel(f, text=text,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#3498db").pack(anchor="w", padx=12, pady=6)

        def drow(label, value, bold=False, bg="#1a1a2e", val_color="#2ecc71"):
            row = ctk.CTkFrame(self._area, fg_color=bg, corner_radius=0)
            row.pack(fill="x", padx=20, pady=1)
            ctk.CTkLabel(row, text=label,
                         font=ctk.CTkFont(size=11, weight="bold" if bold else "normal"),
                         text_color="#ecf0f1", anchor="w"
                         ).pack(side="left", padx=12, pady=7, fill="x", expand=True)
            ctk.CTkLabel(row, text=f"₹ {value:,.2f}",
                         font=ctk.CTkFont(size=11, weight="bold" if bold else "normal"),
                         text_color=val_color, anchor="e", width=150
                         ).pack(side="right", padx=12)

        sec_hdr("3.1  Details of Outward Supplies")
        drow("(a)  Outward taxable supplies – Taxable Value",
             data["taxable_value"])
        drow("     CGST",         data["cgst_out"],  val_color="#f39c12")
        drow("     SGST / UTGST", data["sgst_out"],  val_color="#f39c12",
             bg="#16213e")
        drow("     IGST",         data["igst_out"],  val_color="#f39c12")
        drow("Total Output Tax Liability", data["total_out"],
             bold=True, bg="#0f3460", val_color="#2ecc71")

        sec_hdr("4.  Eligible Input Tax Credit (ITC)")
        drow("     CGST ITC",         data["cgst_itc"], val_color="#95a5a6")
        drow("     SGST / UTGST ITC", data["sgst_itc"], val_color="#95a5a6",
             bg="#16213e")
        drow("     IGST ITC",         data["igst_itc"], val_color="#95a5a6")
        note = ctk.CTkFrame(self._area, fg_color="#2c2c1a", corner_radius=4)
        note.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(note,
                     text="⚠  Purchase invoices are not tracked — ITC is ₹ 0.00",
                     font=ctk.CTkFont(size=10), text_color="#f39c12"
                     ).pack(anchor="w", padx=12, pady=6)
        drow("Total ITC Available", data["total_itc"],
             bold=True, bg="#0f3460", val_color="#95a5a6")

        ctk.CTkFrame(self._area, fg_color="#2c3e50", height=1
                     ).pack(fill="x", padx=20, pady=12)
        net_color = "#2ecc71" if data["net_total"] >= 0 else "#e74c3c"
        drow("NET GST PAYABLE", data["net_total"],
             bold=True, bg="#1a3a5c", val_color=net_color)

    # ── Exports ───────────────────────────────────────────────────────────────

    def _export_pdf(self):
        firm = (db.get_firm_settings() or {}).get("firm_name", "")
        if self._active_tab == "gstr1":
            if not self._last_data_gstr1:
                messagebox.showinfo("Export", "Generate GSTR-1 first."); return
            _run_export(rex.export_gstr1_pdf, "GSTR1.pdf",
                        self._last_data_gstr1, self._last_from, self._last_to, firm)
        else:
            if not self._last_data_gstr3b:
                messagebox.showinfo("Export", "Generate GSTR-3B first."); return
            _run_export(rex.export_gstr3b_pdf, "GSTR3B.pdf",
                        self._last_data_gstr3b, self._last_from, self._last_to, firm)

    def _export_excel(self):
        firm = (db.get_firm_settings() or {}).get("firm_name", "")
        if self._active_tab == "gstr1":
            if not self._last_data_gstr1:
                messagebox.showinfo("Export", "Generate GSTR-1 first."); return
            _run_export(rex.export_gstr1_excel, "GSTR1.xlsx",
                        self._last_data_gstr1, self._last_from, self._last_to, firm)
        else:
            if not self._last_data_gstr3b:
                messagebox.showinfo("Export", "Generate GSTR-3B first."); return
            _run_export(rex.export_gstr3b_excel, "GSTR3B.xlsx",
                        self._last_data_gstr3b, self._last_from, self._last_to, firm)

    def _export_csv(self):
        if self._active_tab == "gstr1":
            if not self._last_data_gstr1:
                messagebox.showinfo("Export", "Generate GSTR-1 first."); return
            _run_export(rex.export_gstr1_csv, "GSTR1.csv",
                        self._last_data_gstr1, self._last_from, self._last_to)
        else:
            if not self._last_data_gstr3b:
                messagebox.showinfo("Export", "Generate GSTR-3B first."); return
            _run_export(rex.export_gstr3b_csv, "GSTR3B.csv",
                        self._last_data_gstr3b, self._last_from, self._last_to)

    def _show_ai_insights(self):
        d1  = self._last_data_gstr1
        d3b = self._last_data_gstr3b
        if not d1 and not d3b:
            messagebox.showinfo("AI Insights", "Generate a GST report first.")
            return
        from_d, to_d = self._last_from, self._last_to
        parts = [f"You are a GST compliance advisor for an Indian business.\n\nPeriod: {from_d} to {to_d}\n"]
        if d1:
            parts.append(
                f"\nGSTR-1 (Outward Supplies):\n"
                f"  Invoices: {d1.get('total_invoices', 0)}\n"
                f"  Taxable Value: ₹{d1.get('total_taxable', 0):,.0f}\n"
                f"  Total Tax Collected: ₹{d1.get('total_tax', 0):,.0f}\n"
            )
        if d3b:
            parts.append(
                f"\nGSTR-3B Summary:\n"
                f"  Total Tax Payable: ₹{d3b.get('total_tax', 0):,.0f}\n"
                f"  CGST: ₹{d3b.get('cgst', 0):,.0f}\n"
                f"  SGST: ₹{d3b.get('sgst', 0):,.0f}\n"
                f"  IGST: ₹{d3b.get('igst', 0):,.0f}\n"
            )
        parts.append(
            "\nProvide 4 GST compliance insights numbered 1–4: "
            "tax liability, filing readiness, ITC observations, and compliance recommendations."
        )
        AIInsightsDialog(self, "GST Reports", "".join(parts))


class BankEntryDialog(ctk.CTkToplevel):
    """Dialog to manually add a single bank statement line."""

    def __init__(self, parent, account_id, on_saved):
        super().__init__(parent)
        self.account_id = account_id
        self.on_saved   = on_saved
        self.title("Add Bank Statement Entry")
        self.geometry("400x340")
        self.grab_set()
        self.resizable(False, False)
        ctk.CTkLabel(self, text="Add Bank Statement Entry",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(14, 6), padx=20, anchor="w")
        self._build()

    def _field(self, label, default="", width=340):
        ctk.CTkLabel(self, text=label, text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=20, pady=(6, 0))
        var = ctk.StringVar(value=default)
        ctk.CTkEntry(self, textvariable=var, width=width).pack(padx=20, pady=(2, 0))
        return var

    def _build(self):
        today = datetime.today().strftime("%Y-%m-%d")
        self._date = self._field("Date (YYYY-MM-DD) *", today)
        self._desc = self._field("Description")
        self._dr   = self._field("Debit (withdrawal)", "0")
        self._cr   = self._field("Credit (deposit)",   "0")
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.pack(pady=14, padx=20, fill="x")
        ctk.CTkButton(f, text="Save", fg_color="#2ecc71", hover_color="#27ae60",
                      text_color="#000", command=self._save).pack(side="right")
        ctk.CTkButton(f, text="Cancel", fg_color="#7f1f1f", hover_color="#c0392b",
                      command=self.destroy).pack(side="right", padx=8)

    def _save(self):
        d = self._date.get().strip()
        try:
            datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Error", "Date must be YYYY-MM-DD.", parent=self); return
        try:
            dr = float(self._dr.get().strip() or 0)
            cr = float(self._cr.get().strip() or 0)
        except ValueError:
            messagebox.showerror("Error", "Debit/Credit must be numbers.", parent=self); return
        db.add_bank_statement_line(self.account_id, d, self._desc.get().strip(), dr, cr)
        self.on_saved()
        self.destroy()


class BankReconciliationPage(BasePage):
    """Side-by-side bank statement vs ledger reconciliation view."""

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._selected_bank_id = None
        self._selected_je_id   = None
        self._bank_rows        = []
        self._je_rows          = []
        self._filter_var       = ctk.StringVar(value="all")

        # ── header ────────────────────────────────────────────────────────────
        self._header("Bank Reconciliation", "Match bank statement entries with ledger journal entries")

        # ── control bar ───────────────────────────────────────────────────────
        ctrl = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=6)
        ctrl.pack(fill="x", padx=24, pady=(0, 8))

        ctk.CTkLabel(ctrl, text="Account:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(12, 4), pady=8)

        accounts = db.get_bank_accounts()
        self._account_map = {f"{a['code']} – {a['name']}": a["id"] for a in accounts}
        acct_names = list(self._account_map.keys())
        default_acct = next((n for n in acct_names if "bank" in n.lower() or "1003" in n), acct_names[0] if acct_names else "")
        self._acct_var = ctk.StringVar(value=default_acct)
        ctk.CTkComboBox(ctrl, values=acct_names, variable=self._acct_var,
                        width=200, font=ctk.CTkFont(size=11)).pack(side="left", padx=4, pady=8)

        ctk.CTkLabel(ctrl, text="From:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(12, 4))
        import datetime as _dt
        today   = _dt.date.today()
        from_d  = today.replace(day=1).strftime("%Y-%m-%d")
        to_d    = today.strftime("%Y-%m-%d")
        self._from_var = ctk.StringVar(value=from_d)
        self._to_var   = ctk.StringVar(value=to_d)
        ctk.CTkEntry(ctrl, textvariable=self._from_var, width=100).pack(side="left", padx=2)
        ctk.CTkLabel(ctrl, text="To:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(8, 4))
        ctk.CTkEntry(ctrl, textvariable=self._to_var, width=100).pack(side="left", padx=2)

        ctk.CTkButton(ctrl, text="Load", width=70, fg_color="#2980b9",
                      hover_color="#3498db", command=self._load).pack(side="left", padx=(12, 4))
        ctk.CTkButton(ctrl, text="📥 Import CSV", width=110, fg_color="#1a3a2a",
                      hover_color="#27ae60", command=self._import_csv).pack(side="left", padx=2)
        ctk.CTkButton(ctrl, text="➕ Add Entry", width=100, fg_color="#1a3a5c",
                      hover_color="#2980b9", command=self._add_entry).pack(side="left", padx=2)

        # filter
        ctk.CTkFrame(ctrl, fg_color="#2c3e50", width=1, height=28).pack(side="left", padx=10, pady=6, fill="y")
        ctk.CTkLabel(ctrl, text="Show:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        for lbl, val in [("All", "all"), ("Unmatched", "unmatched"), ("Matched", "matched")]:
            ctk.CTkRadioButton(ctrl, text=lbl, variable=self._filter_var, value=val,
                               font=ctk.CTkFont(size=11),
                               command=self._refresh_panels).pack(side="left", padx=4)

        # ── action bar ────────────────────────────────────────────────────────
        act = ctk.CTkFrame(self, fg_color="#0d1117", corner_radius=6)
        act.pack(fill="x", padx=24, pady=(0, 6))

        self._match_btn = ctk.CTkButton(act, text="✅ Match Selected", width=140,
                                        fg_color="#145a32", hover_color="#1e8449",
                                        state="disabled", command=self._match_selected)
        self._match_btn.pack(side="left", padx=(12, 4), pady=6)
        ctk.CTkButton(act, text="⚡ Auto-Match", width=120,
                      fg_color="#1a3a5c", hover_color="#2980b9",
                      command=self._auto_match).pack(side="left", padx=2)
        ctk.CTkButton(act, text="Unmatch Selected", width=140,
                      fg_color="#4a1a1a", hover_color="#922b21",
                      command=self._unmatch_selected).pack(side="left", padx=2)

        # export buttons
        ctk.CTkFrame(act, fg_color="#2c3e50", width=1, height=28).pack(side="left", padx=10, pady=4, fill="y")
        ctk.CTkLabel(act, text="Export:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 3))
        for lbl, cmd, fg, hov in [
            ("📄 PDF",   self._export_pdf,   "#1a3a5c", "#2980b9"),
            ("📊 Excel", self._export_excel, "#1a3a2a", "#27ae60"),
            ("CSV",      self._export_csv,   "#2c3e50", "#34495e"),
        ]:
            ctk.CTkButton(act, text=lbl, width=70, font=ctk.CTkFont(size=11),
                          fg_color=fg, hover_color=hov, command=cmd).pack(side="left", padx=2)

        # ── two-panel main area ────────────────────────────────────────────────
        self._main = ctk.CTkFrame(self, fg_color="transparent")
        self._main.pack(fill="both", expand=True, padx=24, pady=(0, 6))
        self._main.columnconfigure(0, weight=1)
        self._main.columnconfigure(1, weight=1)
        self._main.rowconfigure(0, weight=1)

        # Bank panel
        self._bank_outer = ctk.CTkFrame(self._main, fg_color="#16213e", corner_radius=8)
        self._bank_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        # Ledger panel
        self._je_outer = ctk.CTkFrame(self._main, fg_color="#16213e", corner_radius=8)
        self._je_outer.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        # ── summary bar ───────────────────────────────────────────────────────
        self._summary_frame = ctk.CTkFrame(self, fg_color="#0d1117", corner_radius=6)
        self._summary_frame.pack(fill="x", padx=24, pady=(0, 10))
        self._summary_lbl = ctk.CTkLabel(self._summary_frame,
                                          text="Load data to see reconciliation summary.",
                                          text_color="#7f8c8d", font=ctk.CTkFont(size=11))
        self._summary_lbl.pack(padx=16, pady=6)

        self._load()

    # ── data loading ──────────────────────────────────────────────────────────

    def _get_account_id(self):
        return self._account_map.get(self._acct_var.get())

    def _load(self):
        acct_id = self._get_account_id()
        if not acct_id:
            return
        from_d = self._from_var.get().strip()
        to_d   = self._to_var.get().strip()
        self._bank_rows = db.get_bank_statement_lines(acct_id, from_d, to_d)
        self._je_rows   = db.get_ledger_entries_for_recon(acct_id, from_d, to_d)
        self._selected_bank_id = None
        self._selected_je_id   = None
        self._refresh_panels()
        self._update_summary()

    def _refresh_panels(self):
        self._render_bank_panel()
        self._render_je_panel()
        self._update_match_btn()

    # ── bank panel ────────────────────────────────────────────────────────────

    def _render_bank_panel(self):
        for w in self._bank_outer.winfo_children():
            w.destroy()

        hdr = ctk.CTkFrame(self._bank_outer, fg_color="#0d1b2a", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="  BANK STATEMENT",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#3498db").pack(side="left", padx=8, pady=6)
        total = len(self._bank_rows)
        matched = sum(1 for r in self._bank_rows if r["is_matched"])
        ctk.CTkLabel(hdr, text=f"{matched}/{total} matched",
                     font=ctk.CTkFont(size=10), text_color="#7f8c8d").pack(side="right", padx=8)

        col_hdr = ctk.CTkFrame(self._bank_outer, fg_color="#1a2a3a", corner_radius=0)
        col_hdr.pack(fill="x")
        for txt, w in [("Date", 90), ("Description", 180), ("Debit", 70), ("Credit", 70), ("", 54)]:
            ctk.CTkLabel(col_hdr, text=txt, width=w, anchor="w",
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#95a5a6").pack(side="left", padx=(4, 0), pady=3)

        scroll = ctk.CTkScrollableFrame(self._bank_outer, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        filt = self._filter_var.get()
        rows = [r for r in self._bank_rows
                if filt == "all"
                or (filt == "matched"   and r["is_matched"])
                or (filt == "unmatched" and not r["is_matched"])]

        if not rows:
            ctk.CTkLabel(scroll, text="No entries found.",
                         text_color="#555").pack(pady=20)
            return

        for i, row in enumerate(rows):
            is_sel  = row["id"] == self._selected_bank_id
            matched = bool(row["is_matched"])
            bg = "#1b4332" if matched else ("#1a3a5c" if is_sel else ("#1a1a2e" if i % 2 == 0 else "#16213e"))
            fr = ctk.CTkFrame(scroll, fg_color=bg, corner_radius=0)
            fr.pack(fill="x")

            ctk.CTkLabel(fr, text=row["txn_date"], width=90, anchor="w",
                         font=ctk.CTkFont(size=10)).pack(side="left", padx=(4, 0))
            desc = (row["description"] or "")[:22]
            ctk.CTkLabel(fr, text=desc, width=180, anchor="w",
                         font=ctk.CTkFont(size=10)).pack(side="left", padx=(2, 0))
            ctk.CTkLabel(fr, text=f"{row['debit']:,.0f}" if row["debit"] else "",
                         width=70, anchor="e", font=ctk.CTkFont(size=10),
                         text_color="#e74c3c").pack(side="left", padx=(2, 0))
            ctk.CTkLabel(fr, text=f"{row['credit']:,.0f}" if row["credit"] else "",
                         width=70, anchor="e", font=ctk.CTkFont(size=10),
                         text_color="#2ecc71").pack(side="left", padx=(2, 0))

            rid = row["id"]
            if matched:
                ctk.CTkButton(fr, text="✓", width=48, height=20, fg_color="#145a32",
                              hover_color="#1e8449", font=ctk.CTkFont(size=10),
                              command=lambda x=rid: self._toggle_bank(x)).pack(side="left", padx=2, pady=2)
            else:
                sel_text = "●" if is_sel else "○"
                ctk.CTkButton(fr, text=sel_text, width=48, height=20,
                              fg_color="#1a3a5c" if is_sel else "#2c3e50",
                              hover_color="#2980b9", font=ctk.CTkFont(size=10),
                              command=lambda x=rid: self._toggle_bank(x)).pack(side="left", padx=2, pady=2)

    # ── ledger panel ──────────────────────────────────────────────────────────

    def _render_je_panel(self):
        for w in self._je_outer.winfo_children():
            w.destroy()

        hdr = ctk.CTkFrame(self._je_outer, fg_color="#0d1b2a", corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="  LEDGER ENTRIES",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#f39c12").pack(side="left", padx=8, pady=6)
        total   = len(self._je_rows)
        matched = sum(1 for r in self._je_rows if r["is_matched"])
        ctk.CTkLabel(hdr, text=f"{matched}/{total} matched",
                     font=ctk.CTkFont(size=10), text_color="#7f8c8d").pack(side="right", padx=8)

        col_hdr = ctk.CTkFrame(self._je_outer, fg_color="#1a2a3a", corner_radius=0)
        col_hdr.pack(fill="x")
        for txt, w in [("Date", 90), ("Narration", 190), ("Amount", 90), ("", 54)]:
            ctk.CTkLabel(col_hdr, text=txt, width=w, anchor="w",
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#95a5a6").pack(side="left", padx=(4, 0), pady=3)

        scroll = ctk.CTkScrollableFrame(self._je_outer, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        filt = self._filter_var.get()
        rows = [r for r in self._je_rows
                if filt == "all"
                or (filt == "matched"   and r["is_matched"])
                or (filt == "unmatched" and not r["is_matched"])]

        if not rows:
            ctk.CTkLabel(scroll, text="No entries found.",
                         text_color="#555").pack(pady=20)
            return

        for i, row in enumerate(rows):
            is_sel  = row["id"] == self._selected_je_id
            matched = bool(row["is_matched"])
            bg = "#1b4332" if matched else ("#1a3a5c" if is_sel else ("#1a1a2e" if i % 2 == 0 else "#16213e"))
            fr = ctk.CTkFrame(scroll, fg_color=bg, corner_radius=0)
            fr.pack(fill="x")

            ctk.CTkLabel(fr, text=row["entry_date"], width=90, anchor="w",
                         font=ctk.CTkFont(size=10)).pack(side="left", padx=(4, 0))
            narr = (row["narration"] or "")[:26]
            ctk.CTkLabel(fr, text=narr, width=190, anchor="w",
                         font=ctk.CTkFont(size=10)).pack(side="left", padx=(2, 0))
            net_dr = row["net_dr"] or 0
            color  = "#2ecc71" if net_dr > 0 else "#e74c3c"
            ctk.CTkLabel(fr, text=f"{abs(net_dr):,.0f}", width=90, anchor="e",
                         font=ctk.CTkFont(size=10), text_color=color).pack(side="left", padx=(2, 0))

            jid = row["id"]
            if matched:
                ctk.CTkButton(fr, text="✓", width=48, height=20, fg_color="#145a32",
                              hover_color="#1e8449", font=ctk.CTkFont(size=10),
                              command=lambda x=jid: self._toggle_je(x)).pack(side="left", padx=2, pady=2)
            else:
                sel_text = "●" if is_sel else "○"
                ctk.CTkButton(fr, text=sel_text, width=48, height=20,
                              fg_color="#1a3a5c" if is_sel else "#2c3e50",
                              hover_color="#f39c12", font=ctk.CTkFont(size=10),
                              command=lambda x=jid: self._toggle_je(x)).pack(side="left", padx=2, pady=2)

    # ── selection & matching ──────────────────────────────────────────────────

    def _toggle_bank(self, row_id):
        self._selected_bank_id = None if self._selected_bank_id == row_id else row_id
        self._refresh_panels()

    def _toggle_je(self, row_id):
        self._selected_je_id = None if self._selected_je_id == row_id else row_id
        self._refresh_panels()

    def _update_match_btn(self):
        can = self._selected_bank_id is not None and self._selected_je_id is not None
        self._match_btn.configure(state="normal" if can else "disabled")

    def _match_selected(self):
        if not self._selected_bank_id or not self._selected_je_id:
            return
        db.match_bank_line(self._selected_bank_id, self._selected_je_id)
        self._selected_bank_id = None
        self._selected_je_id   = None
        self._load()

    def _unmatch_selected(self):
        if self._selected_bank_id:
            db.unmatch_bank_line(self._selected_bank_id)
            self._selected_bank_id = None
            self._load()
        elif self._selected_je_id:
            # find the bank line matched to this JE
            matched = [r for r in self._bank_rows if r.get("matched_je_id") == self._selected_je_id]
            for m in matched:
                db.unmatch_bank_line(m["id"])
            self._selected_je_id = None
            self._load()
        else:
            messagebox.showinfo("Unmatch", "Select a matched entry first.")

    def _auto_match(self):
        """Match by equal amount and same date (unmatched entries only)."""
        unmatched_bank = [r for r in self._bank_rows if not r["is_matched"]]
        unmatched_je   = [r for r in self._je_rows   if not r["is_matched"]]
        matched_count  = 0
        for b in unmatched_bank:
            b_amt = b["credit"] - b["debit"]
            for j in unmatched_je:
                if b["txn_date"] == j["entry_date"] and abs(b_amt - (j["net_dr"] or 0)) < 0.01:
                    db.match_bank_line(b["id"], j["id"])
                    unmatched_je.remove(j)
                    matched_count += 1
                    break
        if matched_count:
            messagebox.showinfo("Auto-Match", f"Matched {matched_count} pair(s).")
        else:
            messagebox.showinfo("Auto-Match", "No automatic matches found.\nCheck dates and amounts match exactly.")
        self._load()

    # ── import & add ──────────────────────────────────────────────────────────

    def _import_csv(self):
        acct_id = self._get_account_id()
        if not acct_id:
            messagebox.showerror("Error", "Select an account first."); return
        path = filedialog.askopenfilename(
            title="Select Bank Statement CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        count, errors = db.import_bank_csv(acct_id, path)
        msg = f"Imported {count} row(s)."
        if errors:
            msg += f"\n\nWarnings ({len(errors)}):\n" + "\n".join(errors[:10])
        messagebox.showinfo("Import CSV", msg)
        self._load()

    def _add_entry(self):
        acct_id = self._get_account_id()
        if not acct_id:
            messagebox.showerror("Error", "Select an account first."); return
        BankEntryDialog(self, acct_id, self._load)

    # ── summary ───────────────────────────────────────────────────────────────

    def _update_summary(self):
        acct_id = self._get_account_id()
        if not acct_id:
            return
        from_d = self._from_var.get().strip()
        to_d   = self._to_var.get().strip()
        s = db.get_reconciliation_summary(acct_id, from_d, to_d)
        diff    = s["difference"]
        ok      = abs(diff) < 0.01
        d_color = "#2ecc71" if ok else "#e74c3c"
        status  = "✅  Reconciled" if ok else "⚠  Difference"

        for w in self._summary_frame.winfo_children():
            w.destroy()
        row = ctk.CTkFrame(self._summary_frame, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=6)
        for label, val, color in [
            ("Bank Net",      f"₹{s['bank_net']:,.2f}",   "#3498db"),
            ("Ledger Net",    f"₹{s['ledger_net']:,.2f}", "#f39c12"),
            ("Difference",    f"₹{diff:,.2f}",             d_color),
            ("Bank Entries",  str(s["total_bank_lines"]),  "#ecf0f1"),
            ("Unmatched Bank",str(s["unmatched_bank"]),    "#e74c3c" if s["unmatched_bank"] else "#2ecc71"),
            ("Unmatched JE",  str(s["unmatched_je"]),      "#e74c3c" if s["unmatched_je"]   else "#2ecc71"),
            ("Status",        status,                       d_color),
        ]:
            tile = ctk.CTkFrame(row, fg_color="#16213e", corner_radius=6)
            tile.pack(side="left", padx=4, ipadx=8, ipady=4)
            ctk.CTkLabel(tile, text=label, font=ctk.CTkFont(size=9),
                         text_color="#7f8c8d").pack()
            ctk.CTkLabel(tile, text=val, font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=color).pack()

    # ── exports ───────────────────────────────────────────────────────────────

    def _export_pdf(self):
        acct_id = self._get_account_id()
        if not acct_id or not self._bank_rows:
            messagebox.showinfo("Export", "Load data first."); return
        acct_name = self._acct_var.get()
        firm = (db.get_firm_settings() or {}).get("firm_name", "")
        s = db.get_reconciliation_summary(acct_id, self._from_var.get(), self._to_var.get())
        data = {"bank": self._bank_rows, "je": self._je_rows, "summary": s}
        _run_export(rex.export_recon_pdf, "Bank_Reconciliation.pdf",
                    data, acct_name, self._from_var.get(), self._to_var.get(), firm)

    def _export_excel(self):
        acct_id = self._get_account_id()
        if not acct_id or not self._bank_rows:
            messagebox.showinfo("Export", "Load data first."); return
        acct_name = self._acct_var.get()
        firm = (db.get_firm_settings() or {}).get("firm_name", "")
        s = db.get_reconciliation_summary(acct_id, self._from_var.get(), self._to_var.get())
        data = {"bank": self._bank_rows, "je": self._je_rows, "summary": s}
        _run_export(rex.export_recon_excel, "Bank_Reconciliation.xlsx",
                    data, acct_name, self._from_var.get(), self._to_var.get(), firm)

    def _export_csv(self):
        acct_id = self._get_account_id()
        if not acct_id or not self._bank_rows:
            messagebox.showinfo("Export", "Load data first."); return
        acct_name = self._acct_var.get()
        s = db.get_reconciliation_summary(acct_id, self._from_var.get(), self._to_var.get())
        data = {"bank": self._bank_rows, "je": self._je_rows, "summary": s}
        _run_export(rex.export_recon_csv, "Bank_Reconciliation.csv",
                    data, acct_name, self._from_var.get(), self._to_var.get())


# ── Day Book / Cash Book Page ─────────────────────────────────────────────────

class DayBookPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._header("Day Book / Cash Book", "Complete daily transaction register")

        today = datetime.now()
        from_def = today.replace(day=1).strftime("%Y-%m-%d")
        to_def   = today.strftime("%Y-%m-%d")

        # ── Controls ──────────────────────────────────────────────────────────
        ctrl = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=10)
        ctrl.pack(fill="x", padx=24, pady=(0, 6))
        inner = ctk.CTkFrame(ctrl, fg_color="transparent")
        inner.pack(padx=16, pady=10, anchor="w")

        ctk.CTkLabel(inner, text="From:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self._from = ctk.CTkEntry(inner, width=120)
        self._from.insert(0, from_def)
        self._from.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(inner, text="To:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self._to = ctk.CTkEntry(inner, width=120)
        self._to.insert(0, to_def)
        self._to.pack(side="left", padx=(0, 16))

        ctk.CTkButton(inner, text="Generate", width=110, height=36,
                      fg_color="#e94560", hover_color="#c0392b",
                      command=self._generate).pack(side="left", padx=(0, 16))

        # Quick presets
        for label, cmd in [
            ("Today",        self._preset_today),
            ("This Week",    self._preset_week),
            ("This Month",   self._preset_month),
            ("Last Month",   self._preset_last_month),
        ]:
            ctk.CTkButton(inner, text=label, width=90, height=32,
                          fg_color="#2c3e50", hover_color="#3498db",
                          font=ctk.CTkFont(size=11),
                          command=cmd).pack(side="left", padx=3)

        # ── Tabs: Day Book | Cash | Bank ─────────────────────────────────────
        self._tabs = ctk.CTkTabview(self, fg_color="#16213e")
        self._tabs.pack(fill="both", expand=True, padx=24, pady=(0, 8))
        self._tabs.add("📒  Day Book")
        self._tabs.add("💵  Cash Book")
        self._tabs.add("🏦  Bank Book")

        self._db_frame   = self._tabs.tab("📒  Day Book")
        self._cash_frame = self._tabs.tab("💵  Cash Book")
        self._bank_frame = self._tabs.tab("🏦  Bank Book")

        self._generate()

    # ── Presets ───────────────────────────────────────────────────────────────

    def _set_range(self, from_d, to_d):
        self._from.delete(0, "end"); self._from.insert(0, from_d)
        self._to.delete(0, "end");   self._to.insert(0, to_d)
        self._generate()

    def _preset_today(self):
        d = datetime.now().strftime("%Y-%m-%d")
        self._set_range(d, d)

    def _preset_week(self):
        t = datetime.now()
        from_d = (t - timedelta(days=t.weekday())).strftime("%Y-%m-%d")
        self._set_range(from_d, t.strftime("%Y-%m-%d"))

    def _preset_month(self):
        t = datetime.now()
        self._set_range(t.replace(day=1).strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d"))

    def _preset_last_month(self):
        t = datetime.now().replace(day=1) - timedelta(days=1)
        self._set_range(t.replace(day=1).strftime("%Y-%m-%d"), t.strftime("%Y-%m-%d"))

    # ── Generate ──────────────────────────────────────────────────────────────

    def _generate(self):
        from_d = self._from.get().strip()
        to_d   = self._to.get().strip()
        if not from_d or not to_d:
            return
        try:
            datetime.strptime(from_d, "%Y-%m-%d")
            datetime.strptime(to_d,   "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Invalid Date", "Use YYYY-MM-DD format."); return

        self._build_day_book(from_d, to_d)
        self._build_cash_book(from_d, to_d, "1002", self._cash_frame, "Cash in Hand")
        self._build_cash_book(from_d, to_d, "1003", self._bank_frame, "Bank Account")

    # ── Day Book tab ──────────────────────────────────────────────────────────

    def _build_day_book(self, from_d, to_d):
        for w in self._db_frame.winfo_children():
            w.destroy()

        data = db.get_day_book(from_d, to_d)
        rows = data["rows"]

        # Export toolbar
        exp = ctk.CTkFrame(self._db_frame, fg_color="transparent")
        exp.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(exp,
                     text=f"{len(rows)} line(s)  |  Total Dr: ₹{data['total_dr']:,.2f}  |  Total Cr: ₹{data['total_cr']:,.2f}",
                     font=ctk.CTkFont(size=12), text_color="#bdc3c7").pack(side="left")
        ctk.CTkButton(exp, text="📊 Excel", width=80, height=28,
                      fg_color="#1a3a2a", hover_color="#27ae60",
                      font=ctk.CTkFont(size=11),
                      command=lambda: self._export_day_book_excel(data, from_d, to_d)
                      ).pack(side="right", padx=4)
        ctk.CTkButton(exp, text="CSV", width=60, height=28,
                      fg_color="#2c3e50", hover_color="#34495e",
                      font=ctk.CTkFont(size=11),
                      command=lambda: self._export_day_book_csv(data, from_d, to_d)
                      ).pack(side="right", padx=4)

        if not rows:
            ctk.CTkLabel(self._db_frame,
                         text="No transactions found for the selected period.",
                         text_color="#95a5a6", font=ctk.CTkFont(size=13),
                         ).pack(pady=40)
            return

        # Table header
        hdr = ctk.CTkFrame(self._db_frame, fg_color="#0f3460", corner_radius=6)
        hdr.pack(fill="x", padx=8, pady=(0, 2))
        for col, w, text, anchor in [
            (0, 90,  "Date",       "w"),
            (1, 200, "Narration",  "w"),
            (2, 90,  "Ref",        "w"),
            (3, 200, "Account",    "w"),
            (4, 110, "Debit (₹)",  "e"),
            (5, 110, "Credit (₹)", "e"),
        ]:
            ctk.CTkLabel(hdr, text=text, font=ctk.CTkFont(size=11, weight="bold"),
                         width=w, anchor=anchor).grid(row=0, column=col, padx=6, pady=6, sticky=anchor)

        scroll = ctk.CTkScrollableFrame(self._db_frame, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=8, pady=0)

        # Group rows by journal entry for visual clarity
        last_jid = None
        for i, r in enumerate(rows):
            is_new_entry = (r["journal_id"] != last_jid)
            last_jid = r["journal_id"]

            if is_new_entry and i > 0:
                # Thin separator between entries
                sep = ctk.CTkFrame(scroll, fg_color="#2c3e50", height=1)
                sep.pack(fill="x", pady=1)

            bg = "#16213e" if i % 2 == 0 else "#1a2744"
            row_f = ctk.CTkFrame(scroll, fg_color=bg, corner_radius=0)
            row_f.pack(fill="x")

            date_txt = r["entry_date"] if is_new_entry else ""
            narr_txt = r["narration"]  if is_new_entry else ""
            ref_txt  = (r["reference"] or "") if is_new_entry else ""

            dr_color = "#2ecc71" if r["debit"]  > 0 else "#555"
            cr_color = "#e74c3c" if r["credit"] > 0 else "#555"

            for col, w, text, anchor, color in [
                (0, 90,  date_txt,                             "w", "#bdc3c7"),
                (1, 200, narr_txt,                             "w", "#ecf0f1"),
                (2, 90,  ref_txt,                              "w", "#7f8c8d"),
                (3, 200, r["account_name"],                    "w", "#3498db"),
                (4, 110, f"₹{r['debit']:,.2f}"  if r["debit"]  > 0 else "—", "e", dr_color),
                (5, 110, f"₹{r['credit']:,.2f}" if r["credit"] > 0 else "—", "e", cr_color),
            ]:
                ctk.CTkLabel(row_f, text=text, width=w, anchor=anchor,
                             font=ctk.CTkFont(size=11), text_color=color,
                             ).grid(row=0, column=col, padx=6, pady=4, sticky=anchor)

        # Totals footer
        foot = ctk.CTkFrame(self._db_frame, fg_color="#0f3460", corner_radius=6)
        foot.pack(fill="x", padx=8, pady=(4, 4))
        ctk.CTkLabel(foot, text="TOTAL", font=ctk.CTkFont(size=12, weight="bold"),
                     width=580, anchor="e").grid(row=0, column=0, padx=6, pady=6)
        ctk.CTkLabel(foot, text=f"₹{data['total_dr']:,.2f}",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#2ecc71", width=110, anchor="e",
                     ).grid(row=0, column=1, padx=6, pady=6)
        ctk.CTkLabel(foot, text=f"₹{data['total_cr']:,.2f}",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#e74c3c", width=110, anchor="e",
                     ).grid(row=0, column=2, padx=6, pady=6)

    # ── Cash / Bank Book tab ──────────────────────────────────────────────────

    def _build_cash_book(self, from_d, to_d, acct_code, frame, acct_label):
        for w in frame.winfo_children():
            w.destroy()

        data = db.get_cash_book(from_d, to_d, acct_code)

        # Summary strip
        summ = ctk.CTkFrame(frame, fg_color="#16213e", corner_radius=8)
        summ.pack(fill="x", padx=8, pady=(8, 6))
        for label, val, color in [
            ("Opening Balance", f"₹{data['opening']:,.2f}", "#f39c12"),
            ("Total Receipts",  f"₹{data['total_dr']:,.2f}", "#2ecc71"),
            ("Total Payments",  f"₹{data['total_cr']:,.2f}", "#e74c3c"),
            ("Closing Balance", f"₹{data['closing']:,.2f}", "#3498db"),
        ]:
            tile = ctk.CTkFrame(summ, fg_color="#0d1117", corner_radius=6)
            tile.pack(side="left", padx=6, pady=8, ipadx=10, ipady=4)
            ctk.CTkLabel(tile, text=label, font=ctk.CTkFont(size=9),
                         text_color="#7f8c8d").pack()
            ctk.CTkLabel(tile, text=val, font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=color).pack()

        # Export button
        exp = ctk.CTkFrame(frame, fg_color="transparent")
        exp.pack(fill="x", padx=8, pady=(0, 4))
        ctk.CTkButton(exp, text="📊 Excel", width=80, height=28,
                      fg_color="#1a3a2a", hover_color="#27ae60",
                      font=ctk.CTkFont(size=11),
                      command=lambda: self._export_cash_book_excel(data, from_d, to_d, acct_label)
                      ).pack(side="right", padx=4)
        ctk.CTkButton(exp, text="CSV", width=60, height=28,
                      fg_color="#2c3e50", hover_color="#34495e",
                      font=ctk.CTkFont(size=11),
                      command=lambda: self._export_cash_book_csv(data, from_d, to_d, acct_label)
                      ).pack(side="right", padx=4)

        rows = data["rows"]
        if not rows:
            ctk.CTkLabel(frame,
                         text=f"No {acct_label} transactions found for this period.",
                         text_color="#95a5a6", font=ctk.CTkFont(size=13),
                         ).pack(pady=30)
            return

        # Header
        hdr = ctk.CTkFrame(frame, fg_color="#0f3460", corner_radius=6)
        hdr.pack(fill="x", padx=8, pady=(0, 2))
        for col, w, text, anchor in [
            (0, 100, "Date",           "w"),
            (1, 280, "Narration",      "w"),
            (2, 100, "Ref",            "w"),
            (3, 120, "Receipts (₹)",  "e"),
            (4, 120, "Payments (₹)",  "e"),
            (5, 120, "Balance (₹)",   "e"),
        ]:
            ctk.CTkLabel(hdr, text=text, font=ctk.CTkFont(size=11, weight="bold"),
                         width=w, anchor=anchor).grid(row=0, column=col, padx=6, pady=6, sticky=anchor)

        scroll = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=8)

        # Opening balance row
        ob_row = ctk.CTkFrame(scroll, fg_color="#1a3a5c", corner_radius=4)
        ob_row.pack(fill="x", pady=1)
        ctk.CTkLabel(ob_row, text=from_d, width=100, anchor="w",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color="#f39c12",
                     ).grid(row=0, column=0, padx=6, pady=5, sticky="w")
        ctk.CTkLabel(ob_row, text="Opening Balance", width=280, anchor="w",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color="#f39c12",
                     ).grid(row=0, column=1, padx=6, pady=5, sticky="w")
        ctk.CTkLabel(ob_row, text="", width=100).grid(row=0, column=2, padx=6, pady=5)
        ctk.CTkLabel(ob_row, text="", width=120).grid(row=0, column=3, padx=6, pady=5)
        ctk.CTkLabel(ob_row, text="", width=120).grid(row=0, column=4, padx=6, pady=5)
        ctk.CTkLabel(ob_row, text=f"₹{data['opening']:,.2f}", width=120, anchor="e",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color="#f39c12",
                     ).grid(row=0, column=5, padx=6, pady=5, sticky="e")

        for i, r in enumerate(rows):
            bg = "#16213e" if i % 2 == 0 else "#1a2744"
            row_f = ctk.CTkFrame(scroll, fg_color=bg, corner_radius=0)
            row_f.pack(fill="x")
            bal_color = "#2ecc71" if r["balance"] >= 0 else "#e74c3c"

            for col, w, text, anchor, color in [
                (0, 100, r["entry_date"],                                        "w", "#bdc3c7"),
                (1, 280, r["narration"],                                         "w", "#ecf0f1"),
                (2, 100, r.get("reference", "") or "",                           "w", "#7f8c8d"),
                (3, 120, f"₹{r['debit']:,.2f}"   if r["debit"]  > 0 else "—",  "e", "#2ecc71"),
                (4, 120, f"₹{r['credit']:,.2f}"  if r["credit"] > 0 else "—",  "e", "#e74c3c"),
                (5, 120, f"₹{r['balance']:,.2f}",                               "e", bal_color),
            ]:
                ctk.CTkLabel(row_f, text=text, width=w, anchor=anchor,
                             font=ctk.CTkFont(size=11), text_color=color,
                             ).grid(row=0, column=col, padx=6, pady=4, sticky=anchor)

        # Closing balance row
        cl_color = "#3498db" if data["closing"] >= 0 else "#e74c3c"
        cl_row = ctk.CTkFrame(scroll, fg_color="#0f3460", corner_radius=4)
        cl_row.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(cl_row, text=to_d, width=100, anchor="w",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color=cl_color,
                     ).grid(row=0, column=0, padx=6, pady=6, sticky="w")
        ctk.CTkLabel(cl_row, text="Closing Balance", width=280, anchor="w",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color=cl_color,
                     ).grid(row=0, column=1, padx=6, pady=6, sticky="w")
        ctk.CTkLabel(cl_row, text="", width=100).grid(row=0, column=2)
        ctk.CTkLabel(cl_row, text=f"₹{data['total_dr']:,.2f}", width=120, anchor="e",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color="#2ecc71",
                     ).grid(row=0, column=3, padx=6, pady=6, sticky="e")
        ctk.CTkLabel(cl_row, text=f"₹{data['total_cr']:,.2f}", width=120, anchor="e",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color="#e74c3c",
                     ).grid(row=0, column=4, padx=6, pady=6, sticky="e")
        ctk.CTkLabel(cl_row, text=f"₹{data['closing']:,.2f}", width=120, anchor="e",
                     font=ctk.CTkFont(size=12, weight="bold"), text_color=cl_color,
                     ).grid(row=0, column=5, padx=6, pady=6, sticky="e")

    # ── Exports ───────────────────────────────────────────────────────────────

    def _export_day_book_excel(self, data, from_d, to_d):
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Day Book"
            firm = (db.get_firm_settings() or {}).get("firm_name", "")
            ws["A1"] = f"{firm} — Day Book ({from_d} to {to_d})"
            ws["A1"].font = Font(bold=True, size=13)
            ws.append([])
            hdrs = ["Date", "Narration", "Reference", "Account", "Account Type", "Debit (₹)", "Credit (₹)"]
            ws.append(hdrs)
            for cell in ws[ws.max_row]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="1a3a5c")
            for r in data["rows"]:
                ws.append([r["entry_date"], r["narration"], r.get("reference",""),
                           r["account_name"], r["account_type"], r["debit"], r["credit"]])
            ws.append([])
            ws.append(["", "", "", "TOTAL", "", data["total_dr"], data["total_cr"]])
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = 20
        except ImportError:
            messagebox.showerror("Missing Library", "openpyxl not installed."); return
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
            initialfile=f"DayBook_{from_d}_to_{to_d}.xlsx")
        if path:
            wb.save(path)
            messagebox.showinfo("Exported", f"Saved:\n{path}")
            try: os.startfile(path)
            except: pass

    def _export_day_book_csv(self, data, from_d, to_d):
        import csv
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile=f"DayBook_{from_d}_to_{to_d}.csv")
        if not path: return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Date","Narration","Reference","Account","Type","Debit","Credit"])
            for r in data["rows"]:
                w.writerow([r["entry_date"], r["narration"], r.get("reference",""),
                            r["account_name"], r["account_type"], r["debit"], r["credit"]])
            w.writerow(["","","","TOTAL","",data["total_dr"],data["total_cr"]])
        messagebox.showinfo("Exported", f"Saved:\n{path}")

    def _export_cash_book_excel(self, data, from_d, to_d, label):
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = label
            firm = (db.get_firm_settings() or {}).get("firm_name", "")
            ws["A1"] = f"{firm} — {label} ({from_d} to {to_d})"
            ws["A1"].font = Font(bold=True, size=13)
            ws.append([])
            ws.append(["Opening Balance", "", "", "", "", data["opening"]])
            hdrs = ["Date","Narration","Reference","Receipts (₹)","Payments (₹)","Balance (₹)"]
            ws.append(hdrs)
            for cell in ws[ws.max_row]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="1a3a5c")
            for r in data["rows"]:
                ws.append([r["entry_date"], r["narration"], r.get("reference",""),
                           r["debit"], r["credit"], r["balance"]])
            ws.append(["Closing Balance","","",data["total_dr"],data["total_cr"],data["closing"]])
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = 20
        except ImportError:
            messagebox.showerror("Missing Library", "openpyxl not installed."); return
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
            initialfile=f"{label.replace(' ','_')}_{from_d}_to_{to_d}.xlsx")
        if path:
            wb.save(path)
            messagebox.showinfo("Exported", f"Saved:\n{path}")
            try: os.startfile(path)
            except: pass

    def _export_cash_book_csv(self, data, from_d, to_d, label):
        import csv
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile=f"{label.replace(' ','_')}_{from_d}_to_{to_d}.csv")
        if not path: return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Opening Balance","","","","",data["opening"]])
            w.writerow(["Date","Narration","Reference","Receipts","Payments","Balance"])
            for r in data["rows"]:
                w.writerow([r["entry_date"], r["narration"], r.get("reference",""),
                            r["debit"], r["credit"], r["balance"]])
            w.writerow(["Closing Balance","","",data["total_dr"],data["total_cr"],data["closing"]])
        messagebox.showinfo("Exported", f"Saved:\n{path}")


# ── Godowns Page ─────────────────────────────────────────────────────────────

class GodownsPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._selected_godown_id = None

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._header("Godowns / Warehouses",
                     "Manage multiple storage locations and transfer stock between them")

        tabs = ctk.CTkTabview(self, fg_color="#16213e")
        tabs.pack(fill="both", expand=True, padx=24, pady=(0, 24))
        tabs.add("🏭  Godowns")
        tabs.add("📦  Stock by Godown")
        tabs.add("🔄  Transfer History")

        self._build_godowns_tab(tabs.tab("🏭  Godowns"))
        self._build_stock_tab(tabs.tab("📦  Stock by Godown"))
        self._build_transfers_tab(tabs.tab("🔄  Transfer History"))

    def _build_godowns_tab(self, parent):
        # KPI bar
        summary = db.get_godown_summary()
        sc = ctk.CTkFrame(parent, fg_color="transparent")
        sc.pack(fill="x", padx=0, pady=(12, 8))
        for i in range(4):
            sc.columnconfigure(i, weight=1)
        active = sum(1 for r in summary if r["is_active"])
        total_units = sum(r["total_units"] for r in summary)
        total_val   = sum(r["stock_value"] for r in summary)
        for i, (title, val, color) in enumerate([
            ("Total Godowns",   str(len(summary)),               "#3498db"),
            ("Active",          str(active),                     "#2ecc71"),
            ("Total Units",     f"{total_units:,.0f}",           "#f39c12"),
            ("Stock Value",     f"₹ {total_val:,.0f}",           "#9b59b6"),
        ]):
            c = self._card(sc, title, val, color)
            c.grid(row=0, column=i, padx=6, sticky="ew")

        # Toolbar
        tb = ctk.CTkFrame(parent, fg_color="transparent")
        tb.pack(fill="x", pady=(0, 8))
        ctk.CTkButton(tb, text="+ Add Godown", fg_color="#2ecc71",
                      hover_color="#27ae60", text_color="#000", height=32,
                      command=lambda: GodownDialog(self, self.app, on_save=self.refresh)
                      ).pack(side="left")
        ctk.CTkButton(tb, text="🔄 Transfer Stock", fg_color="#3498db",
                      hover_color="#2980b9", height=32,
                      command=lambda: StockTransferDialog(self, self.app, on_save=self.refresh)
                      ).pack(side="left", padx=8)

        # Table
        tbl = ctk.CTkFrame(parent, fg_color="#16213e", corner_radius=10)
        tbl.pack(fill="both", expand=True)

        hdr = ctk.CTkFrame(tbl, fg_color="#0f3460", corner_radius=6)
        hdr.pack(fill="x", padx=12, pady=(10, 2))
        for col, w in [("Name", 180), ("Location", 160), ("Products", 90),
                       ("Total Units", 100), ("Stock Value", 110),
                       ("Status", 80), ("Actions", 150)]:
            ctk.CTkLabel(hdr, text=col, width=w,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#95a5a6").pack(side="left", padx=4, pady=6)

        scroll = ctk.CTkScrollableFrame(tbl, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        for i, r in enumerate(summary):
            bg = "#0f3460" if i % 2 == 0 else "#16213e"
            row = ctk.CTkFrame(scroll, fg_color=bg, corner_radius=4)
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=r["name"], width=180,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#ecf0f1", anchor="w").pack(side="left", padx=4, pady=5)
            ctk.CTkLabel(row, text=r["location"] or "—", width=160,
                         font=ctk.CTkFont(size=11), text_color="#95a5a6"
                         ).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=str(r["product_count"]), width=90,
                         font=ctk.CTkFont(size=11), text_color="#ecf0f1"
                         ).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=f"{r['total_units']:,.0f}", width=100,
                         font=ctk.CTkFont(size=11), text_color="#f39c12"
                         ).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=f"₹ {r['stock_value']:,.0f}", width=110,
                         font=ctk.CTkFont(size=11), text_color="#9b59b6"
                         ).pack(side="left", padx=4)
            status_text  = "Active"   if r["is_active"] else "Inactive"
            status_color = "#2ecc71" if r["is_active"] else "#e74c3c"
            ctk.CTkLabel(row, text=status_text, width=80,
                         font=ctk.CTkFont(size=10), text_color=status_color
                         ).pack(side="left", padx=4)
            gid = r["id"]
            ctk.CTkButton(row, text="Edit", width=48, height=24,
                          fg_color="#2c3e50", hover_color="#0f3460",
                          font=ctk.CTkFont(size=10),
                          command=lambda gid=gid: GodownDialog(
                              self, self.app, godown_id=gid, on_save=self.refresh)
                          ).pack(side="left", padx=2, pady=4)
            ctk.CTkButton(row, text="Stock", width=52, height=24,
                          fg_color="#2c3e50", hover_color="#0f3460",
                          font=ctk.CTkFont(size=10),
                          command=lambda gid=gid, gn=r["name"]: GodownStockDialog(
                              self, self.app, godown_id=gid, godown_name=gn)
                          ).pack(side="left", padx=2)
            ctk.CTkButton(row, text="Del", width=38, height=24,
                          fg_color="#7f1d1d", hover_color="#991b1b",
                          font=ctk.CTkFont(size=10),
                          command=lambda gid=gid, gn=r["name"]: self._delete_godown(gid, gn)
                          ).pack(side="left", padx=2)

    def _build_stock_tab(self, parent):
        godowns = db.get_all_godowns(active_only=True)
        if not godowns:
            ctk.CTkLabel(parent, text="No active godowns found.",
                         text_color="#95a5a6", font=ctk.CTkFont(size=12)).pack(pady=20)
            return

        # Godown selector
        sel_row = ctk.CTkFrame(parent, fg_color="transparent")
        sel_row.pack(fill="x", pady=(12, 8))
        ctk.CTkLabel(sel_row, text="Select Godown:", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 8))

        godown_names = [r["name"] for r in godowns]
        godown_map   = {r["name"]: r["id"] for r in godowns}
        default_name = godown_names[0]

        self._godown_sel_var = ctk.StringVar(value=default_name)

        def on_godown_change(val):
            self._selected_godown_id = godown_map.get(val)
            _refresh_stock()

        ctk.CTkComboBox(sel_row, values=godown_names, variable=self._godown_sel_var,
                        command=on_godown_change, width=200, height=32
                        ).pack(side="left")

        # Stock table container
        tbl_holder = ctk.CTkFrame(parent, fg_color="transparent")
        tbl_holder.pack(fill="both", expand=True)

        def _refresh_stock():
            for w in tbl_holder.winfo_children():
                w.destroy()
            gid = godown_map.get(self._godown_sel_var.get(), godowns[0]["id"])
            stock = db.get_godown_stock(gid)

            tbl = ctk.CTkFrame(tbl_holder, fg_color="#16213e", corner_radius=10)
            tbl.pack(fill="both", expand=True)

            hdr = ctk.CTkFrame(tbl, fg_color="#0f3460", corner_radius=6)
            hdr.pack(fill="x", padx=12, pady=(10, 2))
            for col, w in [("SKU", 100), ("Product", 220), ("Unit", 60),
                           ("Qty in Godown", 120), ("Low Stock Threshold", 150), ("Status", 80)]:
                ctk.CTkLabel(hdr, text=col, width=w,
                             font=ctk.CTkFont(size=11, weight="bold"),
                             text_color="#95a5a6").pack(side="left", padx=4, pady=6)

            scroll = ctk.CTkScrollableFrame(tbl, fg_color="transparent")
            scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))

            if not stock:
                ctk.CTkLabel(scroll, text="No stock assigned to this godown.",
                             text_color="#95a5a6",
                             font=ctk.CTkFont(size=12)).pack(pady=20)
                return

            for i, s in enumerate(stock):
                is_low = s["quantity"] <= s["low_stock_threshold"]
                bg = "#1a1a2e" if is_low else ("#0f3460" if i % 2 == 0 else "#16213e")
                row = ctk.CTkFrame(scroll, fg_color=bg, corner_radius=4)
                row.pack(fill="x", pady=1)
                ctk.CTkLabel(row, text=s["sku"], width=100,
                             font=ctk.CTkFont(size=11), text_color="#95a5a6"
                             ).pack(side="left", padx=4, pady=5)
                ctk.CTkLabel(row, text=s["name"], width=220,
                             font=ctk.CTkFont(size=11), text_color="#ecf0f1",
                             anchor="w").pack(side="left", padx=4)
                ctk.CTkLabel(row, text=s["unit"] or "pcs", width=60,
                             font=ctk.CTkFont(size=11), text_color="#95a5a6"
                             ).pack(side="left", padx=4)
                ctk.CTkLabel(row, text=f"{s['quantity']:,.0f}", width=120,
                             font=ctk.CTkFont(size=11, weight="bold"),
                             text_color="#e74c3c" if is_low else "#ecf0f1"
                             ).pack(side="left", padx=4)
                ctk.CTkLabel(row, text=str(s["low_stock_threshold"]), width=150,
                             font=ctk.CTkFont(size=11), text_color="#95a5a6"
                             ).pack(side="left", padx=4)
                ctk.CTkLabel(row, text="⚠ Low" if is_low else "✅ OK", width=80,
                             font=ctk.CTkFont(size=11),
                             text_color="#e74c3c" if is_low else "#2ecc71"
                             ).pack(side="left", padx=4)

        _refresh_stock()

    def _build_transfers_tab(self, parent):
        transfers = db.get_stock_transfers()

        tb = ctk.CTkFrame(parent, fg_color="transparent")
        tb.pack(fill="x", pady=(12, 8))
        ctk.CTkButton(tb, text="+ New Transfer", fg_color="#3498db",
                      hover_color="#2980b9", height=32,
                      command=lambda: StockTransferDialog(
                          self, self.app, on_save=self.refresh)).pack(side="left")

        tbl = ctk.CTkFrame(parent, fg_color="#16213e", corner_radius=10)
        tbl.pack(fill="both", expand=True)

        hdr = ctk.CTkFrame(tbl, fg_color="#0f3460", corner_radius=6)
        hdr.pack(fill="x", padx=12, pady=(10, 2))
        for col, w in [("Date", 100), ("Product", 200), ("SKU", 100),
                       ("From", 140), ("To", 140), ("Qty", 80), ("Notes", 200)]:
            ctk.CTkLabel(hdr, text=col, width=w,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#95a5a6").pack(side="left", padx=4, pady=6)

        scroll = ctk.CTkScrollableFrame(tbl, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        if not transfers:
            ctk.CTkLabel(scroll, text="No transfers recorded yet.",
                         text_color="#95a5a6",
                         font=ctk.CTkFont(size=12)).pack(pady=20)
            return

        for i, t in enumerate(transfers):
            bg = "#0f3460" if i % 2 == 0 else "#16213e"
            row = ctk.CTkFrame(scroll, fg_color=bg, corner_radius=4)
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=t["transfer_date"], width=100,
                         font=ctk.CTkFont(size=11), text_color="#95a5a6"
                         ).pack(side="left", padx=4, pady=5)
            ctk.CTkLabel(row, text=t["product_name"], width=200,
                         font=ctk.CTkFont(size=11), text_color="#ecf0f1",
                         anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=t["sku"], width=100,
                         font=ctk.CTkFont(size=11), text_color="#95a5a6"
                         ).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=t["from_godown"], width=140,
                         font=ctk.CTkFont(size=11), text_color="#e74c3c"
                         ).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=t["to_godown"], width=140,
                         font=ctk.CTkFont(size=11), text_color="#2ecc71"
                         ).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=f"{t['quantity']:,.0f}", width=80,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#f39c12").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=(t["notes"] or "")[:30], width=200,
                         font=ctk.CTkFont(size=11), text_color="#95a5a6",
                         anchor="w").pack(side="left", padx=4)

    def _delete_godown(self, gid, name):
        if messagebox.askyesno("Delete Godown",
                               f"Delete '{name}'? This will also remove all stock assignments for it."):
            db.delete_godown(gid)
            self.refresh()


# ── Godown Dialog ─────────────────────────────────────────────────────────────

class GodownDialog(ctk.CTkToplevel):
    def __init__(self, parent, app, godown_id=None, on_save=None):
        super().__init__(parent)
        self.app        = app
        self.godown_id  = godown_id
        self.on_save    = on_save

        existing = dict(db.get_godown(godown_id)) if godown_id else None
        self.title("Edit Godown" if godown_id else "Add Godown")
        self.geometry("440x340")
        self.grab_set()
        self.after(50, self.lift)

        frame = ctk.CTkFrame(self, fg_color="#0d1b2a")
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        def lbl(t):
            ctk.CTkLabel(frame, text=t, text_color="#95a5a6",
                         font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(6, 0))

        lbl("Godown Name *")
        self._name_e = ctk.CTkEntry(frame, height=32)
        self._name_e.pack(fill="x")
        if existing:
            self._name_e.insert(0, existing.get("name", ""))

        lbl("Location / City")
        self._loc_e = ctk.CTkEntry(frame, height=32)
        self._loc_e.pack(fill="x")
        if existing:
            self._loc_e.insert(0, existing.get("location", ""))

        lbl("Address")
        self._addr_e = ctk.CTkEntry(frame, height=32)
        self._addr_e.pack(fill="x")
        if existing:
            self._addr_e.insert(0, existing.get("address", ""))

        self._active_var = ctk.IntVar(value=existing.get("is_active", 1) if existing else 1)
        ctk.CTkCheckBox(frame, text="Active", variable=self._active_var,
                        font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(10, 0))

        ctk.CTkButton(frame, text="Save Godown", height=36,
                      fg_color="#2ecc71", hover_color="#27ae60", text_color="#000",
                      command=self._save).pack(fill="x", pady=(12, 0))

    def _save(self):
        name = self._name_e.get().strip()
        if not name:
            messagebox.showwarning("Validation", "Godown name is required.")
            return
        if self.godown_id:
            db.update_godown(self.godown_id, name, self._loc_e.get().strip(),
                             self._addr_e.get().strip(), self._active_var.get())
        else:
            db.add_godown(name, self._loc_e.get().strip(), self._addr_e.get().strip())
        if self.on_save:
            self.on_save()
        self.destroy()


# ── Godown Stock Dialog (distribute / adjust per-godown quantities) ────────────

class GodownStockDialog(ctk.CTkToplevel):
    """View and adjust per-godown quantities for all products in a godown."""
    def __init__(self, parent, app, godown_id: int, godown_name: str):
        super().__init__(parent)
        self.app        = app
        self.godown_id  = godown_id
        self.title(f"Stock in: {godown_name}")
        self.geometry("700x520")
        self.grab_set()
        self.after(50, self.lift)

        frame = ctk.CTkFrame(self, fg_color="#0d1b2a")
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(frame,
                     text=f"Set quantities for each product in '{godown_name}'.",
                     text_color="#95a5a6", font=ctk.CTkFont(size=11)
                     ).pack(anchor="w", pady=(0, 8))

        hdr = ctk.CTkFrame(frame, fg_color="#0f3460", corner_radius=4)
        hdr.pack(fill="x")
        for col, w in [("SKU", 100), ("Product", 240), ("Total Stock", 110), ("Qty Here", 110)]:
            ctk.CTkLabel(hdr, text=col, width=w,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#95a5a6").pack(side="left", padx=4, pady=5)

        scroll = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        scroll.pack(fill="both", expand=True, pady=(4, 8))

        products  = db.get_all_products()
        stock_map = {r["product_id"]: r["quantity"]
                     for r in db.get_godown_stock(godown_id)}
        self._entries = {}

        for p in products:
            row = ctk.CTkFrame(scroll, fg_color="#16213e", corner_radius=3)
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=dict(p).get("sku", ""), width=100,
                         font=ctk.CTkFont(size=10), text_color="#95a5a6"
                         ).pack(side="left", padx=4, pady=4)
            ctk.CTkLabel(row, text=dict(p).get("name", ""), width=240,
                         font=ctk.CTkFont(size=10), text_color="#ecf0f1",
                         anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=str(dict(p).get("stock_quantity", 0)), width=110,
                         font=ctk.CTkFont(size=10), text_color="#f39c12"
                         ).pack(side="left", padx=4)
            qty = stock_map.get(p["id"], 0)
            e = ctk.CTkEntry(row, width=100, height=26)
            e.insert(0, str(int(qty) if float(qty) == int(qty) else qty))
            e.pack(side="left", padx=4)
            self._entries[p["id"]] = e

        ctk.CTkButton(frame, text="Save Quantities", height=34,
                      fg_color="#2ecc71", hover_color="#27ae60", text_color="#000",
                      command=self._save).pack(fill="x")

    def _save(self):
        for pid, e in self._entries.items():
            try:
                qty = float(e.get() or 0)
            except ValueError:
                qty = 0.0
            db.set_godown_stock(pid, self.godown_id, qty)
        messagebox.showinfo("Saved", "Godown stock quantities updated.")
        self.destroy()


# ── Stock Transfer Dialog ─────────────────────────────────────────────────────

class StockTransferDialog(ctk.CTkToplevel):
    """Transfer stock from one godown to another."""
    def __init__(self, parent, app, on_save=None):
        super().__init__(parent)
        self.app     = app
        self.on_save = on_save
        self.title("Transfer Stock Between Godowns")
        self.geometry("500x420")
        self.grab_set()
        self.after(50, self.lift)

        frame = ctk.CTkFrame(self, fg_color="#0d1b2a")
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        def lbl(t):
            ctk.CTkLabel(frame, text=t, text_color="#95a5a6",
                         font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(8, 0))

        godowns = [dict(r) for r in db.get_all_godowns(active_only=True)]
        godown_names = [g["name"] for g in godowns]
        self._godown_map = {g["name"]: g["id"] for g in godowns}

        products = [dict(p) for p in db.get_all_products()]
        prod_names = [p["name"] for p in products]
        self._prod_map = {p["name"]: p["id"] for p in products}

        lbl("Product *")
        self._prod_var = ctk.StringVar()
        ctk.CTkComboBox(frame, values=prod_names, variable=self._prod_var,
                        height=32).pack(fill="x")

        lbl("From Godown *")
        self._from_var = ctk.StringVar(value=godown_names[0] if godown_names else "")
        ctk.CTkComboBox(frame, values=godown_names, variable=self._from_var,
                        height=32).pack(fill="x")

        lbl("To Godown *")
        self._to_var = ctk.StringVar(value=godown_names[1] if len(godown_names) > 1 else "")
        ctk.CTkComboBox(frame, values=godown_names, variable=self._to_var,
                        height=32).pack(fill="x")

        lbl("Quantity *")
        self._qty_e = ctk.CTkEntry(frame, height=32, placeholder_text="0")
        self._qty_e.pack(fill="x")

        lbl("Transfer Date")
        self._date_e = ctk.CTkEntry(frame, height=32)
        self._date_e.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self._date_e.pack(fill="x")

        lbl("Notes")
        self._notes_e = ctk.CTkEntry(frame, height=32,
                                      placeholder_text="Optional reason for transfer")
        self._notes_e.pack(fill="x")

        ctk.CTkButton(frame, text="Transfer Stock", height=36,
                      fg_color="#3498db", hover_color="#2980b9",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=self._save).pack(fill="x", pady=(14, 0))

    def _save(self):
        prod_name  = self._prod_var.get()
        from_name  = self._from_var.get()
        to_name    = self._to_var.get()

        if not prod_name or prod_name not in self._prod_map:
            messagebox.showwarning("Validation", "Select a product."); return
        if not from_name or from_name not in self._godown_map:
            messagebox.showwarning("Validation", "Select From Godown."); return
        if not to_name or to_name not in self._godown_map:
            messagebox.showwarning("Validation", "Select To Godown."); return
        if from_name == to_name:
            messagebox.showwarning("Validation", "From and To godowns must differ."); return

        try:
            qty = float(self._qty_e.get())
            if qty <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Validation", "Enter a valid quantity > 0."); return

        ok = db.transfer_stock(
            product_id      = self._prod_map[prod_name],
            from_godown_id  = self._godown_map[from_name],
            to_godown_id    = self._godown_map[to_name],
            quantity        = qty,
            transfer_date   = self._date_e.get().strip(),
            notes           = self._notes_e.get().strip(),
        )
        if not ok:
            messagebox.showerror("Insufficient Stock",
                                 f"'{from_name}' does not have {qty:,.0f} units of this product.")
            return

        messagebox.showinfo("Transferred",
                            f"Transferred {qty:,.0f} units of '{prod_name}'\n"
                            f"from {from_name} → {to_name}.")
        if self.on_save:
            self.on_save()
        self.destroy()


# ── Credit / Debit Notes Page ─────────────────────────────────────────────────

class CreditDebitNotesPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._type_filter   = "All"
        self._status_filter = "All"
        self._search_var    = ctk.StringVar()

    def refresh(self):
        for w in self.winfo_children():
            w.destroy()
        self._header("Credit / Debit Notes",
                     "Manage Credit Notes and Debit Notes linked to invoices")

        summary = db.get_cdn_summary()

        # ── KPI tiles ─────────────────────────────────────────────────────────
        sc = ctk.CTkFrame(self, fg_color="transparent")
        sc.pack(fill="x", padx=24, pady=(0, 10))
        for i in range(4):
            sc.columnconfigure(i, weight=1)
        for i, (title, val, color) in enumerate([
            ("Total Credit Notes",   str(summary.get("credit_count", 0)),           "#2ecc71"),
            ("CN Total Amount",      f"₹ {summary.get('credit_total', 0):,.0f}",   "#27ae60"),
            ("Total Debit Notes",    str(summary.get("debit_count", 0)),            "#e74c3c"),
            ("DN Total Amount",      f"₹ {summary.get('debit_total', 0):,.0f}",    "#c0392b"),
        ]):
            c = self._card(sc, title, val, color)
            c.grid(row=0, column=i, padx=6, sticky="ew")

        # ── Toolbar ───────────────────────────────────────────────────────────
        tb = ctk.CTkFrame(self, fg_color="transparent")
        tb.pack(fill="x", padx=24, pady=(0, 8))

        ctk.CTkButton(tb, text="+ Credit Note", fg_color="#2ecc71",
                      hover_color="#27ae60", text_color="#000", height=32,
                      command=lambda: CreditDebitNoteDialog(
                          self, self.app, note_type="Credit", on_save=self.refresh)
                      ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(tb, text="+ Debit Note", fg_color="#e74c3c",
                      hover_color="#c0392b", text_color="#fff", height=32,
                      command=lambda: CreditDebitNoteDialog(
                          self, self.app, note_type="Debit", on_save=self.refresh)
                      ).pack(side="left", padx=(0, 8))

        # Type filter
        for label in ["All", "Credit", "Debit"]:
            active = label == self._type_filter
            ctk.CTkButton(
                tb, text=label, width=74, height=28,
                fg_color="#0f3460" if active else "transparent",
                hover_color="#16213e", border_width=1, border_color="#0f3460",
                font=ctk.CTkFont(size=11),
                command=lambda l=label: self._set_type(l),
            ).pack(side="left", padx=2)

        # Status filter
        for label in ["Draft", "Final"]:
            active = label == self._status_filter
            ctk.CTkButton(
                tb, text=label, width=64, height=28,
                fg_color="#8e44ad" if active else "transparent",
                hover_color="#16213e", border_width=1, border_color="#8e44ad",
                font=ctk.CTkFont(size=11),
                command=lambda l=label: self._set_status(l),
            ).pack(side="left", padx=2)

        # Search
        se = ctk.CTkEntry(tb, textvariable=self._search_var,
                          placeholder_text="Search party …", width=160, height=28)
        se.pack(side="left", padx=8)
        ctk.CTkButton(tb, text="🔍", width=32, height=28,
                      fg_color="transparent", hover_color="#16213e",
                      command=self.refresh).pack(side="left")

        # Export buttons
        ctk.CTkButton(tb, text="📊 Excel", width=80, height=28,
                      fg_color="#16213e", hover_color="#0f3460",
                      font=ctk.CTkFont(size=11),
                      command=self._export_excel).pack(side="right", padx=3)
        ctk.CTkButton(tb, text="📄 PDF", width=70, height=28,
                      fg_color="#16213e", hover_color="#0f3460",
                      font=ctk.CTkFont(size=11),
                      command=self._export_pdf).pack(side="right", padx=3)

        # ── Table ─────────────────────────────────────────────────────────────
        tbl = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=12)
        tbl.pack(fill="both", expand=True, padx=24, pady=(0, 24))

        hdr = ctk.CTkFrame(tbl, fg_color="#0f3460", corner_radius=6)
        hdr.pack(fill="x", padx=12, pady=(12, 2))
        for col, w in [("Note #", 110), ("Date", 90), ("Type", 70),
                       ("Party", 170), ("Orig. Invoice", 110),
                       ("Amount", 110), ("Status", 80), ("Actions", 180)]:
            ctk.CTkLabel(hdr, text=col, width=w,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#95a5a6").pack(side="left", padx=4, pady=6)

        scroll = ctk.CTkScrollableFrame(tbl, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        q = self._search_var.get().strip().lower()
        notes = [dict(r) for r in db.get_all_cdns(
            note_type=self._type_filter if self._type_filter != "All" else None,
            status=self._status_filter if self._status_filter != "All" else None,
        )]
        if q:
            notes = [n for n in notes if q in (n.get("client_name") or "").lower()
                     or q in (n.get("note_number") or "").lower()]

        if not notes:
            ctk.CTkLabel(scroll, text="No notes found.",
                         text_color="#95a5a6",
                         font=ctk.CTkFont(size=12)).pack(pady=20)
            return

        for n in notes:
            bg = "#0f3460" if notes.index(n) % 2 == 0 else "#16213e"
            row = ctk.CTkFrame(scroll, fg_color=bg, corner_radius=4)
            row.pack(fill="x", pady=1)

            is_cn = n.get("note_type") == "Credit"
            type_color = "#2ecc71" if is_cn else "#e74c3c"
            stat_color = "#f39c12" if n.get("status") == "Draft" else "#2ecc71"

            ctk.CTkLabel(row, text=n.get("note_number",""), width=110,
                         font=ctk.CTkFont(size=11), text_color="#ecf0f1",
                         anchor="w").pack(side="left", padx=4, pady=5)
            ctk.CTkLabel(row, text=n.get("note_date",""), width=90,
                         font=ctk.CTkFont(size=11), text_color="#95a5a6"
                         ).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=n.get("note_type",""), width=70,
                         font=ctk.CTkFont(size=11), text_color=type_color,
                         ).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=(n.get("client_name") or "—")[:22], width=170,
                         font=ctk.CTkFont(size=11), text_color="#ecf0f1",
                         anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=(n.get("original_invoice_no") or "—"), width=110,
                         font=ctk.CTkFont(size=11), text_color="#95a5a6"
                         ).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=f"₹ {n.get('grand_total',0):,.2f}", width=110,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#ecf0f1", anchor="e").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=n.get("status",""), width=80,
                         font=ctk.CTkFont(size=10), text_color=stat_color,
                         ).pack(side="left", padx=4)

            # Actions
            nid = n["id"]
            ctk.CTkButton(row, text="Edit", width=48, height=24,
                          fg_color="#2c3e50", hover_color="#0f3460",
                          font=ctk.CTkFont(size=10),
                          command=lambda nid=nid: CreditDebitNoteDialog(
                              self, self.app, note_id=nid, on_save=self.refresh)
                          ).pack(side="left", padx=2, pady=4)
            ctk.CTkButton(row, text="PDF", width=42, height=24,
                          fg_color="#2c3e50", hover_color="#0f3460",
                          font=ctk.CTkFont(size=10),
                          command=lambda nid=nid: self._pdf_note(nid)
                          ).pack(side="left", padx=2)
            ctk.CTkButton(row, text="Del", width=38, height=24,
                          fg_color="#7f1d1d", hover_color="#991b1b",
                          font=ctk.CTkFont(size=10),
                          command=lambda nid=nid: self._delete(nid)
                          ).pack(side="left", padx=2)

    def _set_type(self, v):
        self._type_filter = "All" if self._type_filter == v else v
        self.refresh()

    def _set_status(self, v):
        self._status_filter = "All" if self._status_filter == v else v
        self.refresh()

    def _pdf_note(self, note_id):
        from invoice_pdf import generate_cdn_pdf
        _row  = db.get_cdn_note(note_id)
        note  = dict(_row) if _row else None
        items = [dict(r) for r in db.get_cdn_items(note_id)]
        firm  = db.get_firm_settings()
        if not note:
            messagebox.showerror("Error", "Note not found.")
            return
        path = os.path.join(os.path.expanduser("~"), "Downloads",
                            f"{note['note_number'].replace('/', '_')}.pdf")
        try:
            generate_cdn_pdf(note, items, firm, path)
            messagebox.showinfo("PDF Created", f"Saved to:\n{path}")
        except Exception as exc:
            messagebox.showerror("PDF Error", str(exc))

    def _delete(self, note_id):
        if messagebox.askyesno("Delete", "Delete this note permanently?"):
            db.delete_cdn(note_id)
            self.refresh()

    def _export_pdf(self):
        from report_export import export_cdn_pdf
        notes = db.get_all_cdns(
            note_type=self._type_filter if self._type_filter != "All" else None,
            status=self._status_filter if self._status_filter != "All" else None,
        )
        path = os.path.join(os.path.expanduser("~"), "Downloads", "credit_debit_notes.pdf")
        export_cdn_pdf([dict(r) for r in notes], path)
        messagebox.showinfo("Exported", f"PDF saved to:\n{path}")

    def _export_excel(self):
        from report_export import export_cdn_excel
        notes = db.get_all_cdns(
            note_type=self._type_filter if self._type_filter != "All" else None,
            status=self._status_filter if self._status_filter != "All" else None,
        )
        path = os.path.join(os.path.expanduser("~"), "Downloads", "credit_debit_notes.xlsx")
        export_cdn_excel([dict(r) for r in notes], path)
        messagebox.showinfo("Exported", f"Excel saved to:\n{path}")


# ── Credit / Debit Note Dialog ────────────────────────────────────────────────

class CreditDebitNoteDialog(ctk.CTkToplevel):
    """Create or edit a Credit Note / Debit Note."""

    def __init__(self, parent, app, note_type="Credit", note_id=None, on_save=None):
        super().__init__(parent)
        self.app      = app
        self.note_id  = note_id
        self.on_save  = on_save
        self._items   = []          # list of item dicts

        _row = db.get_cdn_note(note_id) if note_id else None
        existing = dict(_row) if _row else None
        self._note_type = (existing.get("note_type", note_type)
                           if existing else note_type)

        title = "Edit" if note_id else "New"
        self.title(f"{title} {self._note_type} Note")
        self.geometry("900x700")
        self.grab_set()
        self.after(50, self.lift)

        # ── Scroll container ──────────────────────────────────────────────────
        outer = ctk.CTkScrollableFrame(self, fg_color="#0d1b2a")
        outer.pack(fill="both", expand=True, padx=12, pady=12)

        def lbl(parent, text, color="#95a5a6"):
            ctk.CTkLabel(parent, text=text, text_color=color,
                         font=ctk.CTkFont(size=11)).pack(anchor="w")

        def entry(parent, **kw):
            e = ctk.CTkEntry(parent, height=32, **kw)
            e.pack(fill="x", pady=(0, 8))
            return e

        # ── Header row ────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(outer, fg_color="transparent")
        hdr.pack(fill="x", pady=(0, 8))
        hdr.columnconfigure((0, 1, 2, 3), weight=1)

        # Note Type
        ctk.CTkLabel(hdr, text="Note Type", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).grid(row=0, column=0, sticky="w", padx=4)
        self._type_var = ctk.StringVar(value=self._note_type)
        ctk.CTkComboBox(hdr, values=["Credit", "Debit"],
                        variable=self._type_var, state="readonly",
                        height=32).grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 8))

        # Note Number (auto)
        ctk.CTkLabel(hdr, text="Note Number", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).grid(row=0, column=1, sticky="w", padx=4)
        self._num_var = ctk.StringVar(
            value=existing.get("note_number", "") if existing else
            db.next_cdn_number(self._note_type))
        ctk.CTkEntry(hdr, textvariable=self._num_var, height=32
                     ).grid(row=1, column=1, sticky="ew", padx=4, pady=(0, 8))

        # Note Date
        ctk.CTkLabel(hdr, text="Note Date", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).grid(row=0, column=2, sticky="w", padx=4)
        self._date_var = ctk.StringVar(
            value=existing.get("note_date", datetime.now().strftime("%Y-%m-%d"))
            if existing else datetime.now().strftime("%Y-%m-%d"))
        ctk.CTkEntry(hdr, textvariable=self._date_var, height=32
                     ).grid(row=1, column=2, sticky="ew", padx=4, pady=(0, 8))

        # Status
        ctk.CTkLabel(hdr, text="Status", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).grid(row=0, column=3, sticky="w", padx=4)
        self._status_var = ctk.StringVar(
            value=existing.get("status", "Draft") if existing else "Draft")
        ctk.CTkComboBox(hdr, values=["Draft", "Final"],
                        variable=self._status_var, state="readonly",
                        height=32).grid(row=1, column=3, sticky="ew", padx=4, pady=(0, 8))

        # ── Second row ────────────────────────────────────────────────────────
        r2 = ctk.CTkFrame(outer, fg_color="transparent")
        r2.pack(fill="x", pady=(0, 8))
        r2.columnconfigure((0, 1, 2), weight=1)

        # Client / Party
        ctk.CTkLabel(r2, text="Party (Client)", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).grid(row=0, column=0, sticky="w", padx=4)
        clients = db.get_all_clients()
        client_names = [c["name"] for c in clients]
        self._clients_data = {c["name"]: c for c in clients}
        self._client_var = ctk.StringVar(
            value=existing.get("client_name", "") if existing else "")
        self._client_cb = ctk.CTkComboBox(r2, values=client_names,
                                           variable=self._client_var,
                                           height=32, width=240)
        self._client_cb.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 8))

        # Original Invoice
        ctk.CTkLabel(r2, text="Original Invoice No.", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).grid(row=0, column=1, sticky="w", padx=4)
        self._orig_inv_var = ctk.StringVar(
            value=existing.get("original_invoice_no", "") if existing else "")
        ctk.CTkEntry(r2, textvariable=self._orig_inv_var, height=32
                     ).grid(row=1, column=1, sticky="ew", padx=4, pady=(0, 8))

        # Supply Type
        ctk.CTkLabel(r2, text="Supply Type", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).grid(row=0, column=2, sticky="w", padx=4)
        self._supply_var = ctk.StringVar(
            value=existing.get("supply_type", "intra") if existing else "intra")
        ctk.CTkComboBox(r2, values=["intra", "inter"],
                        variable=self._supply_var, state="readonly",
                        height=32).grid(row=1, column=2, sticky="ew", padx=4, pady=(0, 8))

        # ── Reason ────────────────────────────────────────────────────────────
        ctk.CTkLabel(outer, text="Reason", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=4)
        self._reason_var = ctk.StringVar(
            value=existing.get("reason", "") if existing else "")
        ctk.CTkEntry(outer, textvariable=self._reason_var, height=32
                     ).pack(fill="x", padx=4, pady=(0, 8))

        # ── Items section ─────────────────────────────────────────────────────
        ctk.CTkLabel(outer, text="Line Items",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#ecf0f1").pack(anchor="w", padx=4, pady=(4, 2))

        item_toolbar = ctk.CTkFrame(outer, fg_color="transparent")
        item_toolbar.pack(fill="x", padx=4, pady=(0, 4))
        ctk.CTkButton(item_toolbar, text="+ Add Item", width=100, height=28,
                      fg_color="#2ecc71", hover_color="#27ae60", text_color="#000",
                      command=self._add_item_row).pack(side="left")

        # Header row for items
        ih = ctk.CTkFrame(outer, fg_color="#0f3460", corner_radius=4)
        ih.pack(fill="x", padx=4, pady=(0, 2))
        for col, w in [("Description", 220), ("HSN", 70), ("Qty", 55),
                       ("Unit", 55), ("Rate", 80), ("GST%", 55),
                       ("Total", 90), ("", 32)]:
            ctk.CTkLabel(ih, text=col, width=w,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#95a5a6").pack(side="left", padx=3, pady=4)

        self._items_frame = ctk.CTkFrame(outer, fg_color="transparent")
        self._items_frame.pack(fill="x", padx=4)

        # ── Notes ─────────────────────────────────────────────────────────────
        ctk.CTkLabel(outer, text="Internal Notes", text_color="#95a5a6",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=4, pady=(8, 0))
        self._notes_box = ctk.CTkTextbox(outer, height=60)
        self._notes_box.pack(fill="x", padx=4, pady=(0, 8))
        if existing and existing.get("notes"):
            self._notes_box.insert("0.0", existing["notes"])

        # ── Totals display ────────────────────────────────────────────────────
        self._totals_frame = ctk.CTkFrame(outer, fg_color="#0f3460", corner_radius=6)
        self._totals_frame.pack(fill="x", padx=4, pady=(4, 8))
        self._total_lbl = ctk.CTkLabel(self._totals_frame,
                                        text="Grand Total: ₹ 0.00",
                                        font=ctk.CTkFont(size=13, weight="bold"),
                                        text_color="#2ecc71")
        self._total_lbl.pack(side="right", padx=16, pady=8)
        self._tax_lbl = ctk.CTkLabel(self._totals_frame,
                                      text="Tax: ₹ 0.00",
                                      font=ctk.CTkFont(size=11),
                                      text_color="#95a5a6")
        self._tax_lbl.pack(side="right", padx=16, pady=8)
        self._sub_lbl = ctk.CTkLabel(self._totals_frame,
                                      text="Subtotal: ₹ 0.00",
                                      font=ctk.CTkFont(size=11),
                                      text_color="#95a5a6")
        self._sub_lbl.pack(side="right", padx=16, pady=8)

        # ── Save button ───────────────────────────────────────────────────────
        ctk.CTkButton(outer, text="Save Note", height=36,
                      fg_color="#2ecc71", hover_color="#27ae60", text_color="#000",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=self._save).pack(fill="x", padx=4, pady=(4, 4))

        # Load existing items
        if note_id:
            existing_items = [dict(r) for r in db.get_cdn_items(note_id)]
            for it in existing_items:
                self._add_item_row(it)
        else:
            self._add_item_row()

    def _add_item_row(self, data=None):
        row = ctk.CTkFrame(self._items_frame, fg_color="#16213e", corner_radius=3)
        row.pack(fill="x", pady=1)
        row._entries = {}

        for key, w, placeholder in [
            ("description", 220, "Item description"),
            ("hsn_code", 70, "HSN"),
            ("quantity", 55, "1"),
            ("unit", 55, "NOS"),
            ("unit_price", 80, "0.00"),
            ("gst_rate", 55, "18"),
        ]:
            e = ctk.CTkEntry(row, width=w, height=26, placeholder_text=placeholder)
            e.pack(side="left", padx=2, pady=3)
            if data and data.get(key) is not None:
                e.insert(0, str(data[key]))
            row._entries[key] = e

        # Total display
        row._total_lbl = ctk.CTkLabel(row, text="₹ 0.00", width=90,
                                       font=ctk.CTkFont(size=10),
                                       text_color="#2ecc71")
        row._total_lbl.pack(side="left", padx=2)
        if data:
            row._total_lbl.configure(text=f"₹ {data.get('total_amt',0):,.2f}")

        # Bind recalculate on change
        for key in ("quantity", "unit_price", "gst_rate"):
            row._entries[key].bind("<FocusOut>", lambda e, r=row: self._recalc_row(r))
            row._entries[key].bind("<Return>",   lambda e, r=row: self._recalc_row(r))

        ctk.CTkButton(row, text="×", width=28, height=26,
                      fg_color="#7f1d1d", hover_color="#991b1b",
                      font=ctk.CTkFont(size=12),
                      command=lambda r=row: self._remove_row(r)
                      ).pack(side="left", padx=2)

    def _remove_row(self, row):
        row.destroy()
        self._recalc_totals()

    def _recalc_row(self, row):
        try:
            qty   = float(row._entries["quantity"].get() or 1)
            rate  = float(row._entries["unit_price"].get() or 0)
            gst   = float(row._entries["gst_rate"].get() or 0)
            taxable = round(qty * rate, 2)
            tax   = round(taxable * gst / 100, 2)
            total = round(taxable + tax, 2)
            row._total_lbl.configure(text=f"₹ {total:,.2f}")
        except Exception:
            pass
        self._recalc_totals()

    def _recalc_totals(self):
        subtotal = cgst_tot = sgst_tot = igst_tot = grand = 0.0
        is_intra = self._supply_var.get() == "intra"
        for row in self._items_frame.winfo_children():
            if not hasattr(row, "_entries"):
                continue
            try:
                qty     = float(row._entries["quantity"].get() or 1)
                rate    = float(row._entries["unit_price"].get() or 0)
                gst     = float(row._entries["gst_rate"].get() or 0)
                taxable = round(qty * rate, 2)
                tax     = round(taxable * gst / 100, 2)
                subtotal += taxable
                if is_intra:
                    cgst_tot += tax / 2
                    sgst_tot += tax / 2
                else:
                    igst_tot += tax
                grand   += taxable + tax
            except Exception:
                pass
        tax_total = cgst_tot + sgst_tot + igst_tot
        self._sub_lbl.configure(text=f"Subtotal: ₹ {subtotal:,.2f}")
        self._tax_lbl.configure(text=f"Tax: ₹ {tax_total:,.2f}")
        self._total_lbl.configure(text=f"Grand Total: ₹ {grand:,.2f}")

    def _collect_items(self):
        items = []
        is_intra = self._supply_var.get() == "intra"
        for row in self._items_frame.winfo_children():
            if not hasattr(row, "_entries"):
                continue
            desc = row._entries["description"].get().strip()
            if not desc:
                continue
            qty   = float(row._entries["quantity"].get() or 1)
            rate  = float(row._entries["unit_price"].get() or 0)
            gst   = float(row._entries["gst_rate"].get() or 0)
            taxable = round(qty * rate, 2)
            tax     = round(taxable * gst / 100, 2)
            cgst = sgst = igst = 0.0
            if is_intra:
                cgst = sgst = round(tax / 2, 2)
            else:
                igst = tax
            items.append({
                "description":   desc,
                "hsn_code":      row._entries["hsn_code"].get().strip(),
                "quantity":      qty,
                "unit":          row._entries["unit"].get().strip() or "NOS",
                "unit_price":    rate,
                "gst_rate":      gst,
                "taxable_value": taxable,
                "cgst_amt":      cgst,
                "sgst_amt":      sgst,
                "igst_amt":      igst,
                "total_amt":     round(taxable + tax, 2),
            })
        return items

    def _save(self):
        items = self._collect_items()
        if not items:
            messagebox.showwarning("Validation", "Add at least one line item.")
            return

        is_intra = self._supply_var.get() == "intra"
        subtotal = sum(i["taxable_value"] for i in items)
        cgst_tot = sum(i["cgst_amt"] for i in items)
        sgst_tot = sum(i["sgst_amt"] for i in items)
        igst_tot = sum(i["igst_amt"] for i in items)
        grand    = sum(i["total_amt"] for i in items)

        data = {
            "note_type":           self._type_var.get(),
            "note_number":         self._num_var.get().strip(),
            "note_date":           self._date_var.get().strip(),
            "original_invoice_no": self._orig_inv_var.get().strip(),
            "client_name":         self._client_var.get().strip(),
            "reason":              self._reason_var.get().strip(),
            "supply_type":         self._supply_var.get(),
            "subtotal":            round(subtotal, 2),
            "cgst_total":          round(cgst_tot, 2),
            "sgst_total":          round(sgst_tot, 2),
            "igst_total":          round(igst_tot, 2),
            "discount_amt":        0.0,
            "grand_total":         round(grand, 2),
            "status":              self._status_var.get(),
            "notes":               self._notes_box.get("0.0", "end").strip(),
        }

        args = (
            data["note_type"], data["note_number"], data["note_date"],
            None, data["client_name"],
            None, data["original_invoice_no"],
            data["reason"], data["supply_type"],
            data["subtotal"], data["cgst_total"], data["sgst_total"],
            data["igst_total"], data["discount_amt"], data["grand_total"],
            data["status"], data["notes"], items,
        )
        if self.note_id:
            db.update_cdn(self.note_id, *args)
        else:
            db.save_cdn(*args)

        if self.on_save:
            self.on_save()
        self.destroy()


# ── Fixed Assets Register ─────────────────────────────────────────────────────

class FixedAssetsPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._header("🏗  Fixed Assets Register",
                     "Track company assets, depreciation schedules, and disposals")

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=20, pady=(0, 8))
        ctk.CTkButton(toolbar, text="+ Add Asset", fg_color="#1a5276",
                      hover_color="#2980b9",
                      command=self._add_asset).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="📋 Depreciation Schedule", fg_color="#6c3483",
                      hover_color="#7d3c98",
                      command=lambda: self._show_tab(1)).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="🗑 Disposed Assets", fg_color="#922b21",
                      hover_color="#a93226",
                      command=lambda: self._show_tab(2)).pack(side="left", padx=4)

        # KPI bar
        summary = db.get_asset_summary()
        kpi_row = ctk.CTkFrame(self, fg_color="transparent")
        kpi_row.pack(fill="x", padx=20, pady=(0, 10))
        kpis = [
            ("Total Assets", str(summary.get("total_assets", 0)), COLORS["accent"]),
            ("Active Assets", str(summary.get("active_count", 0)), COLORS["success"]),
            ("Total Cost", f"₹{summary.get('total_cost', 0):,.0f}", "#8e44ad"),
            ("Disposed", str(summary.get("disposed_count", 0)), COLORS["danger"]),
        ]
        for label, val, color in kpis:
            card = self._card(kpi_row, pad=False)
            card.pack(side="left", fill="x", expand=True, padx=4, pady=2)
            ctk.CTkLabel(card, text=val, font=ctk.CTkFont(size=20, weight="bold"),
                         text_color=color).pack(pady=(8, 0))
            ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=10),
                         text_color=COLORS["text_dim"]).pack(pady=(0, 8))

        # Tabs
        self._tab_widget = ctk.CTkTabview(self)
        self._tab_widget.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        self._tab_widget.add("🏗  Asset Register")
        self._tab_widget.add("📉  Depreciation Schedule")
        self._tab_widget.add("🗑  Disposed Assets")

        self._build_register_tab(self._tab_widget.tab("🏗  Asset Register"))
        self._build_depreciation_tab(self._tab_widget.tab("📉  Depreciation Schedule"))
        self._build_disposed_tab(self._tab_widget.tab("🗑  Disposed Assets"))

    def _show_tab(self, idx):
        names = ["🏗  Asset Register", "📉  Depreciation Schedule", "🗑  Disposed Assets"]
        self._tab_widget.set(names[idx])

    def _build_register_tab(self, parent):
        # Filter bar
        fb = ctk.CTkFrame(parent, fg_color="transparent")
        fb.pack(fill="x", pady=(4, 6))
        ctk.CTkLabel(fb, text="Category:", font=ctk.CTkFont(size=11)).pack(side="left", padx=(4, 2))
        self._cat_var = ctk.StringVar(value="All")
        cats = ["All"] + db.ASSET_CATEGORIES
        ctk.CTkOptionMenu(fb, variable=self._cat_var, values=cats, width=180,
                          command=lambda _: self._refresh_register()).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(fb, text="Status:", font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 2))
        self._status_var = ctk.StringVar(value="Active")
        ctk.CTkOptionMenu(fb, variable=self._status_var,
                          values=["All", "Active", "Disposed", "Written Off"], width=120,
                          command=lambda _: self._refresh_register()).pack(side="left")

        self._reg_scroll = ctk.CTkScrollableFrame(parent)
        self._reg_scroll.pack(fill="both", expand=True, pady=(2, 0))
        self._refresh_register()

    def _refresh_register(self):
        for w in self._reg_scroll.winfo_children():
            w.destroy()
        cat = self._cat_var.get() if self._cat_var.get() != "All" else None
        status = self._status_var.get() if self._status_var.get() != "All" else None
        assets = [dict(r) for r in db.get_assets_with_nbv()]
        if cat:
            assets = [a for a in assets if a["category"] == cat]
        if status:
            assets = [a for a in assets if a["status"] == status]

        hdrs = ["Code", "Name", "Category", "Purchase Date", "Cost", "NBV", "Method", "Status", "Actions"]
        widths = [70, 180, 140, 100, 100, 100, 55, 70, 130]
        hdr_row = ctk.CTkFrame(self._reg_scroll, fg_color="#1a3a5c")
        hdr_row.pack(fill="x", pady=(0, 2))
        for h, w in zip(hdrs, widths):
            ctk.CTkLabel(hdr_row, text=h, font=ctk.CTkFont(size=11, weight="bold"),
                         width=w, anchor="w").pack(side="left", padx=4, pady=4)

        if not assets:
            ctk.CTkLabel(self._reg_scroll, text="No assets found.",
                         text_color=COLORS["text_dim"]).pack(pady=20)
            return

        for a in assets:
            row = ctk.CTkFrame(self._reg_scroll, fg_color=COLORS["card_bg"],
                               corner_radius=4)
            row.pack(fill="x", pady=1)
            vals = [
                a["asset_code"], a["name"], a["category"],
                a.get("purchase_date", ""), f"₹{a['purchase_cost']:,.0f}",
                f"₹{a.get('current_nbv', a['purchase_cost']):,.0f}",
                a.get("depreciation_method", "SLM"), a["status"],
            ]
            colors = [COLORS["text"]] * len(vals)
            if a["status"] == "Active":
                colors[7] = COLORS["success"]
            elif a["status"] == "Disposed":
                colors[7] = COLORS["danger"]
            for val, w, col in zip(vals, widths, colors):
                ctk.CTkLabel(row, text=str(val), font=ctk.CTkFont(size=11),
                             width=w, anchor="w", text_color=col).pack(side="left", padx=4, pady=5)
            act = ctk.CTkFrame(row, fg_color="transparent")
            act.pack(side="left", padx=4)
            aid = a["id"]
            ctk.CTkButton(act, text="Edit", width=48, height=24, fg_color="#1a5276",
                          hover_color="#2980b9", font=ctk.CTkFont(size=10),
                          command=lambda x=aid: self._edit_asset(x)).pack(side="left", padx=2)
            ctk.CTkButton(act, text="Dep.", width=46, height=24, fg_color="#6c3483",
                          hover_color="#7d3c98", font=ctk.CTkFont(size=10),
                          command=lambda x=aid: self._add_depreciation(x)).pack(side="left", padx=2)
            if a["status"] == "Active":
                ctk.CTkButton(act, text="Dispose", width=58, height=24, fg_color="#922b21",
                              hover_color="#a93226", font=ctk.CTkFont(size=10),
                              command=lambda x=aid: self._dispose_asset(x)).pack(side="left", padx=2)

    def _build_depreciation_tab(self, parent):
        ctk.CTkLabel(parent, text="Select asset to view depreciation schedule:",
                     font=ctk.CTkFont(size=11), text_color=COLORS["text_dim"]).pack(anchor="w", pady=(6, 2), padx=4)
        assets = [dict(r) for r in db.get_all_assets(status="Active")]
        if not assets:
            ctk.CTkLabel(parent, text="No active assets.", text_color=COLORS["text_dim"]).pack(pady=20)
            return
        self._dep_asset_var = ctk.StringVar(value=f"{assets[0]['asset_code']} – {assets[0]['name']}")
        self._dep_asset_map = {f"{a['asset_code']} – {a['name']}": a["id"] for a in assets}
        ctk.CTkOptionMenu(parent, variable=self._dep_asset_var,
                          values=list(self._dep_asset_map.keys()), width=320,
                          command=lambda _: self._refresh_dep_schedule()).pack(anchor="w", padx=4, pady=(0, 6))
        self._dep_scroll = ctk.CTkScrollableFrame(parent)
        self._dep_scroll.pack(fill="both", expand=True)
        self._refresh_dep_schedule()

    def _refresh_dep_schedule(self):
        for w in self._dep_scroll.winfo_children():
            w.destroy()
        aid = self._dep_asset_map.get(self._dep_asset_var.get())
        if not aid:
            return
        entries = [dict(r) for r in db.get_asset_depreciation(aid)]
        asset = dict(db.get_asset(aid)) if db.get_asset(aid) else {}

        hdrs = ["Financial Year", "Opening NBV", "Depreciation", "Accumulated Dep.", "Closing NBV", "Entry Date", "Notes"]
        widths = [110, 120, 120, 150, 120, 100, 200]
        hdr_row = ctk.CTkFrame(self._dep_scroll, fg_color="#1a3a5c")
        hdr_row.pack(fill="x", pady=(0, 2))
        for h, w in zip(hdrs, widths):
            ctk.CTkLabel(hdr_row, text=h, font=ctk.CTkFont(size=11, weight="bold"),
                         width=w, anchor="w").pack(side="left", padx=4, pady=4)

        if not entries:
            ctk.CTkLabel(self._dep_scroll, text="No depreciation recorded yet.",
                         text_color=COLORS["text_dim"]).pack(pady=20)
            return

        for e in entries:
            row = ctk.CTkFrame(self._dep_scroll, fg_color=COLORS["card_bg"], corner_radius=4)
            row.pack(fill="x", pady=1)
            vals = [
                e["financial_year"],
                f"₹{e['opening_nbv']:,.2f}",
                f"₹{e['depreciation_amount']:,.2f}",
                f"₹{e['accumulated_depreciation']:,.2f}",
                f"₹{e['closing_nbv']:,.2f}",
                e.get("entry_date", ""),
                e.get("notes", ""),
            ]
            for val, w in zip(vals, widths):
                ctk.CTkLabel(row, text=str(val), font=ctk.CTkFont(size=11),
                             width=w, anchor="w").pack(side="left", padx=4, pady=5)

    def _build_disposed_tab(self, parent):
        self._disp_scroll = ctk.CTkScrollableFrame(parent)
        self._disp_scroll.pack(fill="both", expand=True, pady=4)
        assets = [dict(r) for r in db.get_all_assets(status="Disposed")]

        hdrs = ["Code", "Name", "Category", "Purchase Cost", "Disposal Date", "Disposal Value", "Profit/Loss"]
        widths = [80, 180, 140, 120, 110, 120, 110]
        hdr_row = ctk.CTkFrame(self._disp_scroll, fg_color="#1a3a5c")
        hdr_row.pack(fill="x", pady=(0, 2))
        for h, w in zip(hdrs, widths):
            ctk.CTkLabel(hdr_row, text=h, font=ctk.CTkFont(size=11, weight="bold"),
                         width=w, anchor="w").pack(side="left", padx=4, pady=4)

        if not assets:
            ctk.CTkLabel(self._disp_scroll, text="No disposed assets.",
                         text_color=COLORS["text_dim"]).pack(pady=20)
            return

        for a in assets:
            row = ctk.CTkFrame(self._disp_scroll, fg_color=COLORS["card_bg"], corner_radius=4)
            row.pack(fill="x", pady=1)
            pl = a.get("disposal_value", 0) - a["purchase_cost"]
            pl_color = COLORS["success"] if pl >= 0 else COLORS["danger"]
            vals = [
                a["asset_code"], a["name"], a["category"],
                f"₹{a['purchase_cost']:,.0f}",
                a.get("disposal_date", ""),
                f"₹{a.get('disposal_value', 0):,.0f}",
            ]
            widths_data = widths[:-1]
            for val, w in zip(vals, widths_data):
                ctk.CTkLabel(row, text=str(val), font=ctk.CTkFont(size=11),
                             width=w, anchor="w").pack(side="left", padx=4, pady=5)
            pl_sign = "+" if pl >= 0 else ""
            ctk.CTkLabel(row, text=f"{pl_sign}₹{pl:,.0f}", font=ctk.CTkFont(size=11),
                         width=widths[-1], anchor="w", text_color=pl_color).pack(side="left", padx=4, pady=5)

    def _add_asset(self):
        AssetDialog(self, on_save=self.refresh)

    def _edit_asset(self, asset_id):
        AssetDialog(self, asset_id=asset_id, on_save=self.refresh)

    def _add_depreciation(self, asset_id):
        DepreciationDialog(self, asset_id=asset_id,
                           on_save=lambda: (self.refresh(), self._refresh_dep_schedule()
                           if hasattr(self, "_dep_asset_var") else None))

    def _dispose_asset(self, asset_id):
        AssetDisposalDialog(self, asset_id=asset_id, on_save=self.refresh)

    def refresh(self):
        self._refresh_register()
        if hasattr(self, "_dep_scroll"):
            self._refresh_dep_schedule()
        for w in self._disp_scroll.winfo_children():
            w.destroy()
        assets = [dict(r) for r in db.get_all_assets(status="Disposed")]
        hdrs = ["Code", "Name", "Category", "Purchase Cost", "Disposal Date", "Disposal Value", "Profit/Loss"]
        widths = [80, 180, 140, 120, 110, 120, 110]
        hdr_row = ctk.CTkFrame(self._disp_scroll, fg_color="#1a3a5c")
        hdr_row.pack(fill="x", pady=(0, 2))
        for h, w in zip(hdrs, widths):
            ctk.CTkLabel(hdr_row, text=h, font=ctk.CTkFont(size=11, weight="bold"),
                         width=w, anchor="w").pack(side="left", padx=4, pady=4)
        if not assets:
            ctk.CTkLabel(self._disp_scroll, text="No disposed assets.",
                         text_color=COLORS["text_dim"]).pack(pady=20)
            return
        for a in assets:
            row = ctk.CTkFrame(self._disp_scroll, fg_color=COLORS["card_bg"], corner_radius=4)
            row.pack(fill="x", pady=1)
            pl = a.get("disposal_value", 0) - a["purchase_cost"]
            pl_color = COLORS["success"] if pl >= 0 else COLORS["danger"]
            vals = [a["asset_code"], a["name"], a["category"],
                    f"₹{a['purchase_cost']:,.0f}", a.get("disposal_date", ""),
                    f"₹{a.get('disposal_value', 0):,.0f}"]
            for val, w in zip(vals, widths[:-1]):
                ctk.CTkLabel(row, text=str(val), font=ctk.CTkFont(size=11),
                             width=w, anchor="w").pack(side="left", padx=4, pady=5)
            pl_sign = "+" if pl >= 0 else ""
            ctk.CTkLabel(row, text=f"{pl_sign}₹{pl:,.0f}", font=ctk.CTkFont(size=11),
                         width=widths[-1], anchor="w", text_color=pl_color).pack(side="left", padx=4, pady=5)


class AssetDialog(ctk.CTkToplevel):
    def __init__(self, parent, asset_id=None, on_save=None):
        super().__init__(parent)
        self.asset_id = asset_id
        self.on_save = on_save
        self.title("Edit Asset" if asset_id else "Add Fixed Asset")
        self.geometry("680x640")
        self.resizable(False, False)
        self.grab_set()

        _row = db.get_asset(asset_id) if asset_id else None
        ex = dict(_row) if _row else {}

        scroll = ctk.CTkScrollableFrame(self)
        scroll.pack(fill="both", expand=True, padx=16, pady=12)

        def _field(label, row, col=0, width=220, colspan=1):
            ctk.CTkLabel(scroll, text=label, font=ctk.CTkFont(size=11),
                         text_color=COLORS["text_dim"]).grid(row=row*2, column=col, sticky="w", padx=6, pady=(6, 0))
            var = ctk.StringVar(value="")
            ent = ctk.CTkEntry(scroll, textvariable=var, width=width if colspan == 1 else width*colspan+10)
            ent.grid(row=row*2+1, column=col, columnspan=colspan, sticky="ew", padx=6, pady=(0, 2))
            return var

        scroll.columnconfigure(0, weight=1)
        scroll.columnconfigure(1, weight=1)
        scroll.columnconfigure(2, weight=1)

        self._code_var = _field("Asset Code *", 0, 0)
        self._code_var.set(ex.get("asset_code", db.next_asset_code()))

        self._name_var = _field("Asset Name *", 0, 1, colspan=2)
        self._name_var.set(ex.get("name", ""))

        ctk.CTkLabel(scroll, text="Category *", font=ctk.CTkFont(size=11),
                     text_color=COLORS["text_dim"]).grid(row=2, column=0, sticky="w", padx=6, pady=(6, 0))
        self._cat_var = ctk.StringVar(value=ex.get("category", db.ASSET_CATEGORIES[0]))
        ctk.CTkOptionMenu(scroll, variable=self._cat_var, values=db.ASSET_CATEGORIES,
                          width=220).grid(row=3, column=0, sticky="ew", padx=6)

        self._loc_var = _field("Location", 1, 1)
        self._loc_var.set(ex.get("location", ""))
        self._vendor_var = _field("Vendor / Supplier", 1, 2)
        self._vendor_var.set(ex.get("vendor", ""))

        self._date_var = _field("Purchase Date * (YYYY-MM-DD)", 2, 0)
        self._date_var.set(ex.get("purchase_date", datetime.today().strftime("%Y-%m-%d")))
        self._cost_var = _field("Purchase Cost (₹) *", 2, 1)
        self._cost_var.set(str(ex.get("purchase_cost", "")))
        self._salvage_var = _field("Salvage / Residual Value (₹)", 2, 2)
        self._salvage_var.set(str(ex.get("salvage_value", "0")))

        ctk.CTkLabel(scroll, text="Depreciation Method *", font=ctk.CTkFont(size=11),
                     text_color=COLORS["text_dim"]).grid(row=6, column=0, sticky="w", padx=6, pady=(6, 0))
        self._method_var = ctk.StringVar(value=ex.get("depreciation_method", "SLM"))
        ctk.CTkOptionMenu(scroll, variable=self._method_var, values=["SLM", "WDV"],
                          width=220, command=self._on_method_change).grid(row=7, column=0, sticky="ew", padx=6)

        self._life_var = _field("Useful Life (Years) *", 3, 1)
        self._life_var.set(str(ex.get("useful_life_years", "5")))
        self._rate_var = _field("Depreciation Rate (%) *", 3, 2)
        self._rate_var.set(str(ex.get("depreciation_rate", "20")))

        self._inv_var = _field("Invoice No.", 4, 0)
        self._inv_var.set(ex.get("invoice_no", ""))

        ctk.CTkLabel(scroll, text="Description", font=ctk.CTkFont(size=11),
                     text_color=COLORS["text_dim"]).grid(row=9, column=0, sticky="w", padx=6, pady=(6, 0))
        self._desc_box = ctk.CTkTextbox(scroll, height=60)
        self._desc_box.grid(row=10, column=0, columnspan=3, sticky="ew", padx=6)
        self._desc_box.insert("0.0", ex.get("description", ""))

        ctk.CTkLabel(scroll, text="Notes", font=ctk.CTkFont(size=11),
                     text_color=COLORS["text_dim"]).grid(row=11, column=0, sticky="w", padx=6, pady=(6, 0))
        self._notes_box = ctk.CTkTextbox(scroll, height=60)
        self._notes_box.grid(row=12, column=0, columnspan=3, sticky="ew", padx=6, pady=(0, 8))
        self._notes_box.insert("0.0", ex.get("notes", ""))

        self._on_method_change(self._method_var.get())

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=8)
        ctk.CTkButton(btn_row, text="Save Asset", fg_color=COLORS["success"],
                      hover_color="#27ae60", command=self._save).pack(side="right", padx=4)
        ctk.CTkButton(btn_row, text="Cancel", fg_color="#555",
                      hover_color="#444", command=self.destroy).pack(side="right", padx=4)

    def _on_method_change(self, method):
        pass

    def _save(self):
        code = self._code_var.get().strip()
        name = self._name_var.get().strip()
        date = self._date_var.get().strip()
        if not code or not name or not date:
            messagebox.showwarning("Validation", "Asset Code, Name, and Purchase Date are required.", parent=self)
            return
        try:
            cost = float(self._cost_var.get())
            salvage = float(self._salvage_var.get() or 0)
            life = float(self._life_var.get() or 5)
            rate = float(self._rate_var.get() or 20)
        except ValueError:
            messagebox.showwarning("Validation", "Cost, Life, and Rate must be numbers.", parent=self)
            return

        args = (code, name, self._cat_var.get(),
                self._desc_box.get("0.0", "end").strip(),
                date, cost, salvage, life,
                self._method_var.get(), rate,
                self._loc_var.get().strip(),
                self._vendor_var.get().strip(),
                self._inv_var.get().strip(),
                self._notes_box.get("0.0", "end").strip())
        try:
            if self.asset_id:
                db.update_asset(self.asset_id, *args)
            else:
                db.add_asset(*args)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)
            return
        if self.on_save:
            self.on_save()
        self.destroy()


class DepreciationDialog(ctk.CTkToplevel):
    def __init__(self, parent, asset_id, on_save=None):
        super().__init__(parent)
        self.asset_id = asset_id
        self.on_save = on_save
        self.title("Record Depreciation")
        self.geometry("500x480")
        self.resizable(False, False)
        self.grab_set()

        _row = db.get_asset(asset_id)
        self.asset = dict(_row) if _row else {}

        # Compute opening NBV from last depreciation entry
        entries = [dict(r) for r in db.get_asset_depreciation(asset_id)]
        if entries:
            last = entries[-1]
            self._opening_nbv = last["closing_nbv"]
            self._accumulated = last["accumulated_depreciation"]
        else:
            self._opening_nbv = self.asset.get("purchase_cost", 0)
            self._accumulated = 0.0

        frm = ctk.CTkFrame(self, fg_color="transparent")
        frm.pack(fill="both", expand=True, padx=16, pady=12)

        ctk.CTkLabel(frm, text=f"Asset: {self.asset.get('asset_code', '')} – {self.asset.get('name', '')}",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(frm, text=f"Method: {self.asset.get('depreciation_method', 'SLM')}  |  "
                               f"Opening NBV: ₹{self._opening_nbv:,.2f}",
                     font=ctk.CTkFont(size=11), text_color=COLORS["text_dim"]).pack(anchor="w", pady=(0, 10))

        def _lbl(text): ctk.CTkLabel(frm, text=text, font=ctk.CTkFont(size=11),
                                     text_color=COLORS["text_dim"]).pack(anchor="w")
        def _ent(var): e = ctk.CTkEntry(frm, textvariable=var, width=300); e.pack(anchor="w", pady=(0, 8)); return e

        # Suggest current FY
        today = datetime.today()
        if today.month >= 4:
            default_fy = f"{today.year}-{today.year+1}"
        else:
            default_fy = f"{today.year-1}-{today.year}"

        _lbl("Financial Year (e.g. 2024-2025) *")
        self._fy_var = ctk.StringVar(value=default_fy)
        _ent(self._fy_var)

        # Auto-calculate depreciation
        suggested = db.calculate_depreciation_amount(
            self.asset.get("purchase_cost", 0),
            self.asset.get("salvage_value", 0),
            self.asset.get("useful_life_years", 5),
            self.asset.get("depreciation_method", "SLM"),
            self.asset.get("depreciation_rate", 20),
            self._opening_nbv,
        )

        _lbl(f"Depreciation Amount (₹) * [Suggested: ₹{suggested:,.2f}]")
        self._dep_var = ctk.StringVar(value=str(suggested))
        _ent(self._dep_var)

        _lbl("Entry Date (YYYY-MM-DD)")
        self._date_var = ctk.StringVar(value=today.strftime("%Y-%m-%d"))
        _ent(self._date_var)

        _lbl("Notes")
        self._notes_var = ctk.StringVar(value="")
        _ent(self._notes_var)

        # Preview closing NBV
        self._preview_lbl = ctk.CTkLabel(frm, text="", font=ctk.CTkFont(size=12),
                                          text_color=COLORS["success"])
        self._preview_lbl.pack(anchor="w", pady=(4, 0))
        self._dep_var.trace_add("write", lambda *_: self._update_preview())
        self._update_preview()

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=8)
        ctk.CTkButton(btn_row, text="Record Depreciation", fg_color=COLORS["success"],
                      hover_color="#27ae60", command=self._save).pack(side="right", padx=4)
        ctk.CTkButton(btn_row, text="Cancel", fg_color="#555",
                      hover_color="#444", command=self.destroy).pack(side="right", padx=4)

    def _update_preview(self):
        try:
            dep = float(self._dep_var.get() or 0)
            closing = round(self._opening_nbv - dep, 2)
            acc = round(self._accumulated + dep, 2)
            self._preview_lbl.configure(
                text=f"Closing NBV: ₹{closing:,.2f}  |  Accumulated Dep.: ₹{acc:,.2f}")
        except ValueError:
            self._preview_lbl.configure(text="")

    def _save(self):
        fy = self._fy_var.get().strip()
        date = self._date_var.get().strip()
        if not fy:
            messagebox.showwarning("Validation", "Financial Year is required.", parent=self)
            return
        try:
            dep = float(self._dep_var.get())
        except ValueError:
            messagebox.showwarning("Validation", "Depreciation Amount must be a number.", parent=self)
            return
        closing = round(self._opening_nbv - dep, 2)
        accumulated = round(self._accumulated + dep, 2)
        try:
            db.record_depreciation(self.asset_id, fy, self._opening_nbv, dep,
                                   accumulated, closing, date,
                                   self._notes_var.get().strip())
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)
            return
        if self.on_save:
            self.on_save()
        self.destroy()


class AssetDisposalDialog(ctk.CTkToplevel):
    def __init__(self, parent, asset_id, on_save=None):
        super().__init__(parent)
        self.asset_id = asset_id
        self.on_save = on_save
        self.title("Dispose Asset")
        self.geometry("440x340")
        self.resizable(False, False)
        self.grab_set()

        _row = db.get_asset(asset_id)
        self.asset = dict(_row) if _row else {}

        frm = ctk.CTkFrame(self, fg_color="transparent")
        frm.pack(fill="both", expand=True, padx=16, pady=12)

        ctk.CTkLabel(frm, text=f"Disposing: {self.asset.get('asset_code', '')} – {self.asset.get('name', '')}",
                     font=ctk.CTkFont(size=13, weight="bold"), wraplength=400).pack(anchor="w", pady=(0, 6))
        ctk.CTkLabel(frm, text=f"Purchase Cost: ₹{self.asset.get('purchase_cost', 0):,.2f}",
                     font=ctk.CTkFont(size=11), text_color=COLORS["text_dim"]).pack(anchor="w", pady=(0, 10))

        def _lbl(text): ctk.CTkLabel(frm, text=text, font=ctk.CTkFont(size=11),
                                     text_color=COLORS["text_dim"]).pack(anchor="w")
        def _ent(var): e = ctk.CTkEntry(frm, textvariable=var, width=300); e.pack(anchor="w", pady=(0, 8)); return e

        _lbl("Disposal Date (YYYY-MM-DD) *")
        self._date_var = ctk.StringVar(value=datetime.today().strftime("%Y-%m-%d"))
        _ent(self._date_var)

        _lbl("Disposal Value (₹) *")
        self._val_var = ctk.StringVar(value="0")
        _ent(self._val_var)

        _lbl("Reason / Notes")
        self._notes_var = ctk.StringVar(value="")
        _ent(self._notes_var)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=8)
        ctk.CTkButton(btn_row, text="Confirm Disposal", fg_color=COLORS["danger"],
                      hover_color="#c0392b", command=self._save).pack(side="right", padx=4)
        ctk.CTkButton(btn_row, text="Cancel", fg_color="#555",
                      hover_color="#444", command=self.destroy).pack(side="right", padx=4)

    def _save(self):
        date = self._date_var.get().strip()
        if not date:
            messagebox.showwarning("Validation", "Disposal Date is required.", parent=self)
            return
        try:
            val = float(self._val_var.get() or 0)
        except ValueError:
            messagebox.showwarning("Validation", "Disposal Value must be a number.", parent=self)
            return
        if not messagebox.askyesno("Confirm", f"Mark this asset as Disposed with value ₹{val:,.2f}?", parent=self):
            return
        db.dispose_asset(self.asset_id, date, val, self._notes_var.get().strip())
        if self.on_save:
            self.on_save()
        self.destroy()


# ── Payroll Management ────────────────────────────────────────────────────────

_MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]


class PayrollPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._header("👷  Payroll Management",
                     "Manage employees, process monthly payroll, and track salary payments")

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=20, pady=(0, 8))
        ctk.CTkButton(toolbar, text="+ Add Employee", fg_color="#1a5276",
                      hover_color="#2980b9", command=self._add_employee).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="⚙ Process Payroll", fg_color="#6c3483",
                      hover_color="#7d3c98", command=self._process_payroll).pack(side="left", padx=4)

        # KPI bar
        summary = db.get_employee_summary()
        kpi_row = ctk.CTkFrame(self, fg_color="transparent")
        kpi_row.pack(fill="x", padx=20, pady=(0, 10))
        kpis = [
            ("Total Employees", str(summary.get("total", 0)), COLORS["accent"]),
            ("Active", str(summary.get("active", 0)), COLORS["success"]),
            ("Monthly CTC", f"₹{summary.get('monthly_ctc', 0):,.0f}", "#8e44ad"),
        ]
        for label, val, color in kpis:
            card = self._card(kpi_row, pad=False)
            card.pack(side="left", fill="x", expand=True, padx=4, pady=2)
            ctk.CTkLabel(card, text=val, font=ctk.CTkFont(size=20, weight="bold"),
                         text_color=color).pack(pady=(8, 0))
            ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=10),
                         text_color=COLORS["text_dim"]).pack(pady=(0, 8))

        self._tabs = ctk.CTkTabview(self)
        self._tabs.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        self._tabs.add("👤  Employees")
        self._tabs.add("💰  Payroll Register")

        self._build_employees_tab(self._tabs.tab("👤  Employees"))
        self._build_register_tab(self._tabs.tab("💰  Payroll Register"))

    def _build_employees_tab(self, parent):
        # Status filter
        fb = ctk.CTkFrame(parent, fg_color="transparent")
        fb.pack(fill="x", pady=(4, 6))
        ctk.CTkLabel(fb, text="Status:", font=ctk.CTkFont(size=11)).pack(side="left", padx=(4, 2))
        self._emp_status_var = ctk.StringVar(value="Active")
        ctk.CTkOptionMenu(fb, variable=self._emp_status_var,
                          values=["All", "Active", "Resigned", "Terminated"], width=130,
                          command=lambda _: self._refresh_employees()).pack(side="left")

        self._emp_scroll = ctk.CTkScrollableFrame(parent)
        self._emp_scroll.pack(fill="both", expand=True, pady=(2, 0))
        self._refresh_employees()

    def _refresh_employees(self):
        for w in self._emp_scroll.winfo_children():
            w.destroy()
        status = self._emp_status_var.get()
        emps = [dict(r) for r in db.get_all_employees(status=None if status == "All" else status)]

        hdrs  = ["Code", "Name", "Designation", "Department", "Basic", "Gross CTC", "PF", "ESI", "Status", "Actions"]
        widths = [70, 160, 140, 120, 90, 90, 40, 40, 80, 120]
        hdr_row = ctk.CTkFrame(self._emp_scroll, fg_color="#1a3a5c")
        hdr_row.pack(fill="x", pady=(0, 2))
        for h, w in zip(hdrs, widths):
            ctk.CTkLabel(hdr_row, text=h, font=ctk.CTkFont(size=11, weight="bold"),
                         width=w, anchor="w").pack(side="left", padx=4, pady=4)

        if not emps:
            ctk.CTkLabel(self._emp_scroll, text="No employees found.",
                         text_color=COLORS["text_dim"]).pack(pady=20)
            return

        for e in emps:
            gross = e["basic"] + e["hra"] + e["da"] + e["special_allowance"] + e["other_allowance"]
            row = ctk.CTkFrame(self._emp_scroll, fg_color=COLORS["card_bg"], corner_radius=4)
            row.pack(fill="x", pady=1)
            vals = [
                e["emp_code"], e["name"], e.get("designation", ""), e.get("department", ""),
                f"₹{e['basic']:,.0f}", f"₹{gross:,.0f}",
                "✓" if e["pf_applicable"] else "–",
                "✓" if e["esi_applicable"] else "–",
                e["status"],
            ]
            stat_colors = {"Active": COLORS["success"], "Resigned": COLORS["warning"],
                           "Terminated": COLORS["danger"]}
            row_colors = [COLORS["text"]] * len(vals)
            row_colors[8] = stat_colors.get(e["status"], COLORS["text"])
            for val, w, col in zip(vals, widths, row_colors):
                ctk.CTkLabel(row, text=str(val), font=ctk.CTkFont(size=11),
                             width=w, anchor="w", text_color=col).pack(side="left", padx=4, pady=5)
            act = ctk.CTkFrame(row, fg_color="transparent")
            act.pack(side="left", padx=4)
            eid = e["id"]
            ctk.CTkButton(act, text="Edit", width=48, height=24, fg_color="#1a5276",
                          hover_color="#2980b9", font=ctk.CTkFont(size=10),
                          command=lambda x=eid: self._edit_employee(x)).pack(side="left", padx=2)
            ctk.CTkButton(act, text="History", width=58, height=24, fg_color="#2c3e50",
                          hover_color="#34495e", font=ctk.CTkFont(size=10),
                          command=lambda x=eid: self._view_history(x)).pack(side="left", padx=2)

    def _build_register_tab(self, parent):
        # Month/year selector
        fb = ctk.CTkFrame(parent, fg_color="transparent")
        fb.pack(fill="x", pady=(4, 6))
        ctk.CTkLabel(fb, text="Month:", font=ctk.CTkFont(size=11)).pack(side="left", padx=(4, 2))
        today = datetime.today()
        self._reg_month_var = ctk.StringVar(value=_MONTH_NAMES[today.month - 1])
        ctk.CTkOptionMenu(fb, variable=self._reg_month_var, values=_MONTH_NAMES, width=80,
                          command=lambda _: self._refresh_register()).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(fb, text="Year:", font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 2))
        years = [str(y) for y in range(today.year - 2, today.year + 2)]
        self._reg_year_var = ctk.StringVar(value=str(today.year))
        ctk.CTkOptionMenu(fb, variable=self._reg_year_var, values=years, width=80,
                          command=lambda _: self._refresh_register()).pack(side="left")

        self._reg_scroll = ctk.CTkScrollableFrame(parent)
        self._reg_scroll.pack(fill="both", expand=True, pady=(2, 0))
        self._refresh_register()

    def _refresh_register(self):
        for w in self._reg_scroll.winfo_children():
            w.destroy()
        month = _MONTH_NAMES.index(self._reg_month_var.get()) + 1
        year  = int(self._reg_year_var.get())
        rows  = [dict(r) for r in db.get_payroll_month(month, year)]

        hdrs  = ["Code", "Name", "Dept", "Days", "Gross", "Deductions", "Net Pay", "Status", "Actions"]
        widths = [70, 160, 100, 55, 100, 110, 100, 80, 130]
        hdr_row = ctk.CTkFrame(self._reg_scroll, fg_color="#1a3a5c")
        hdr_row.pack(fill="x", pady=(0, 2))
        for h, w in zip(hdrs, widths):
            ctk.CTkLabel(hdr_row, text=h, font=ctk.CTkFont(size=11, weight="bold"),
                         width=w, anchor="w").pack(side="left", padx=4, pady=4)

        if not rows:
            ctk.CTkLabel(self._reg_scroll, text=f"No payroll processed for {self._reg_month_var.get()} {year}. "
                                                 "Click '⚙ Process Payroll' to generate.",
                         text_color=COLORS["text_dim"]).pack(pady=20)
            return

        total_net = 0
        for r in rows:
            row = ctk.CTkFrame(self._reg_scroll, fg_color=COLORS["card_bg"], corner_radius=4)
            row.pack(fill="x", pady=1)
            stat_color = {"Paid": COLORS["success"], "Processed": COLORS["warning"],
                          "Draft": COLORS["text_dim"]}.get(r["status"], COLORS["text_dim"])
            vals = [
                r["emp_code"], r["name"], r.get("department", ""),
                f"{r['present_days']:.0f}/{r['working_days']:.0f}",
                f"₹{r['gross_earnings']:,.0f}",
                f"₹{r['total_deductions']:,.0f}",
                f"₹{r['net_pay']:,.0f}",
                r["status"],
            ]
            vcolors = [COLORS["text"]] * len(vals)
            vcolors[7] = stat_color
            for val, w, col in zip(vals, widths, vcolors):
                ctk.CTkLabel(row, text=str(val), font=ctk.CTkFont(size=11),
                             width=w, anchor="w", text_color=col).pack(side="left", padx=4, pady=5)
            act = ctk.CTkFrame(row, fg_color="transparent")
            act.pack(side="left", padx=4)
            rid = r["id"]
            ctk.CTkButton(act, text="Payslip", width=58, height=24, fg_color="#1a5276",
                          hover_color="#2980b9", font=ctk.CTkFont(size=10),
                          command=lambda x=rid: self._view_payslip(x)).pack(side="left", padx=2)
            if r["status"] != "Paid":
                ctk.CTkButton(act, text="Mark Paid", width=68, height=24, fg_color=COLORS["success"],
                              hover_color="#27ae60", font=ctk.CTkFont(size=10),
                              command=lambda x=rid: self._mark_paid(x)).pack(side="left", padx=2)
            total_net += r["net_pay"]

        # Total row
        tot = ctk.CTkFrame(self._reg_scroll, fg_color="#1a3a5c", corner_radius=4)
        tot.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(tot, text=f"Total Net Pay: ₹{total_net:,.2f}",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=COLORS["success"]).pack(side="right", padx=16, pady=6)

    def _add_employee(self):
        EmployeeDialog(self, on_save=self.refresh)

    def _edit_employee(self, emp_id):
        EmployeeDialog(self, emp_id=emp_id, on_save=self.refresh)

    def _view_history(self, emp_id):
        PayrollHistoryDialog(self, emp_id=emp_id)

    def _view_payslip(self, payroll_id):
        PayslipDialog(self, payroll_id=payroll_id)

    def _mark_paid(self, payroll_id):
        d = ctk.CTkToplevel(self)
        d.title("Mark as Paid")
        d.geometry("360x200")
        d.grab_set()
        frm = ctk.CTkFrame(d, fg_color="transparent")
        frm.pack(fill="both", expand=True, padx=16, pady=12)
        ctk.CTkLabel(frm, text="Payment Date (YYYY-MM-DD)").pack(anchor="w")
        date_var = ctk.StringVar(value=datetime.today().strftime("%Y-%m-%d"))
        ctk.CTkEntry(frm, textvariable=date_var, width=280).pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(frm, text="Payment Reference / UTR").pack(anchor="w")
        ref_var = ctk.StringVar()
        ctk.CTkEntry(frm, textvariable=ref_var, width=280).pack(anchor="w", pady=(0, 8))
        def _do():
            db.mark_payroll_paid(payroll_id, date_var.get().strip(), ref_var.get().strip())
            d.destroy()
            self._refresh_register()
        ctk.CTkButton(frm, text="Confirm Payment", fg_color=COLORS["success"],
                      hover_color="#27ae60", command=_do).pack(pady=8)

    def _process_payroll(self):
        PayrollProcessDialog(self, on_save=self.refresh)

    def refresh(self):
        self._refresh_employees()
        self._refresh_register()


class EmployeeDialog(ctk.CTkToplevel):
    def __init__(self, parent, emp_id=None, on_save=None):
        super().__init__(parent)
        self.emp_id = emp_id
        self.on_save = on_save
        self.title("Edit Employee" if emp_id else "Add Employee")
        self.geometry("720x700")
        self.resizable(False, False)
        self.grab_set()

        _row = db.get_employee(emp_id) if emp_id else None
        ex = dict(_row) if _row else {}

        scroll = ctk.CTkScrollableFrame(self)
        scroll.pack(fill="both", expand=True, padx=16, pady=12)
        scroll.columnconfigure(0, weight=1)
        scroll.columnconfigure(1, weight=1)
        scroll.columnconfigure(2, weight=1)

        def _lbl(text, r, c): ctk.CTkLabel(scroll, text=text, font=ctk.CTkFont(size=11),
                                            text_color=COLORS["text_dim"]).grid(row=r*2, column=c, sticky="w", padx=6, pady=(6,0))
        def _ent(r, c, val="", width=210, colspan=1):
            var = ctk.StringVar(value=val)
            ctk.CTkEntry(scroll, textvariable=var, width=width if colspan==1 else width*colspan+10
                        ).grid(row=r*2+1, column=c, columnspan=colspan, sticky="ew", padx=6, pady=(0,2))
            return var

        _lbl("Employee Code *", 0, 0); self._code_var = _ent(0, 0, ex.get("emp_code", db.next_emp_code()))
        _lbl("Full Name *", 0, 1); self._name_var = _ent(0, 1, ex.get("name", ""), colspan=2)

        _lbl("Designation", 1, 0); self._desig_var = _ent(1, 0, ex.get("designation", ""))
        _lbl("Department", 1, 1); self._dept_var  = _ent(1, 1, ex.get("department", ""))
        _lbl("Joining Date (YYYY-MM-DD)", 1, 2); self._jdate_var = _ent(1, 2, ex.get("joining_date", ""))

        _lbl("Date of Birth (YYYY-MM-DD)", 2, 0); self._dob_var  = _ent(2, 0, ex.get("dob", ""))
        _lbl("PAN", 2, 1); self._pan_var  = _ent(2, 1, ex.get("pan", ""))
        _lbl("UAN (PF)", 2, 2); self._uan_var  = _ent(2, 2, ex.get("uan", ""))

        ctk.CTkLabel(scroll, text="── Salary Structure ──────────────────────────",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color=COLORS["text_dim"]
                    ).grid(row=6, column=0, columnspan=3, sticky="w", padx=6, pady=(10, 0))

        _lbl("Basic (₹) *", 4, 0); self._basic_var = _ent(4, 0, str(ex.get("basic", "")))
        _lbl("HRA (₹)", 4, 1); self._hra_var   = _ent(4, 1, str(ex.get("hra", "0")))
        _lbl("DA (₹)", 4, 2); self._da_var    = _ent(4, 2, str(ex.get("da", "0")))
        _lbl("Special Allowance (₹)", 5, 0); self._sa_var = _ent(5, 0, str(ex.get("special_allowance", "0")))
        _lbl("Other Allowance (₹)", 5, 1); self._oa_var = _ent(5, 1, str(ex.get("other_allowance", "0")))
        _lbl("TDS/Month (₹)", 5, 2); self._tds_var = _ent(5, 2, str(ex.get("tds_monthly", "0")))

        ctk.CTkLabel(scroll, text="── Deduction Applicability ───────────────────",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color=COLORS["text_dim"]
                    ).grid(row=12, column=0, columnspan=3, sticky="w", padx=6, pady=(10, 0))

        self._pf_var  = ctk.BooleanVar(value=bool(ex.get("pf_applicable", 1)))
        self._esi_var = ctk.BooleanVar(value=bool(ex.get("esi_applicable", 1)))
        self._pt_var  = ctk.BooleanVar(value=bool(ex.get("pt_applicable", 1)))
        chk_row = ctk.CTkFrame(scroll, fg_color="transparent")
        chk_row.grid(row=13, column=0, columnspan=3, sticky="w", padx=6, pady=(0, 6))
        ctk.CTkCheckBox(chk_row, text="PF (12% of Basic)", variable=self._pf_var).pack(side="left", padx=8)
        ctk.CTkCheckBox(chk_row, text="ESI (0.75% if Gross ≤ ₹21,000)", variable=self._esi_var).pack(side="left", padx=8)
        ctk.CTkCheckBox(chk_row, text="Professional Tax", variable=self._pt_var).pack(side="left", padx=8)

        ctk.CTkLabel(scroll, text="── Bank Details ──────────────────────────────",
                     font=ctk.CTkFont(size=11, weight="bold"), text_color=COLORS["text_dim"]
                    ).grid(row=14, column=0, columnspan=3, sticky="w", padx=6, pady=(10, 0))
        _lbl("Bank Account No.", 8, 0); self._bacc_var  = _ent(8, 0, ex.get("bank_account", ""))
        _lbl("Bank Name", 8, 1); self._bname_var = _ent(8, 1, ex.get("bank_name", ""))
        _lbl("IFSC Code", 8, 2); self._ifsc_var  = _ent(8, 2, ex.get("ifsc", ""))

        if emp_id:
            ctk.CTkLabel(scroll, text="Status", font=ctk.CTkFont(size=11),
                         text_color=COLORS["text_dim"]).grid(row=18, column=0, sticky="w", padx=6, pady=(6,0))
            self._status_var = ctk.StringVar(value=ex.get("status", "Active"))
            ctk.CTkOptionMenu(scroll, variable=self._status_var,
                              values=["Active", "Resigned", "Terminated"], width=160
                             ).grid(row=19, column=0, sticky="ew", padx=6)
        else:
            self._status_var = ctk.StringVar(value="Active")

        ctk.CTkLabel(scroll, text="Notes", font=ctk.CTkFont(size=11),
                     text_color=COLORS["text_dim"]).grid(row=20, column=0, sticky="w", padx=6, pady=(6,0))
        self._notes_box = ctk.CTkTextbox(scroll, height=50)
        self._notes_box.grid(row=21, column=0, columnspan=3, sticky="ew", padx=6, pady=(0, 8))
        self._notes_box.insert("0.0", ex.get("notes", ""))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=8)
        ctk.CTkButton(btn_row, text="Save Employee", fg_color=COLORS["success"],
                      hover_color="#27ae60", command=self._save).pack(side="right", padx=4)
        ctk.CTkButton(btn_row, text="Cancel", fg_color="#555",
                      hover_color="#444", command=self.destroy).pack(side="right", padx=4)

    def _save(self):
        code = self._code_var.get().strip()
        name = self._name_var.get().strip()
        if not code or not name:
            messagebox.showwarning("Validation", "Employee Code and Name are required.", parent=self)
            return
        try:
            basic = float(self._basic_var.get() or 0)
            hra   = float(self._hra_var.get() or 0)
            da    = float(self._da_var.get() or 0)
            sa    = float(self._sa_var.get() or 0)
            oa    = float(self._oa_var.get() or 0)
            tds   = float(self._tds_var.get() or 0)
        except ValueError:
            messagebox.showwarning("Validation", "Salary fields must be numeric.", parent=self)
            return
        notes = self._notes_box.get("0.0", "end").strip()
        args_base = (code, name, self._desig_var.get().strip(), self._dept_var.get().strip(),
                     self._jdate_var.get().strip(), self._dob_var.get().strip(),
                     self._pan_var.get().strip(), self._uan_var.get().strip(),
                     self._bacc_var.get().strip(), self._bname_var.get().strip(),
                     self._ifsc_var.get().strip(),
                     basic, hra, da, sa, oa,
                     int(self._pf_var.get()), int(self._esi_var.get()), int(self._pt_var.get()),
                     tds)
        try:
            if self.emp_id:
                db.update_employee(self.emp_id, *args_base, self._status_var.get(), notes)
            else:
                db.add_employee(*args_base, notes)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)
            return
        if self.on_save:
            self.on_save()
        self.destroy()


class PayrollProcessDialog(ctk.CTkToplevel):
    """Process payroll for a selected month — one row per active employee."""
    def __init__(self, parent, on_save=None):
        super().__init__(parent)
        self.on_save = on_save
        self.title("Process Payroll")
        self.geometry("900x620")
        self.grab_set()

        today = datetime.today()
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(10, 4))
        ctk.CTkLabel(hdr, text="Month:", font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self._month_var = ctk.StringVar(value=_MONTH_NAMES[today.month - 1])
        ctk.CTkOptionMenu(hdr, variable=self._month_var, values=_MONTH_NAMES, width=80).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(hdr, text="Year:", font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        years = [str(y) for y in range(today.year - 2, today.year + 2)]
        self._year_var = ctk.StringVar(value=str(today.year))
        ctk.CTkOptionMenu(hdr, variable=self._year_var, values=years, width=80).pack(side="left", padx=(0, 12))
        ctk.CTkLabel(hdr, text="Working Days:", font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
        self._wdays_var = ctk.StringVar(value="26")
        ctk.CTkEntry(hdr, textvariable=self._wdays_var, width=50).pack(side="left", padx=(0, 8))
        ctk.CTkButton(hdr, text="Load Employees", fg_color="#1a5276", hover_color="#2980b9",
                      command=self._load).pack(side="left", padx=4)

        self._scroll = ctk.CTkScrollableFrame(self)
        self._scroll.pack(fill="both", expand=True, padx=16, pady=4)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=8)
        ctk.CTkButton(btn_row, text="Process & Save All", fg_color=COLORS["success"],
                      hover_color="#27ae60", command=self._save_all).pack(side="right", padx=4)
        ctk.CTkButton(btn_row, text="Cancel", fg_color="#555",
                      hover_color="#444", command=self.destroy).pack(side="right", padx=4)

        self._rows = []  # list of (emp_dict, present_var, advance_var, other_ded_var)
        self._load()

    def _load(self):
        for w in self._scroll.winfo_children():
            w.destroy()
        self._rows = []
        try:
            wdays = float(self._wdays_var.get())
        except ValueError:
            wdays = 26.0
        emps = [dict(r) for r in db.get_all_employees(status="Active")]
        if not emps:
            ctk.CTkLabel(self._scroll, text="No active employees.",
                         text_color=COLORS["text_dim"]).pack(pady=20)
            return

        hdrs   = ["Code", "Name", "Gross CTC", "Present Days", "Advance (₹)", "Other Ded (₹)", "Net Pay (est.)"]
        widths = [70, 180, 100, 100, 100, 100, 110]
        hdr_row = ctk.CTkFrame(self._scroll, fg_color="#1a3a5c")
        hdr_row.pack(fill="x", pady=(0, 2))
        for h, w in zip(hdrs, widths):
            ctk.CTkLabel(hdr_row, text=h, font=ctk.CTkFont(size=11, weight="bold"),
                         width=w, anchor="w").pack(side="left", padx=4, pady=4)

        for e in emps:
            gross_ctc = e["basic"] + e["hra"] + e["da"] + e["special_allowance"] + e["other_allowance"]
            row = ctk.CTkFrame(self._scroll, fg_color=COLORS["card_bg"], corner_radius=4)
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=e["emp_code"], width=widths[0], anchor="w",
                         font=ctk.CTkFont(size=11)).pack(side="left", padx=4, pady=5)
            ctk.CTkLabel(row, text=e["name"], width=widths[1], anchor="w",
                         font=ctk.CTkFont(size=11)).pack(side="left", padx=4, pady=5)
            ctk.CTkLabel(row, text=f"₹{gross_ctc:,.0f}", width=widths[2], anchor="w",
                         font=ctk.CTkFont(size=11)).pack(side="left", padx=4, pady=5)
            pres_var = ctk.StringVar(value=str(wdays))
            adv_var  = ctk.StringVar(value="0")
            oth_var  = ctk.StringVar(value="0")
            ctk.CTkEntry(row, textvariable=pres_var, width=widths[3]-8).pack(side="left", padx=4)
            ctk.CTkEntry(row, textvariable=adv_var,  width=widths[4]-8).pack(side="left", padx=4)
            ctk.CTkEntry(row, textvariable=oth_var,  width=widths[5]-8).pack(side="left", padx=4)
            net_lbl = ctk.CTkLabel(row, text="–", width=widths[6], anchor="w",
                                   font=ctk.CTkFont(size=11), text_color=COLORS["success"])
            net_lbl.pack(side="left", padx=4)

            def _update(e=e, pv=pres_var, av=adv_var, ov=oth_var, nl=net_lbl, wd=wdays):
                try:
                    calc = db.calculate_payroll(e, wd, float(pv.get() or wd),
                                                float(av.get() or 0), float(ov.get() or 0))
                    nl.configure(text=f"₹{calc['net_pay']:,.0f}")
                except Exception:
                    nl.configure(text="–")

            pres_var.trace_add("write", lambda *_, f=_update: f())
            adv_var.trace_add("write",  lambda *_, f=_update: f())
            oth_var.trace_add("write",  lambda *_, f=_update: f())
            _update()
            self._rows.append((e, pres_var, adv_var, oth_var, wdays))

    def _save_all(self):
        month = _MONTH_NAMES.index(self._month_var.get()) + 1
        year  = int(self._year_var.get())
        try:
            wdays = float(self._wdays_var.get())
        except ValueError:
            wdays = 26.0
        saved = 0
        for e, pres_var, adv_var, oth_var, _wd in self._rows:
            try:
                pres = float(pres_var.get() or wdays)
                adv  = float(adv_var.get() or 0)
                oth  = float(oth_var.get() or 0)
                calc = db.calculate_payroll(e, wdays, pres, adv, oth)
                db.save_payroll(e["id"], month, year, wdays, pres, calc, status="Processed")
                saved += 1
            except Exception as ex:
                pass
        messagebox.showinfo("Done", f"Payroll processed for {saved} employee(s).", parent=self)
        if self.on_save:
            self.on_save()
        self.destroy()


class PayslipDialog(ctk.CTkToplevel):
    def __init__(self, parent, payroll_id):
        super().__init__(parent)
        self.title("Payslip")
        self.geometry("500x600")
        self.resizable(False, False)
        self.grab_set()

        with db.get_connection() as conn:
            row = conn.execute("""
                SELECT pm.*, e.name, e.emp_code, e.designation, e.department,
                       e.pan, e.bank_account, e.bank_name, e.uan
                FROM payroll_months pm
                JOIN employees e ON e.id=pm.employee_id
                WHERE pm.id=?
            """, (payroll_id,)).fetchone()
        if not row:
            ctk.CTkLabel(self, text="Record not found.").pack(pady=20)
            return
        r = dict(row)

        scroll = ctk.CTkScrollableFrame(self)
        scroll.pack(fill="both", expand=True, padx=16, pady=12)

        def _section(text):
            ctk.CTkLabel(scroll, text=text, font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=COLORS["accent_light"]).pack(anchor="w", pady=(10, 2))
            ctk.CTkFrame(scroll, height=1, fg_color="#444").pack(fill="x", pady=(0, 4))

        def _row2(label, val, color=COLORS["text"]):
            fr = ctk.CTkFrame(scroll, fg_color="transparent")
            fr.pack(fill="x")
            ctk.CTkLabel(fr, text=label, font=ctk.CTkFont(size=11),
                         text_color=COLORS["text_dim"], width=200, anchor="w").pack(side="left")
            ctk.CTkLabel(fr, text=str(val), font=ctk.CTkFont(size=11),
                         text_color=color, anchor="e").pack(side="right")

        ctk.CTkLabel(scroll, text="PAYSLIP", font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=COLORS["accent_light"]).pack(anchor="center", pady=(0, 4))
        mname = _MONTH_NAMES[r["month"] - 1]
        ctk.CTkLabel(scroll, text=f"{mname} {r['year']}",
                     font=ctk.CTkFont(size=13), text_color=COLORS["text_dim"]).pack(anchor="center")

        _section("Employee Details")
        _row2("Employee Code", r["emp_code"])
        _row2("Name", r["name"])
        _row2("Designation", r.get("designation", ""))
        _row2("Department", r.get("department", ""))
        _row2("PAN", r.get("pan", ""))
        _row2("Bank Account", r.get("bank_account", ""))
        _row2("UAN", r.get("uan", ""))

        _section("Attendance")
        _row2("Working Days", f"{r['working_days']:.0f}")
        _row2("Days Present", f"{r['present_days']:.0f}")
        _row2("LOP Days", f"{r['lop_days']:.0f}")

        _section("Earnings")
        _row2("Basic", f"₹{r['basic_earned']:,.2f}")
        _row2("HRA", f"₹{r['hra_earned']:,.2f}")
        _row2("DA", f"₹{r['da_earned']:,.2f}")
        _row2("Special Allowance", f"₹{r['special_allowance_earned']:,.2f}")
        _row2("Other Allowance", f"₹{r['other_allowance_earned']:,.2f}")
        ctk.CTkFrame(scroll, height=1, fg_color="#444").pack(fill="x", pady=2)
        _row2("Gross Earnings", f"₹{r['gross_earnings']:,.2f}", COLORS["success"])

        _section("Deductions")
        _row2("PF (Employee 12%)", f"₹{r['pf_employee']:,.2f}")
        _row2("ESI (Employee 0.75%)", f"₹{r['esi_employee']:,.2f}")
        _row2("Professional Tax", f"₹{r['pt_deduction']:,.2f}")
        _row2("TDS", f"₹{r['tds_deduction']:,.2f}")
        _row2("Advance Deduction", f"₹{r['advance_deduction']:,.2f}")
        _row2("Other Deductions", f"₹{r['other_deductions']:,.2f}")
        ctk.CTkFrame(scroll, height=1, fg_color="#444").pack(fill="x", pady=2)
        _row2("Total Deductions", f"₹{r['total_deductions']:,.2f}", COLORS["danger"])

        ctk.CTkFrame(scroll, height=2, fg_color=COLORS["accent_light"]).pack(fill="x", pady=6)
        fr_net = ctk.CTkFrame(scroll, fg_color=COLORS["card_bg"], corner_radius=6)
        fr_net.pack(fill="x", pady=4)
        ctk.CTkLabel(fr_net, text="NET PAY", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=12, pady=10)
        ctk.CTkLabel(fr_net, text=f"₹{r['net_pay']:,.2f}",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=COLORS["success"]).pack(side="right", padx=12)

        ctk.CTkButton(self, text="Close", fg_color="#555", hover_color="#444",
                      command=self.destroy).pack(pady=8)


class PayrollHistoryDialog(ctk.CTkToplevel):
    def __init__(self, parent, emp_id):
        super().__init__(parent)
        _row = db.get_employee(emp_id)
        emp = dict(_row) if _row else {}
        self.title(f"Payroll History — {emp.get('name', '')}")
        self.geometry("660x480")
        self.grab_set()

        ctk.CTkLabel(self, text=f"{emp.get('emp_code', '')}  {emp.get('name', '')}",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=16, pady=(10, 4))

        scroll = ctk.CTkScrollableFrame(self)
        scroll.pack(fill="both", expand=True, padx=16, pady=4)

        hdrs   = ["Month", "Year", "Days", "Gross", "Deductions", "Net Pay", "Status"]
        widths = [60, 60, 55, 110, 120, 110, 80]
        hdr_row = ctk.CTkFrame(scroll, fg_color="#1a3a5c")
        hdr_row.pack(fill="x", pady=(0, 2))
        for h, w in zip(hdrs, widths):
            ctk.CTkLabel(hdr_row, text=h, font=ctk.CTkFont(size=11, weight="bold"),
                         width=w, anchor="w").pack(side="left", padx=4, pady=4)

        history = [dict(r) for r in db.get_employee_payroll_history(emp_id)]
        if not history:
            ctk.CTkLabel(scroll, text="No payroll records found.",
                         text_color=COLORS["text_dim"]).pack(pady=20)
        for h in history:
            row = ctk.CTkFrame(scroll, fg_color=COLORS["card_bg"], corner_radius=4)
            row.pack(fill="x", pady=1)
            stat_color = {"Paid": COLORS["success"], "Processed": COLORS["warning"],
                          "Draft": COLORS["text_dim"]}.get(h["status"], COLORS["text_dim"])
            vals = [_MONTH_NAMES[h["month"]-1], str(h["year"]),
                    f"{h['present_days']:.0f}/{h['working_days']:.0f}",
                    f"₹{h['gross_earnings']:,.2f}", f"₹{h['total_deductions']:,.2f}",
                    f"₹{h['net_pay']:,.2f}", h["status"]]
            vcolors = [COLORS["text"]] * len(vals); vcolors[-1] = stat_color
            for val, w, col in zip(vals, widths, vcolors):
                ctk.CTkLabel(row, text=val, font=ctk.CTkFont(size=11),
                             width=w, anchor="w", text_color=col).pack(side="left", padx=4, pady=5)

        ctk.CTkButton(self, text="Close", fg_color="#555", hover_color="#444",
                      command=self.destroy).pack(pady=8)


# ── Advance Payments ──────────────────────────────────────────────────────────

_PAY_MODES = ["Bank Transfer", "NEFT", "RTGS", "IMPS", "UPI", "Cheque", "Cash", "DD"]


class AdvancePaymentsPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._header("💵  Advance Payments",
                     "Track advances received from customers and paid to vendors")

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=20, pady=(0, 8))
        ctk.CTkButton(toolbar, text="+ Received Advance", fg_color="#1a5276",
                      hover_color="#2980b9",
                      command=lambda: self._add_advance("Received")).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="+ Paid Advance", fg_color="#922b21",
                      hover_color="#a93226",
                      command=lambda: self._add_advance("Paid")).pack(side="left", padx=4)

        summary = db.get_advance_summary()
        kpi_row = ctk.CTkFrame(self, fg_color="transparent")
        kpi_row.pack(fill="x", padx=20, pady=(0, 10))
        kpis = [
            ("Total Received", f"₹{summary.get('total_received', 0):,.0f}", COLORS["success"]),
            ("Open (Received)", f"₹{summary.get('open_received', 0):,.0f}", "#2980b9"),
            ("Total Paid", f"₹{summary.get('total_paid', 0):,.0f}", COLORS["danger"]),
            ("Open (Paid)", f"₹{summary.get('open_paid', 0):,.0f}", COLORS["warning"]),
        ]
        for label, val, color in kpis:
            card = self._card(kpi_row, pad=False)
            card.pack(side="left", fill="x", expand=True, padx=4, pady=2)
            ctk.CTkLabel(card, text=val, font=ctk.CTkFont(size=18, weight="bold"),
                         text_color=color).pack(pady=(8, 0))
            ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=10),
                         text_color=COLORS["text_dim"]).pack(pady=(0, 8))

        self._tabs = ctk.CTkTabview(self)
        self._tabs.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        self._tabs.add("⬇  Received (from Customers)")
        self._tabs.add("⬆  Paid (to Vendors)")

        self._build_tab(self._tabs.tab("⬇  Received (from Customers)"), "Received")
        self._build_tab(self._tabs.tab("⬆  Paid (to Vendors)"), "Paid")

    def _build_tab(self, parent, ptype):
        fb = ctk.CTkFrame(parent, fg_color="transparent")
        fb.pack(fill="x", pady=(4, 6))
        ctk.CTkLabel(fb, text="Status:", font=ctk.CTkFont(size=11)).pack(side="left", padx=(4, 2))
        svar = ctk.StringVar(value="All")
        ctk.CTkOptionMenu(fb, variable=svar,
                          values=["All", "Open", "Partially Adjusted", "Fully Adjusted"],
                          width=170, command=lambda _, p=ptype, v=svar: self._refresh_tab(p, v)).pack(side="left")

        scroll = ctk.CTkScrollableFrame(parent)
        scroll.pack(fill="both", expand=True, pady=(2, 0))

        if ptype == "Received":
            self._recv_scroll = scroll
            self._recv_svar   = svar
        else:
            self._paid_scroll = scroll
            self._paid_svar   = svar

        self._refresh_tab(ptype, svar)

    def _refresh_tab(self, ptype, svar):
        scroll = self._recv_scroll if ptype == "Received" else self._paid_scroll
        for w in scroll.winfo_children():
            w.destroy()
        status = svar.get() if svar.get() != "All" else None
        advances = [dict(r) for r in db.get_all_advances(payment_type=ptype, status=status)]

        hdrs   = ["Advance No.", "Date", "Party", "Amount", "Adjusted", "Balance", "Mode", "Ref", "Status", "Actions"]
        widths = [90, 90, 160, 100, 100, 100, 100, 110, 130, 100]
        hdr_row = ctk.CTkFrame(scroll, fg_color="#1a3a5c")
        hdr_row.pack(fill="x", pady=(0, 2))
        for h, w in zip(hdrs, widths):
            ctk.CTkLabel(hdr_row, text=h, font=ctk.CTkFont(size=11, weight="bold"),
                         width=w, anchor="w").pack(side="left", padx=4, pady=4)

        if not advances:
            ctk.CTkLabel(scroll, text="No records found.", text_color=COLORS["text_dim"]).pack(pady=20)
            return

        for a in advances:
            balance = round(a["amount"] - a["adjusted_amount"], 2)
            stat_color = {
                "Open": COLORS["warning"], "Partially Adjusted": "#2980b9",
                "Fully Adjusted": COLORS["success"]
            }.get(a["status"], COLORS["text_dim"])
            row = ctk.CTkFrame(scroll, fg_color=COLORS["card_bg"], corner_radius=4)
            row.pack(fill="x", pady=1)
            vals = [
                a["advance_no"], a["advance_date"], a["party_name"],
                f"₹{a['amount']:,.0f}", f"₹{a['adjusted_amount']:,.0f}",
                f"₹{balance:,.0f}", a["payment_mode"],
                a.get("bank_ref", "")[:12], a["status"],
            ]
            vcolors = [COLORS["text"]] * len(vals); vcolors[8] = stat_color
            for val, w, col in zip(vals, widths, vcolors):
                ctk.CTkLabel(row, text=str(val), font=ctk.CTkFont(size=11),
                             width=w, anchor="w", text_color=col).pack(side="left", padx=4, pady=5)
            act = ctk.CTkFrame(row, fg_color="transparent")
            act.pack(side="left", padx=4)
            aid = a["id"]
            ctk.CTkButton(act, text="Edit", width=42, height=24, fg_color="#1a5276",
                          hover_color="#2980b9", font=ctk.CTkFont(size=10),
                          command=lambda x=aid: self._edit_advance(x)).pack(side="left", padx=2)
            if a["status"] != "Fully Adjusted":
                ctk.CTkButton(act, text="Adjust", width=48, height=24, fg_color="#6c3483",
                              hover_color="#7d3c98", font=ctk.CTkFont(size=10),
                              command=lambda x=aid, b=balance: self._adjust_advance(x, b)).pack(side="left", padx=2)

    def _add_advance(self, ptype):
        AdvanceDialog(self, payment_type=ptype, on_save=self.refresh)

    def _edit_advance(self, adv_id):
        AdvanceDialog(self, adv_id=adv_id, on_save=self.refresh)

    def _adjust_advance(self, adv_id, balance):
        d = ctk.CTkToplevel(self)
        d.title("Adjust Advance")
        d.geometry("360x200")
        d.grab_set()
        frm = ctk.CTkFrame(d, fg_color="transparent")
        frm.pack(fill="both", expand=True, padx=16, pady=12)
        ctk.CTkLabel(frm, text=f"Available Balance: ₹{balance:,.2f}",
                     font=ctk.CTkFont(size=12), text_color=COLORS["text_dim"]).pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(frm, text="Adjustment Amount (₹)").pack(anchor="w")
        amt_var = ctk.StringVar(value=str(balance))
        ctk.CTkEntry(frm, textvariable=amt_var, width=280).pack(anchor="w", pady=(0, 8))
        def _do():
            try:
                amt = float(amt_var.get())
            except ValueError:
                messagebox.showwarning("Validation", "Enter a valid amount.", parent=d); return
            db.adjust_advance(adv_id, amt)
            d.destroy()
            self.refresh()
        ctk.CTkButton(frm, text="Apply Adjustment", fg_color=COLORS["success"],
                      hover_color="#27ae60", command=_do).pack(pady=8)

    def refresh(self):
        summary = db.get_advance_summary()
        self._refresh_tab("Received", self._recv_svar)
        self._refresh_tab("Paid",     self._paid_svar)


class AdvanceDialog(ctk.CTkToplevel):
    def __init__(self, parent, adv_id=None, payment_type="Received", on_save=None):
        super().__init__(parent)
        self.adv_id = adv_id
        self.on_save = on_save
        self.title("Edit Advance" if adv_id else "New Advance Payment")
        self.geometry("560x500")
        self.resizable(False, False)
        self.grab_set()

        _row = db.get_advance(adv_id) if adv_id else None
        ex = dict(_row) if _row else {}

        frm = ctk.CTkScrollableFrame(self)
        frm.pack(fill="both", expand=True, padx=16, pady=12)
        frm.columnconfigure(0, weight=1)
        frm.columnconfigure(1, weight=1)

        def _lbl(text, r, c): ctk.CTkLabel(frm, text=text, font=ctk.CTkFont(size=11),
                                            text_color=COLORS["text_dim"]).grid(row=r*2, column=c, sticky="w", padx=6, pady=(6,0))
        def _ent(r, c, val="", width=240, colspan=1):
            var = ctk.StringVar(value=val)
            ctk.CTkEntry(frm, textvariable=var, width=width if colspan==1 else width*colspan+10
                        ).grid(row=r*2+1, column=c, columnspan=colspan, sticky="ew", padx=6, pady=(0,2))
            return var

        ctk.CTkLabel(frm, text="Type *", font=ctk.CTkFont(size=11),
                     text_color=COLORS["text_dim"]).grid(row=0, column=0, sticky="w", padx=6, pady=(6,0))
        self._ptype_var = ctk.StringVar(value=ex.get("payment_type", payment_type))
        ctk.CTkOptionMenu(frm, variable=self._ptype_var, values=["Received", "Paid"],
                          width=180).grid(row=1, column=0, sticky="ew", padx=6)

        ctk.CTkLabel(frm, text="Party Type *", font=ctk.CTkFont(size=11),
                     text_color=COLORS["text_dim"]).grid(row=0, column=1, sticky="w", padx=6, pady=(6,0))
        self._party_type_var = ctk.StringVar(value=ex.get("party_type", "Customer"))
        ctk.CTkOptionMenu(frm, variable=self._party_type_var, values=["Customer", "Vendor", "Other"],
                          width=180).grid(row=1, column=1, sticky="ew", padx=6)

        _lbl("Advance No. *", 1, 0); self._ano_var = _ent(1, 0, ex.get("advance_no", db.next_advance_no(payment_type)))
        _lbl("Date (YYYY-MM-DD) *", 1, 1); self._date_var = _ent(1, 1, ex.get("advance_date", datetime.today().strftime("%Y-%m-%d")))

        _lbl("Party Name *", 2, 0); self._party_var = _ent(2, 0, ex.get("party_name", ""), colspan=2)

        _lbl("Amount (₹) *", 3, 0); self._amt_var = _ent(3, 0, str(ex.get("amount", "")))

        ctk.CTkLabel(frm, text="Payment Mode *", font=ctk.CTkFont(size=11),
                     text_color=COLORS["text_dim"]).grid(row=7, column=0, sticky="w", padx=6, pady=(6,0))
        self._mode_var = ctk.StringVar(value=ex.get("payment_mode", "Bank Transfer"))
        ctk.CTkOptionMenu(frm, variable=self._mode_var, values=_PAY_MODES, width=180
                         ).grid(row=8, column=0, sticky="ew", padx=6)

        _lbl("Bank Ref / UTR / Cheque No.", 4, 1); self._ref_var = _ent(4, 1, ex.get("bank_ref", ""))
        _lbl("Linked PO / Invoice Ref", 5, 0); self._linked_var = _ent(5, 0, ex.get("linked_ref", ""), colspan=2)
        _lbl("Narration", 6, 0); self._narr_var = _ent(6, 0, ex.get("narration", ""), colspan=2)

        ctk.CTkLabel(frm, text="Notes", font=ctk.CTkFont(size=11),
                     text_color=COLORS["text_dim"]).grid(row=14, column=0, sticky="w", padx=6, pady=(6,0))
        self._notes_box = ctk.CTkTextbox(frm, height=50)
        self._notes_box.grid(row=15, column=0, columnspan=2, sticky="ew", padx=6, pady=(0,8))
        self._notes_box.insert("0.0", ex.get("notes", ""))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=8)
        ctk.CTkButton(btn_row, text="Save", fg_color=COLORS["success"],
                      hover_color="#27ae60", command=self._save).pack(side="right", padx=4)
        ctk.CTkButton(btn_row, text="Cancel", fg_color="#555",
                      hover_color="#444", command=self.destroy).pack(side="right", padx=4)

    def _save(self):
        ano   = self._ano_var.get().strip()
        date  = self._date_var.get().strip()
        party = self._party_var.get().strip()
        if not ano or not date or not party:
            messagebox.showwarning("Validation", "Advance No., Date, and Party Name are required.", parent=self)
            return
        try:
            amt = float(self._amt_var.get())
        except ValueError:
            messagebox.showwarning("Validation", "Amount must be a number.", parent=self)
            return
        args = (self._ptype_var.get(), self._party_type_var.get(), party, ano, date, amt,
                self._mode_var.get(), self._ref_var.get().strip(),
                self._linked_var.get().strip(), self._narr_var.get().strip(),
                self._notes_box.get("0.0", "end").strip())
        try:
            if self.adv_id:
                db.update_advance(self.adv_id, *args)
            else:
                db.add_advance(*args)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)
            return
        if self.on_save:
            self.on_save()
        self.destroy()


# ── Cheque / PDC Management ───────────────────────────────────────────────────

class ChequePDCPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._header("🏦  Cheque / PDC Management",
                     "Track inward & outward cheques, post-dated cheques, and clearing status")

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=20, pady=(0, 8))
        ctk.CTkButton(toolbar, text="+ Inward Cheque", fg_color="#1a5276",
                      hover_color="#2980b9",
                      command=lambda: self._add_cheque("Inward")).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="+ Outward Cheque", fg_color="#922b21",
                      hover_color="#a93226",
                      command=lambda: self._add_cheque("Outward")).pack(side="left", padx=4)

        summary = db.get_cheque_summary()
        kpi_row = ctk.CTkFrame(self, fg_color="transparent")
        kpi_row.pack(fill="x", padx=20, pady=(0, 10))
        kpis = [
            ("Inward Pending", f"₹{summary.get('inward_pending', 0):,.0f}", COLORS["warning"]),
            ("Inward Cleared", f"₹{summary.get('inward_cleared', 0):,.0f}", COLORS["success"]),
            ("Outward Pending", f"₹{summary.get('outward_pending', 0):,.0f}", COLORS["warning"]),
            ("Bounced", str(summary.get("bounced_count", 0)), COLORS["danger"]),
        ]
        for label, val, color in kpis:
            card = self._card(kpi_row, pad=False)
            card.pack(side="left", fill="x", expand=True, padx=4, pady=2)
            ctk.CTkLabel(card, text=val, font=ctk.CTkFont(size=18, weight="bold"),
                         text_color=color).pack(pady=(8, 0))
            ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=10),
                         text_color=COLORS["text_dim"]).pack(pady=(0, 8))

        self._tabs = ctk.CTkTabview(self)
        self._tabs.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        self._tabs.add("⬇  Inward Cheques")
        self._tabs.add("⬆  Outward Cheques")
        self._tabs.add("📅  Upcoming PDCs")

        self._build_cheque_tab(self._tabs.tab("⬇  Inward Cheques"), "Inward")
        self._build_cheque_tab(self._tabs.tab("⬆  Outward Cheques"), "Outward")
        self._build_upcoming_tab(self._tabs.tab("📅  Upcoming PDCs"))

    def _build_cheque_tab(self, parent, ctype):
        fb = ctk.CTkFrame(parent, fg_color="transparent")
        fb.pack(fill="x", pady=(4, 6))
        ctk.CTkLabel(fb, text="Status:", font=ctk.CTkFont(size=11)).pack(side="left", padx=(4, 2))
        svar = ctk.StringVar(value="All")
        ctk.CTkOptionMenu(fb, variable=svar,
                          values=["All", "Pending", "Presented", "Cleared", "Bounced", "Cancelled"],
                          width=140, command=lambda _, c=ctype, v=svar: self._refresh_tab(c, v)).pack(side="left")

        scroll = ctk.CTkScrollableFrame(parent)
        scroll.pack(fill="both", expand=True, pady=(2, 0))

        if ctype == "Inward":
            self._in_scroll = scroll; self._in_svar = svar
        else:
            self._out_scroll = scroll; self._out_svar = svar

        self._refresh_tab(ctype, svar)

    def _refresh_tab(self, ctype, svar):
        scroll = self._in_scroll if ctype == "Inward" else self._out_scroll
        for w in scroll.winfo_children():
            w.destroy()
        status = svar.get() if svar.get() != "All" else None
        cheques = [dict(r) for r in db.get_all_cheques(cheque_type=ctype, status=status)]

        hdrs   = ["Cheque No.", "Bank", "Party", "Amount", "Cheque Date", "Recv/Issue Date", "Status", "Actions"]
        widths = [100, 130, 160, 100, 100, 110, 100, 180]
        hdr_row = ctk.CTkFrame(scroll, fg_color="#1a3a5c")
        hdr_row.pack(fill="x", pady=(0, 2))
        for h, w in zip(hdrs, widths):
            ctk.CTkLabel(hdr_row, text=h, font=ctk.CTkFont(size=11, weight="bold"),
                         width=w, anchor="w").pack(side="left", padx=4, pady=4)

        if not cheques:
            ctk.CTkLabel(scroll, text="No cheques found.", text_color=COLORS["text_dim"]).pack(pady=20)
            return

        for c in cheques:
            stat_color = {
                "Pending": COLORS["warning"], "Presented": "#2980b9",
                "Cleared": COLORS["success"], "Bounced": COLORS["danger"],
                "Cancelled": COLORS["text_dim"]
            }.get(c["status"], COLORS["text_dim"])
            row = ctk.CTkFrame(scroll, fg_color=COLORS["card_bg"], corner_radius=4)
            row.pack(fill="x", pady=1)
            vals = [
                c["cheque_no"], c["bank_name"], c["party_name"],
                f"₹{c['amount']:,.0f}", c["cheque_date"],
                c.get("received_date", ""), c["status"],
            ]
            vcolors = [COLORS["text"]] * len(vals); vcolors[6] = stat_color
            for val, w, col in zip(vals, widths, vcolors):
                ctk.CTkLabel(row, text=str(val), font=ctk.CTkFont(size=11),
                             width=w, anchor="w", text_color=col).pack(side="left", padx=4, pady=5)
            act = ctk.CTkFrame(row, fg_color="transparent")
            act.pack(side="left", padx=4)
            cid = c["id"]
            ctk.CTkButton(act, text="Edit", width=38, height=24, fg_color="#1a5276",
                          hover_color="#2980b9", font=ctk.CTkFont(size=10),
                          command=lambda x=cid: self._edit_cheque(x)).pack(side="left", padx=2)
            if c["status"] == "Pending":
                ctk.CTkButton(act, text="Present", width=52, height=24, fg_color="#6c3483",
                              hover_color="#7d3c98", font=ctk.CTkFont(size=10),
                              command=lambda x=cid: self._present(x)).pack(side="left", padx=2)
            if c["status"] == "Presented":
                ctk.CTkButton(act, text="Cleared", width=52, height=24, fg_color=COLORS["success"],
                              hover_color="#27ae60", font=ctk.CTkFont(size=10),
                              command=lambda x=cid: self._clear(x)).pack(side="left", padx=2)
                ctk.CTkButton(act, text="Bounced", width=52, height=24, fg_color=COLORS["danger"],
                              hover_color="#c0392b", font=ctk.CTkFont(size=10),
                              command=lambda x=cid: self._bounce(x)).pack(side="left", padx=2)
            if c["status"] in ("Pending", "Presented"):
                ctk.CTkButton(act, text="Cancel", width=46, height=24, fg_color="#555",
                              hover_color="#444", font=ctk.CTkFont(size=10),
                              command=lambda x=cid: self._cancel(x)).pack(side="left", padx=2)

    def _build_upcoming_tab(self, parent):
        ctk.CTkLabel(parent, text="Cheques due in next 30 days (Pending status):",
                     font=ctk.CTkFont(size=11), text_color=COLORS["text_dim"]).pack(anchor="w", pady=(6, 2), padx=4)
        self._upcoming_scroll = ctk.CTkScrollableFrame(parent)
        self._upcoming_scroll.pack(fill="both", expand=True, pady=(2, 0))
        self._refresh_upcoming()

    def _refresh_upcoming(self):
        for w in self._upcoming_scroll.winfo_children():
            w.destroy()
        cheques = [dict(r) for r in db.get_upcoming_cheques(days=30)]
        hdrs   = ["Type", "Cheque No.", "Bank", "Party", "Amount", "Cheque Date", "Days Left"]
        widths = [70, 110, 140, 160, 110, 110, 90]
        hdr_row = ctk.CTkFrame(self._upcoming_scroll, fg_color="#1a3a5c")
        hdr_row.pack(fill="x", pady=(0, 2))
        for h, w in zip(hdrs, widths):
            ctk.CTkLabel(hdr_row, text=h, font=ctk.CTkFont(size=11, weight="bold"),
                         width=w, anchor="w").pack(side="left", padx=4, pady=4)
        if not cheques:
            ctk.CTkLabel(self._upcoming_scroll, text="No upcoming cheques in next 30 days.",
                         text_color=COLORS["text_dim"]).pack(pady=20)
            return
        today = datetime.today().date()
        for c in cheques:
            row = ctk.CTkFrame(self._upcoming_scroll, fg_color=COLORS["card_bg"], corner_radius=4)
            row.pack(fill="x", pady=1)
            try:
                cdate = datetime.strptime(c["cheque_date"], "%Y-%m-%d").date()
                days_left = (cdate - today).days
                days_txt = f"{days_left}d" if days_left >= 0 else "Overdue"
                days_color = COLORS["danger"] if days_left <= 3 else COLORS["warning"] if days_left <= 7 else COLORS["success"]
            except Exception:
                days_txt = "–"; days_color = COLORS["text_dim"]
            type_color = "#2980b9" if c["cheque_type"] == "Inward" else COLORS["danger"]
            vals_colors = [
                (c["cheque_type"], type_color), (c["cheque_no"], COLORS["text"]),
                (c["bank_name"], COLORS["text"]), (c["party_name"], COLORS["text"]),
                (f"₹{c['amount']:,.0f}", COLORS["text"]), (c["cheque_date"], COLORS["text"]),
                (days_txt, days_color),
            ]
            for (val, col), w in zip(vals_colors, widths):
                ctk.CTkLabel(row, text=str(val), font=ctk.CTkFont(size=11),
                             width=w, anchor="w", text_color=col).pack(side="left", padx=4, pady=5)

    def _add_cheque(self, ctype):
        ChequeDialog(self, cheque_type=ctype, on_save=self.refresh)

    def _edit_cheque(self, cheque_id):
        ChequeDialog(self, cheque_id=cheque_id, on_save=self.refresh)

    def _present(self, cheque_id):
        self._date_action(cheque_id, "Mark as Presented", db.present_cheque)

    def _clear(self, cheque_id):
        self._date_action(cheque_id, "Mark as Cleared", db.clear_cheque)

    def _bounce(self, cheque_id):
        d = ctk.CTkToplevel(self)
        d.title("Mark as Bounced")
        d.geometry("380x220")
        d.grab_set()
        frm = ctk.CTkFrame(d, fg_color="transparent")
        frm.pack(fill="both", expand=True, padx=16, pady=12)
        ctk.CTkLabel(frm, text="Bounce Date (YYYY-MM-DD)").pack(anchor="w")
        dvar = ctk.StringVar(value=datetime.today().strftime("%Y-%m-%d"))
        ctk.CTkEntry(frm, textvariable=dvar, width=280).pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(frm, text="Reason").pack(anchor="w")
        rvar = ctk.StringVar(value="Insufficient funds")
        ctk.CTkEntry(frm, textvariable=rvar, width=280).pack(anchor="w", pady=(0, 8))
        def _do():
            db.bounce_cheque(cheque_id, dvar.get().strip(), rvar.get().strip())
            d.destroy(); self.refresh()
        ctk.CTkButton(frm, text="Confirm Bounce", fg_color=COLORS["danger"],
                      hover_color="#c0392b", command=_do).pack(pady=4)

    def _cancel(self, cheque_id):
        if messagebox.askyesno("Cancel Cheque", "Mark this cheque as Cancelled?"):
            db.cancel_cheque(cheque_id)
            self.refresh()

    def _date_action(self, cheque_id, title, fn):
        d = ctk.CTkToplevel(self)
        d.title(title)
        d.geometry("360x160")
        d.grab_set()
        frm = ctk.CTkFrame(d, fg_color="transparent")
        frm.pack(fill="both", expand=True, padx=16, pady=12)
        ctk.CTkLabel(frm, text="Date (YYYY-MM-DD)").pack(anchor="w")
        dvar = ctk.StringVar(value=datetime.today().strftime("%Y-%m-%d"))
        ctk.CTkEntry(frm, textvariable=dvar, width=280).pack(anchor="w", pady=(0, 8))
        def _do():
            fn(cheque_id, dvar.get().strip())
            d.destroy(); self.refresh()
        ctk.CTkButton(frm, text="Confirm", fg_color=COLORS["success"],
                      hover_color="#27ae60", command=_do).pack(pady=4)

    def refresh(self):
        self._refresh_tab("Inward",  self._in_svar)
        self._refresh_tab("Outward", self._out_svar)
        self._refresh_upcoming()


class ChequeDialog(ctk.CTkToplevel):
    def __init__(self, parent, cheque_id=None, cheque_type="Inward", on_save=None):
        super().__init__(parent)
        self.cheque_id = cheque_id
        self.on_save   = on_save
        self.title("Edit Cheque" if cheque_id else "Add Cheque")
        self.geometry("560x480")
        self.resizable(False, False)
        self.grab_set()

        _row = db.get_cheque(cheque_id) if cheque_id else None
        ex = dict(_row) if _row else {}

        frm = ctk.CTkScrollableFrame(self)
        frm.pack(fill="both", expand=True, padx=16, pady=12)
        frm.columnconfigure(0, weight=1)
        frm.columnconfigure(1, weight=1)

        def _lbl(text, r, c): ctk.CTkLabel(frm, text=text, font=ctk.CTkFont(size=11),
                                            text_color=COLORS["text_dim"]).grid(row=r*2, column=c, sticky="w", padx=6, pady=(6,0))
        def _ent(r, c, val="", colspan=1):
            var = ctk.StringVar(value=val)
            ctk.CTkEntry(frm, textvariable=var, width=240 if colspan==1 else 490
                        ).grid(row=r*2+1, column=c, columnspan=colspan, sticky="ew", padx=6, pady=(0,2))
            return var

        ctk.CTkLabel(frm, text="Cheque Type *", font=ctk.CTkFont(size=11),
                     text_color=COLORS["text_dim"]).grid(row=0, column=0, sticky="w", padx=6, pady=(6,0))
        self._ctype_var = ctk.StringVar(value=ex.get("cheque_type", cheque_type))
        ctk.CTkOptionMenu(frm, variable=self._ctype_var, values=["Inward", "Outward"],
                          width=200).grid(row=1, column=0, sticky="ew", padx=6)

        ctk.CTkLabel(frm, text="Party Type *", font=ctk.CTkFont(size=11),
                     text_color=COLORS["text_dim"]).grid(row=0, column=1, sticky="w", padx=6, pady=(6,0))
        self._ptype_var = ctk.StringVar(value=ex.get("party_type", "Customer"))
        ctk.CTkOptionMenu(frm, variable=self._ptype_var, values=["Customer", "Vendor", "Other"],
                          width=200).grid(row=1, column=1, sticky="ew", padx=6)

        _lbl("Cheque No. *", 1, 0); self._cno_var   = _ent(1, 0, ex.get("cheque_no", ""))
        _lbl("Bank Name *", 1, 1);  self._bank_var  = _ent(1, 1, ex.get("bank_name", ""))
        _lbl("Branch",       2, 0); self._branch_var = _ent(2, 0, ex.get("branch", ""))
        _lbl("Amount (₹) *", 2, 1); self._amt_var   = _ent(2, 1, str(ex.get("amount", "")))

        _lbl("Cheque Date (YYYY-MM-DD) *", 3, 0); self._cdate_var = _ent(3, 0, ex.get("cheque_date", ""))
        _lbl("Received / Issued Date",    3, 1); self._rdate_var = _ent(3, 1, ex.get("received_date", datetime.today().strftime("%Y-%m-%d")))

        _lbl("Party Name *", 4, 0); self._party_var  = _ent(4, 0, ex.get("party_name", ""), colspan=2)
        _lbl("Linked Invoice / Bill Ref", 5, 0); self._linked_var = _ent(5, 0, ex.get("linked_ref", ""), colspan=2)
        _lbl("Narration",   6, 0); self._narr_var  = _ent(6, 0, ex.get("narration", ""), colspan=2)

        ctk.CTkLabel(frm, text="Notes", font=ctk.CTkFont(size=11),
                     text_color=COLORS["text_dim"]).grid(row=14, column=0, sticky="w", padx=6, pady=(6,0))
        self._notes_box = ctk.CTkTextbox(frm, height=50)
        self._notes_box.grid(row=15, column=0, columnspan=2, sticky="ew", padx=6, pady=(0,8))
        self._notes_box.insert("0.0", ex.get("notes", ""))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=8)
        ctk.CTkButton(btn_row, text="Save", fg_color=COLORS["success"],
                      hover_color="#27ae60", command=self._save).pack(side="right", padx=4)
        ctk.CTkButton(btn_row, text="Cancel", fg_color="#555",
                      hover_color="#444", command=self.destroy).pack(side="right", padx=4)

    def _save(self):
        cno   = self._cno_var.get().strip()
        bank  = self._bank_var.get().strip()
        cdate = self._cdate_var.get().strip()
        party = self._party_var.get().strip()
        if not cno or not bank or not cdate or not party:
            messagebox.showwarning("Validation", "Cheque No., Bank, Date, and Party are required.", parent=self)
            return
        try:
            amt = float(self._amt_var.get())
        except ValueError:
            messagebox.showwarning("Validation", "Amount must be a number.", parent=self)
            return
        args = (self._ctype_var.get(), cno, bank, self._branch_var.get().strip(),
                amt, cdate, party, self._ptype_var.get(),
                self._rdate_var.get().strip(), self._linked_var.get().strip(),
                self._narr_var.get().strip(), self._notes_box.get("0.0", "end").strip())
        try:
            if self.cheque_id:
                db.update_cheque(self.cheque_id, *args)
            else:
                db.add_cheque(*args)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)
            return
        if self.on_save:
            self.on_save()
        self.destroy()


# ── Shift Management page ────────────────────────────────────────────────────

class ShiftsPage(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=COLORS["bg"], corner_radius=0)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=COLORS["card_bg"], corner_radius=0)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(hdr, text="Shift Management",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=COLORS["text"]).grid(row=0, column=0, padx=18, pady=14, sticky="w")
        ctk.CTkLabel(hdr, text="From:", text_color=COLORS["text_dim"],
                     font=ctk.CTkFont(size=12)).grid(row=0, column=3, padx=(14, 4), pady=14)
        self._from_var = ctk.StringVar()
        ctk.CTkEntry(hdr, textvariable=self._from_var, width=110,
                     placeholder_text="YYYY-MM-DD").grid(row=0, column=4, padx=4, pady=14)
        ctk.CTkLabel(hdr, text="To:", text_color=COLORS["text_dim"],
                     font=ctk.CTkFont(size=12)).grid(row=0, column=5, padx=4, pady=14)
        self._to_var = ctk.StringVar()
        ctk.CTkEntry(hdr, textvariable=self._to_var, width=110,
                     placeholder_text="YYYY-MM-DD").grid(row=0, column=6, padx=4, pady=14)
        ctk.CTkButton(hdr, text="Filter", width=70,
                      fg_color=COLORS["accent"], hover_color=COLORS["accent_light"],
                      command=self.refresh).grid(row=0, column=7, padx=(4, 18), pady=14)

        tbl_frame = ctk.CTkFrame(self, fg_color=COLORS["card_bg"], corner_radius=10)
        tbl_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=16)
        tbl_frame.grid_columnconfigure(0, weight=1)
        tbl_frame.grid_rowconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Shifts.Treeview",
                        background="#0d1424", foreground="#ecf0f1",
                        fieldbackground="#0d1424", rowheight=28,
                        font=("Segoe UI", 11))
        style.configure("Shifts.Treeview.Heading",
                        background="#1e2a3a", foreground="#94a3b8",
                        font=("Segoe UI", 10, "bold"))
        style.map("Shifts.Treeview", background=[("selected", "#1e3a5f")])

        cols = ("id", "cashier", "date", "open_time", "close_time",
                "opening", "sales", "expected", "closing", "discrepancy", "status")
        self._tree = ttk.Treeview(tbl_frame, columns=cols, show="headings",
                                   style="Shifts.Treeview", selectmode="browse")
        heads = {
            "id": ("#", 50), "cashier": ("Cashier", 140), "date": ("Date", 90),
            "open_time": ("Opened", 76), "close_time": ("Closed", 76),
            "opening": ("Opening ₹", 90), "sales": ("Sales ₹", 90),
            "expected": ("Expected ₹", 100), "closing": ("Closing ₹", 100),
            "discrepancy": ("Discrepancy", 100), "status": ("Status", 70),
        }
        for col, (head, width) in heads.items():
            self._tree.heading(col, text=head)
            self._tree.column(col, width=width, minwidth=width, anchor="center")
        self._tree.column("cashier", anchor="w")

        vsb = ttk.Scrollbar(tbl_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

    def refresh(self):
        from_d = self._from_var.get().strip() or None
        to_d   = self._to_var.get().strip() or None
        shifts = db.get_all_shifts(from_date=from_d, to_date=to_d)
        for row in self._tree.get_children():
            self._tree.delete(row)
        for s in shifts:
            disc = s.get("discrepancy")
            opened = str(s.get("opened_at") or "")
            closed = str(s.get("closed_at") or "")
            if "T" in opened:
                opened = opened.replace("T", " ")
            if "T" in closed:
                closed = closed.replace("T", " ")
            date_part  = opened[:10] if len(opened) >= 10 else opened
            open_time  = opened[11:16] if len(opened) >= 16 else ""
            close_time = closed[11:16] if len(closed) >= 16 else ("—" if not closed else closed[:5])
            tag = "open" if s.get("status") == "Open" else ""
            if disc is not None:
                disc_f = float(disc)
                if disc_f == 0:
                    tag = "exact"
                elif abs(disc_f) <= 50:
                    tag = "warn"
                else:
                    tag = "bad"
            disc_str = (f"₹ {float(disc):+,.2f}" if disc is not None else "—")
            self._tree.insert("", "end", tags=(tag,), values=(
                s.get("id", ""),
                s.get("full_name") or s.get("username", ""),
                date_part,
                open_time,
                close_time,
                f"₹ {float(s.get('opening_cash') or 0):,.2f}",
                f"₹ {float(s.get('sales_total') or 0):,.2f}",
                (f"₹ {float(s.get('expected_cash') or 0):,.2f}"
                 if s.get("expected_cash") is not None else "—"),
                (f"₹ {float(s.get('closing_cash') or 0):,.2f}"
                 if s.get("closing_cash") is not None else "—"),
                disc_str,
                s.get("status", ""),
            ))
        self._tree.tag_configure("open",  foreground="#f59e0b")
        self._tree.tag_configure("exact", foreground="#2ecc71")
        self._tree.tag_configure("warn",  foreground="#f59e0b")
        self._tree.tag_configure("bad",   foreground="#e74c3c")


# ── Shared denomination cash-count widget ─────────────────────────────────────

_DENOMINATIONS = [2000, 500, 200, 100, 50, 20, 10, 5, 2, 1]


class _DenomFrame(ctk.CTkScrollableFrame):
    """Reusable denomination entry grid: count × value = subtotal, with live total."""

    def __init__(self, parent, on_change=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._on_change = on_change
        self._vars: list = []
        self._total_lbl = None
        self._build()

    def _build(self):
        hdr_font = ctk.CTkFont(size=11, weight="bold")
        ctk.CTkLabel(self, text="Denomination", font=hdr_font,
                     text_color="#94a3b8").grid(row=0, column=0, padx=8, pady=(4, 2), sticky="w")
        ctk.CTkLabel(self, text="Count", font=hdr_font,
                     text_color="#94a3b8").grid(row=0, column=1, padx=8, pady=(4, 2))
        ctk.CTkLabel(self, text="Amount", font=hdr_font,
                     text_color="#94a3b8").grid(row=0, column=2, padx=8, pady=(4, 2), sticky="e")
        for r, denom in enumerate(_DENOMINATIONS, start=1):
            ctk.CTkLabel(self, text=f"₹ {denom:,}",
                         text_color="#ecf0f1",
                         font=ctk.CTkFont(size=12)).grid(row=r, column=0, padx=8, pady=2, sticky="w")
            var = ctk.StringVar(value="0")
            self._vars.append(var)
            ctk.CTkEntry(self, textvariable=var, width=70,
                         justify="center",
                         font=ctk.CTkFont(size=12)).grid(row=r, column=1, padx=8, pady=2)
            amt_lbl = ctk.CTkLabel(self, text="₹ 0",
                                   text_color="#2dd4bf",
                                   font=ctk.CTkFont(size=12))
            amt_lbl.grid(row=r, column=2, padx=8, pady=2, sticky="e")
            var.trace_add("write", lambda *_, d=denom, lbl=amt_lbl: self._update_row(d, lbl))
        sep = len(_DENOMINATIONS) + 1
        ctk.CTkFrame(self, fg_color="#1e2a3a", height=1,
                     corner_radius=0).grid(row=sep, column=0, columnspan=3,
                                            sticky="ew", padx=4, pady=4)
        self._total_lbl = ctk.CTkLabel(self, text="Total:  ₹ 0.00",
                                        font=ctk.CTkFont(size=14, weight="bold"),
                                        text_color="#2ecc71")
        self._total_lbl.grid(row=sep + 1, column=0, columnspan=3, pady=(4, 8))

    def _update_row(self, denom: int, lbl):
        idx = _DENOMINATIONS.index(denom)
        try:
            cnt = max(0, int(self._vars[idx].get() or 0))
        except (ValueError, TypeError):
            cnt = 0
        lbl.configure(text=f"₹ {cnt * denom:,}")
        self._total_lbl.configure(text=f"Total:  ₹ {self.total():,.2f}")
        if self._on_change:
            self._on_change(self.total())

    def total(self) -> float:
        t = 0.0
        for var, denom in zip(self._vars, _DENOMINATIONS):
            try:
                t += max(0, int(var.get() or 0)) * denom
            except (ValueError, TypeError):
                pass
        return round(t, 2)


# ── Open Shift dialog ─────────────────────────────────────────────────────────

class OpenShiftDialog(ctk.CTkToplevel):
    """Modal: cashier must enter opening cash before POS is usable."""

    def __init__(self, parent, user: dict, on_opened, on_exit):
        super().__init__(parent)
        self.title("Open Shift")
        self.geometry("480x600")
        self.resizable(False, False)
        self._user     = user
        self._on_opened = on_opened
        self._on_exit   = on_exit
        self.protocol("WM_DELETE_WINDOW", self._on_close_btn)
        self._build()
        self.grab_set()
        self.focus()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        ctk.CTkLabel(self, text="Open Shift",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color="#2dd4bf").grid(row=0, column=0, pady=(24, 2))
        ctk.CTkLabel(
            self,
            text=(f"Cashier: {self._user.get('full_name') or self._user.get('username','')}\n"
                  "Count the opening cash in the drawer and enter it below."),
            text_color="#94a3b8", font=ctk.CTkFont(size=12), justify="center",
        ).grid(row=1, column=0, pady=(0, 8))
        self._denom = _DenomFrame(self, fg_color="#0d1424", corner_radius=10, height=380)
        self._denom.grid(row=2, column=0, sticky="nsew", padx=18, pady=4)
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=3, column=0, pady=16)
        ctk.CTkButton(btn_frame, text="Exit POS", width=110,
                      fg_color="#7f1f1f", hover_color="#c0392b",
                      command=self._on_exit).pack(side="left", padx=8)
        ctk.CTkButton(btn_frame, text="Open Shift  →", width=150,
                      fg_color="#0d9488", hover_color="#0a7a70",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=self._submit).pack(side="left", padx=8)

    def _submit(self):
        opening_cash = self._denom.total()
        try:
            uid   = int(self._user.get("id") or 0)
            uname = self._user.get("username", "")
            fname = self._user.get("full_name", "") or uname
            sid   = db.open_shift(uid, uname, fname, opening_cash)
            self.destroy()
            self._on_opened(sid, opening_cash)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def _on_close_btn(self):
        if messagebox.askyesno("Exit POS?",
                               "No shift opened. Exit the POS?", parent=self):
            self._on_exit()


# ── Close Shift dialog ────────────────────────────────────────────────────────

class CloseShiftDialog(ctk.CTkToplevel):
    """Modal: denomination cash count + discrepancy summary before closing shift."""

    def __init__(self, parent, shift_id: int, opening_cash: float, on_closed):
        super().__init__(parent)
        self.title("Close Shift")
        self.geometry("520x700")
        self.resizable(False, False)
        self._shift_id    = shift_id
        self._opening_cash = opening_cash
        self._on_closed   = on_closed
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._build()
        self.grab_set()
        self.focus()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        ctk.CTkLabel(self, text="Close Shift",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color="#e74c3c").grid(row=0, column=0, pady=(20, 2))
        sales = db.get_shift_sales(self._shift_id)
        ctk.CTkLabel(
            self,
            text=(f"Sales this shift:  {sales['count']} bills  |  "
                  f"₹ {sales['total']:,.2f}"),
            text_color="#94a3b8", font=ctk.CTkFont(size=12),
        ).grid(row=1, column=0, pady=(0, 6))
        self._denom = _DenomFrame(self, fg_color="#0d1424", corner_radius=10,
                                   height=380, on_change=self._update_discrepancy)
        self._denom.grid(row=2, column=0, sticky="nsew", padx=18, pady=4)
        # discrepancy row
        disc_frame = ctk.CTkFrame(self, fg_color="#0d1424", corner_radius=8)
        disc_frame.grid(row=3, column=0, sticky="ew", padx=18, pady=(4, 0))
        disc_frame.grid_columnconfigure(1, weight=1)
        expected = round(self._opening_cash + sales["total"], 2)
        ctk.CTkLabel(disc_frame, text="Expected Cash:",
                     text_color="#94a3b8", font=ctk.CTkFont(size=11)).grid(
                         row=0, column=0, padx=12, pady=4, sticky="w")
        ctk.CTkLabel(disc_frame, text=f"₹ {expected:,.2f}",
                     text_color="#ecf0f1", font=ctk.CTkFont(size=12)).grid(
                         row=0, column=1, padx=12, pady=4, sticky="e")
        ctk.CTkLabel(disc_frame, text="Discrepancy:",
                     text_color="#94a3b8", font=ctk.CTkFont(size=11)).grid(
                         row=1, column=0, padx=12, pady=(0, 6), sticky="w")
        self._disc_lbl = ctk.CTkLabel(disc_frame, text="—",
                                       font=ctk.CTkFont(size=13, weight="bold"),
                                       text_color="#94a3b8")
        self._disc_lbl.grid(row=1, column=1, padx=12, pady=(0, 6), sticky="e")
        # notes
        ctk.CTkLabel(self, text="Notes (optional):",
                     text_color="#94a3b8", font=ctk.CTkFont(size=11)).grid(
                         row=4, column=0, sticky="w", padx=20, pady=(8, 0))
        self._notes = ctk.CTkEntry(self, placeholder_text="e.g. float left in drawer…")
        self._notes.grid(row=5, column=0, sticky="ew", padx=18, pady=(2, 0))
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=6, column=0, pady=14)
        ctk.CTkButton(btn_frame, text="Cancel", width=100,
                      fg_color="#1a2235", hover_color="#2a3245",
                      command=self.destroy).pack(side="left", padx=8)
        ctk.CTkButton(btn_frame, text="Close Shift  →", width=150,
                      fg_color="#e74c3c", hover_color="#c0392b",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=self._submit).pack(side="left", padx=8)

    def _update_discrepancy(self, closing_cash: float):
        sales    = db.get_shift_sales(self._shift_id)
        expected = round(self._opening_cash + sales["total"], 2)
        disc     = round(closing_cash - expected, 2)
        if disc == 0:
            color, text = "#2ecc71", "₹ 0.00  ✓"
        elif abs(disc) <= 50:
            color, text = "#f59e0b", f"₹ {disc:+,.2f}"
        else:
            color, text = "#e74c3c", f"₹ {disc:+,.2f}"
        self._disc_lbl.configure(text=text, text_color=color)

    def _submit(self):
        closing_cash = self._denom.total()
        if closing_cash == 0:
            if not messagebox.askyesno("Zero Cash?",
                                       "Closing cash is ₹ 0.00. Continue?", parent=self):
                return
        notes = self._notes.get().strip()
        try:
            result = db.close_shift(self._shift_id, closing_cash, notes)
            self.destroy()
            self._on_closed(result)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)


# ── Cashier POS ───────────────────────────────────────────────────────────────

class CashierApp(ctk.CTk):
    """Full-screen fast-billing POS for cashier role."""

    _BARCODE_GAP_MS = 80  # max ms between scanner keystrokes

    def __init__(self, user: dict):
        super().__init__()
        import db_connection
        self.current_user = user
        self.title(f"POS — {user.get('full_name') or user.get('username', 'Cashier')}")
        self.geometry("900x650")
        self.minsize(760, 540)
        self._cart: list[dict] = []          # {product, qty}
        self._all_products: list[dict] = []
        self._active_category: str = "All"
        self._cat_btns: dict = {}
        self._barcode_buf = ""
        self._barcode_ts  = 0.0
        self._selected_client: dict | None = None   # loyalty customer lookup
        self._payment_mode: str = "Cash"
        self._pay_btns: dict   = {}
        # Phase 6: shift management
        self._shift_id:        int | None = None
        self._shift_cash:      float      = 0.0
        self._shift_opened_at: str        = ""
        # Surface any silent Tkinter callback exception as a visible error dialog.
        def _report_cb_exc(exc, val, tb):
            import traceback
            messagebox.showerror("POS Error", "".join(traceback.format_exception(exc, val, tb)), parent=self)
        self.report_callback_exception = _report_cb_exc
        self._build()
        self._load_products()
        # Phase 4: multi-counter sync
        db_connection.register_reconnect_callback(self._on_cloud_reconnect)
        db_connection.start_reconnect_watcher()
        self._status_tick()   # start the 5-second status refresh loop
        self._stock_tick()    # start the 30-second stock polling loop
        self.after(300, self._resume_existing_shift)

    # ── build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── header ──
        hdr = ctk.CTkFrame(self, fg_color="#0d1424", corner_radius=0, height=52)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(hdr, text="🧾  POS Billing",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color="#2dd4bf").grid(row=0, column=0, padx=18, pady=10)
        ctk.CTkLabel(hdr,
                     text=f"Cashier: {self.current_user.get('full_name') or self.current_user.get('username','')}",
                     text_color="#94a3b8", font=ctk.CTkFont(size=12)).grid(
                         row=0, column=1, sticky="w", padx=8)
        self._shift_btn = ctk.CTkButton(hdr, text="🔓  Open Shift", width=120, height=30,
                      fg_color="#1e3a5f", hover_color="#2a4a6f",
                      font=ctk.CTkFont(size=12),
                      command=self._close_shift_clicked)
        self._shift_btn.grid(row=0, column=2, padx=8, pady=10)
        self._status_lbl = ctk.CTkLabel(
            hdr, text="● …", text_color="#94a3b8", font=ctk.CTkFont(size=11))
        self._status_lbl.grid(row=0, column=3, padx=14)
        ctk.CTkButton(hdr, text="✕  Exit", width=90, height=30,
                      fg_color="#7f1f1f", hover_color="#c0392b",
                      font=ctk.CTkFont(size=12),
                      command=self.destroy).grid(row=0, column=4, padx=14, pady=10)

        # ── body: left=search/results, right=cart ──
        body = ctk.CTkFrame(self, fg_color="#0a0f1e", corner_radius=0)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        # ── left panel ──
        left = ctk.CTkFrame(body, fg_color="#0d1424", corner_radius=10)
        self._left_panel = left
        left.grid(row=0, column=0, padx=(14, 7), pady=14, sticky="nsew")
        left.grid_rowconfigure(0, weight=0)
        left.grid_rowconfigure(1, weight=0)
        left.grid_rowconfigure(2, weight=0)
        left.grid_rowconfigure(3, weight=1)
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(left, text="Search product / scan barcode",
                     font=ctk.CTkFont(size=12), text_color="#94a3b8"
                     ).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 0))

        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refresh_results())
        search_entry = ctk.CTkEntry(
            left, textvariable=self._search_var,
            placeholder_text="🔍  Type name or scan barcode…",
            height=38, font=ctk.CTkFont(size=13),
        )
        search_entry.grid(row=1, column=0, padx=14, pady=(4, 4), sticky="ew")
        search_entry.focus()

        # Barcode scanner: bind key events on the whole window
        self.bind("<Key>", self._on_key)

        # ── category tabs ──
        self._cat_seg = ctk.CTkSegmentedButton(
            left, values=["All"],
            fg_color="#111827",
            selected_color="#0d9488",
            selected_hover_color="#0a7a70",
            unselected_color="#1a2235",
            unselected_hover_color="#2a3245",
            text_color="#ffffff",
            text_color_disabled="#94a3b8",
            font=ctk.CTkFont(size=11),
            height=30,
            command=self._select_category,
        )
        self._cat_seg.grid(row=2, column=0, padx=14, pady=(0, 6), sticky="ew")

        self._results_frame = ctk.CTkScrollableFrame(
            left, fg_color="transparent", corner_radius=0)
        self._results_frame.grid(row=3, column=0, sticky="nsew", padx=4, pady=(0, 8))
        self._results_frame.grid_columnconfigure(0, weight=1)

        # ── right panel: cart ──
        right = ctk.CTkFrame(body, fg_color="#0d1424", corner_radius=10)
        right.grid(row=0, column=1, padx=(7, 14), pady=14, sticky="nsew")
        right.grid_rowconfigure(2, weight=1)
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(right, text="🛒  Cart",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#2dd4bf").grid(
                         row=0, column=0, sticky="w", padx=14, pady=(12, 4))

        # ── customer lookup bar ──
        cust_bar = ctk.CTkFrame(right, fg_color="#111827", corner_radius=6)
        cust_bar.grid(row=1, column=0, padx=14, pady=(0, 6), sticky="ew")
        cust_bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(cust_bar, text="Customer", width=65,
                     font=ctk.CTkFont(size=11), text_color="#94a3b8"
                     ).grid(row=0, column=0, padx=(8, 4), pady=(6, 2))

        self._phone_var = ctk.StringVar()
        self._phone_entry = ctk.CTkEntry(
            cust_bar, textvariable=self._phone_var,
            placeholder_text="Phone number…", height=30,
            font=ctk.CTkFont(size=12))
        self._phone_entry.grid(row=0, column=1, padx=4, pady=(6, 2), sticky="ew")
        self._phone_entry.bind("<Return>", lambda _: self._lookup_customer())

        ctk.CTkButton(cust_bar, text="Find", width=52, height=30,
                      fg_color="#1e3a5f", hover_color="#2a4a6f",
                      font=ctk.CTkFont(size=11),
                      command=self._lookup_customer
                      ).grid(row=0, column=2, padx=(4, 8), pady=(6, 2))

        self._cust_lbl = ctk.CTkLabel(
            cust_bar, text="👤  Walk-in customer",
            font=ctk.CTkFont(size=11), text_color="#64748b", anchor="w")
        self._cust_lbl.grid(row=1, column=0, columnspan=3,
                            sticky="w", padx=10, pady=(0, 6))

        self._cart_frame = ctk.CTkScrollableFrame(
            right, fg_color="transparent", corner_radius=0)
        self._cart_frame.grid(row=2, column=0, sticky="nsew", padx=4)
        self._cart_frame.grid_columnconfigure(0, weight=1)

        # totals + actions
        foot = ctk.CTkFrame(right, fg_color="transparent")
        foot.grid(row=3, column=0, sticky="ew", padx=14, pady=10)
        foot.grid_columnconfigure(0, weight=1)

        # ── breakdown panel ──
        bd = ctk.CTkFrame(foot, fg_color="#111827", corner_radius=6)
        bd.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        bd.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(bd, text="Subtotal", font=ctk.CTkFont(size=11),
                     text_color="#64748b").grid(row=0, column=0, sticky="w", padx=10, pady=(8, 2))
        self._subtotal_val = ctk.CTkLabel(bd, text="₹ 0.00",
                                           font=ctk.CTkFont(size=11), text_color="#94a3b8", anchor="e")
        self._subtotal_val.grid(row=0, column=1, sticky="e", padx=10, pady=(8, 2))

        ctk.CTkLabel(bd, text="GST", font=ctk.CTkFont(size=11),
                     text_color="#64748b").grid(row=1, column=0, sticky="w", padx=10, pady=2)
        self._gst_val = ctk.CTkLabel(bd, text="₹ 0.00",
                                      font=ctk.CTkFont(size=11), text_color="#94a3b8", anchor="e")
        self._gst_val.grid(row=1, column=1, sticky="e", padx=10, pady=2)

        ctk.CTkFrame(bd, fg_color="#1e2a3a", height=1).grid(
            row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=4)

        ctk.CTkLabel(bd, text="TOTAL", font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#2ecc71").grid(row=3, column=0, sticky="w", padx=10, pady=(2, 8))
        self._total_lbl = ctk.CTkLabel(bd, text="₹ 0.00",
                                        font=ctk.CTkFont(size=14, weight="bold"),
                                        text_color="#2ecc71", anchor="e")
        self._total_lbl.grid(row=3, column=1, sticky="e", padx=10, pady=(2, 8))

        # ── payment mode selector ──
        pay_row = ctk.CTkFrame(foot, fg_color="transparent")
        pay_row.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        ctk.CTkLabel(pay_row, text="Pay via", font=ctk.CTkFont(size=11),
                     text_color="#64748b").pack(side="left", padx=(0, 6))
        for mode, icon in [("Cash", "💵"), ("UPI", "📱"), ("Card", "💳")]:
            active = mode == "Cash"
            btn = ctk.CTkButton(
                pay_row, text=f"{icon} {mode}", height=30, width=82,
                fg_color="#0d9488" if active else "#1a2235",
                hover_color="#0a7a70" if active else "#2a3245",
                text_color="#ffffff" if active else "#94a3b8",
                font=ctk.CTkFont(size=11),
                command=lambda m=mode: self._select_payment(m))
            btn.pack(side="left", padx=3)
            self._pay_btns[mode] = btn

        # ── action buttons ──
        btn_row = ctk.CTkFrame(foot, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew")
        ctk.CTkButton(btn_row, text="🗑  Clear", width=100, height=36,
                      fg_color="#1a2235", hover_color="#2a3245",
                      command=self._clear_cart).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="💾  Save Bill", height=36,
                      fg_color="#0d9488", hover_color="#0a7a70",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=self._save_bill).pack(side="left", fill="x", expand=True)

    # ── product loading & search ───────────────────────────────────────────────

    @staticmethod
    def _product_to_dict(p) -> dict:
        """Convert a DB row to a plain dict, coercing decimal.Decimal → float."""
        from decimal import Decimal
        return {k: float(v) if isinstance(v, Decimal) else v for k, v in dict(p).items()}

    def _load_products(self):
        self._all_products = [self._product_to_dict(p) for p in db.get_all_products()]
        self._refresh_results()
        self.after(0, self._rebuild_category_tabs)

    def _rebuild_category_tabs(self):
        unique_cats = sorted({p.get("category") or "" for p in self._all_products if p.get("category")})
        cats = ["All"] + unique_cats
        if self._active_category not in cats:
            self._active_category = "All"
        self._cat_seg.destroy()
        self._cat_seg = ctk.CTkSegmentedButton(
            self._left_panel,
            values=cats,
            fg_color="#111827",
            selected_color="#0d9488",
            selected_hover_color="#0a7a70",
            unselected_color="#1a2235",
            unselected_hover_color="#2a3245",
            text_color="#ffffff",
            text_color_disabled="#94a3b8",
            font=ctk.CTkFont(size=11),
            height=30,
            command=self._select_category,
        )
        self._cat_seg.grid(row=2, column=0, padx=14, pady=(0, 6), sticky="ew")
        self._cat_seg.set(self._active_category)

    def _select_category(self, cat: str):
        self._active_category = cat
        self._refresh_results()

    def _refresh_results(self):
        for w in self._results_frame.winfo_children():
            w.destroy()
        q = self._search_var.get().strip().lower()
        pool = self._all_products
        if self._active_category != "All":
            pool = [p for p in pool if (p.get("category") or "") == self._active_category]
        matches = [p for p in pool
                   if q in p["name"].lower() or q in (p.get("sku") or "").lower()] if q else pool[:40]
        if not matches:
            ctk.CTkLabel(self._results_frame, text="No products found.",
                         text_color="#555").pack(pady=12)
            return
        for p in matches[:60]:
            self._product_row(p)

    def _product_row(self, p: dict):
        row = ctk.CTkFrame(self._results_frame, fg_color="#16213e", corner_radius=6)
        row.pack(fill="x", pady=2, padx=2)
        row.grid_columnconfigure(0, weight=1)
        stock_color = "#e74c3c" if p.get("stock_quantity", 0) <= 0 else "#94a3b8"
        ctk.CTkLabel(row, text=p["name"], anchor="w",
                     font=ctk.CTkFont(size=12),
                     text_color="#ecf0f1").grid(row=0, column=0, sticky="w", padx=10, pady=(6, 0))
        ctk.CTkLabel(row,
                     text=f"₹{p['unit_price']:,.2f}  |  Stock: {p.get('stock_quantity', 0):g} {p.get('unit','pcs')}",
                     anchor="w", font=ctk.CTkFont(size=10), text_color=stock_color,
                     ).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 6))
        ctk.CTkButton(row, text="+ Add", width=60, height=28,
                      fg_color="#0d9488", hover_color="#0a7a70",
                      font=ctk.CTkFont(size=11),
                      command=lambda prod=p: self._add_to_cart(prod)
                      ).grid(row=0, column=1, rowspan=2, padx=8, pady=4)

    # ── barcode scanner ────────────────────────────────────────────────────────

    def _on_key(self, event):
        import time
        now = time.time() * 1000
        if now - self._barcode_ts < self._BARCODE_GAP_MS:
            if event.char and event.char.isprintable():
                self._barcode_buf += event.char
        else:
            self._barcode_buf = event.char if (event.char and event.char.isprintable()) else ""
        self._barcode_ts = now

        if event.keysym == "Return" and len(self._barcode_buf) >= 3:
            code = self._barcode_buf.strip()
            self._barcode_buf = ""
            matches = [p for p in self._all_products
                       if (p.get("sku") or "").lower() == code.lower()
                       or p["name"].lower() == code.lower()]
            if matches:
                self._add_to_cart(matches[0])
                self._search_var.set("")
            else:
                self._search_var.set(code)

    # ── cart management ────────────────────────────────────────────────────────

    def _add_to_cart(self, product: dict):
        stock = int(product.get("stock_quantity") or 0)
        for entry in self._cart:
            if entry["product"]["id"] == product["id"]:
                if entry["qty"] >= stock:
                    messagebox.showwarning(
                        "Stock limit", f"Only {stock} unit(s) available.", parent=self)
                    return
                entry["qty"] += 1
                self._refresh_cart()
                return
        if stock < 1:
            messagebox.showwarning(
                "Out of stock", f"{product['name']} is out of stock.", parent=self)
            return
        self._cart.append({"product": product, "qty": 1})
        self._refresh_cart()
        # Delay search clear: setting it synchronously triggers _refresh_results() which
        # destroys the clicked button while CTkButton is still running its post-command
        # cleanup, causing a silent TclError that swallows the whole cart update.
        self.after(1, lambda: self._search_var.set(""))

    def _refresh_cart(self):
        for w in self._cart_frame.winfo_children():
            w.destroy()
        if not self._cart:
            ctk.CTkLabel(self._cart_frame, text="Cart is empty.",
                         text_color="#555").pack(pady=20)
            self._subtotal_val.configure(text="₹ 0.00")
            self._gst_val.configure(text="₹ 0.00")
            self._total_lbl.configure(text="₹ 0.00")
            return
        subtotal  = 0.0
        gst_total = 0.0
        for idx, entry in enumerate(self._cart):
            p   = entry["product"]
            qty = entry["qty"]
            line_total = round(qty * float(p["unit_price"]), 2)
            gst_total += round(line_total * float(p.get("gst_rate") or 0) / 100, 2)
            subtotal  += line_total
            row = ctk.CTkFrame(self._cart_frame, fg_color="#16213e", corner_radius=6)
            row.pack(fill="x", pady=2, padx=2)
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(row, text=p["name"], anchor="w",
                         font=ctk.CTkFont(size=11),
                         text_color="#ecf0f1").grid(row=0, column=0, sticky="w", padx=8, pady=(4, 0))
            # qty controls
            ctrl = ctk.CTkFrame(row, fg_color="transparent")
            ctrl.grid(row=1, column=0, sticky="w", padx=6, pady=(0, 4))
            ctk.CTkButton(ctrl, text="−", width=26, height=24,
                          fg_color="#1a2235", hover_color="#2a3245",
                          command=lambda i=idx: self._change_qty(i, -1)).pack(side="left")
            ctk.CTkLabel(ctrl, text=f"{qty:g}", width=32,
                         font=ctk.CTkFont(size=12),
                         text_color="#ecf0f1").pack(side="left")
            ctk.CTkButton(ctrl, text="+", width=26, height=24,
                          fg_color="#1a2235", hover_color="#2a3245",
                          command=lambda i=idx: self._change_qty(i, 1)).pack(side="left")
            ctk.CTkLabel(ctrl, text=f"× ₹{p['unit_price']:,.2f} = ₹{line_total:,.2f}",
                         font=ctk.CTkFont(size=10), text_color="#94a3b8").pack(side="left", padx=(8, 0))
            ctk.CTkButton(row, text="✕", width=28, height=24,
                          fg_color="#7f1f1f", hover_color="#c0392b",
                          font=ctk.CTkFont(size=10),
                          command=lambda i=idx: self._remove_item(i)
                          ).grid(row=0, column=1, rowspan=2, padx=6, pady=4)
        grand = round(subtotal + gst_total, 2)
        self._subtotal_val.configure(text=f"₹ {subtotal:,.2f}")
        self._gst_val.configure(text=f"₹ {gst_total:,.2f}")
        self._total_lbl.configure(text=f"₹ {grand:,.2f}")

    def _change_qty(self, idx: int, delta: int):
        entry = self._cart[idx]
        stock = int(entry["product"].get("stock_quantity") or 0)
        new_qty = entry["qty"] + delta
        if new_qty > stock:
            messagebox.showwarning(
                "Stock limit", f"Only {stock} unit(s) available.", parent=self)
            return
        entry["qty"] = max(1, new_qty)
        self._refresh_cart()

    def _remove_item(self, idx: int):
        self._cart.pop(idx)
        self._refresh_cart()

    def _clear_cart(self):
        self._cart.clear()
        self._refresh_cart()
        self._clear_customer()

    def _select_payment(self, mode: str):
        self._payment_mode = mode
        for m, btn in self._pay_btns.items():
            active = m == mode
            btn.configure(
                fg_color="#0d9488" if active else "#1a2235",
                hover_color="#0a7a70" if active else "#2a3245",
                text_color="#ffffff" if active else "#94a3b8")

    # ── Phase 4: status / polling / sync ──────────────────────────────────────

    def _status_tick(self):
        """Refresh the online/offline badge every 5 seconds."""
        import db_connection
        try:
            queued = db.get_offline_queue_count()
            if db_connection.is_cloud():
                if queued:
                    self._status_lbl.configure(
                        text=f"● Online  ({queued} syncing…)", text_color="#f59e0b")
                else:
                    self._status_lbl.configure(text="● Online", text_color="#2ecc71")
            else:
                if queued:
                    self._status_lbl.configure(
                        text=f"● Offline — {queued} bill{'s' if queued != 1 else ''} queued",
                        text_color="#e74c3c")
                else:
                    self._status_lbl.configure(text="● Offline", text_color="#e74c3c")
        except Exception:
            pass
        self.after(5_000, self._status_tick)

    def _stock_tick(self):
        """Reload product stock from the cloud every 30 seconds (multi-counter sync)."""
        import db_connection, threading
        if db_connection.is_cloud():
            threading.Thread(target=self._bg_load_products, daemon=True).start()
        self.after(30_000, self._stock_tick)

    def _bg_load_products(self):
        """Load products in a background thread, then update UI on main thread."""
        try:
            products = [self._product_to_dict(p) for p in db.get_all_products()]
            self.after(0, lambda: self._apply_products(products))
        except Exception:
            pass

    def _apply_products(self, products):
        self._all_products = products
        self._rebuild_category_tabs()
        self._refresh_results()

    def _on_cloud_reconnect(self):
        """Called from the reconnect watcher thread when PostgreSQL comes back."""
        self.after(0, self._do_sync)

    def _do_sync(self):
        try:
            count = db.sync_offline_queue()
            self._load_products()
            self._status_tick()
            if count:
                messagebox.showinfo(
                    "Sync Complete",
                    f"{count} offline bill{'s' if count != 1 else ''} synced to cloud.",
                    parent=self)
        except Exception as e:
            messagebox.showerror("Sync Error", str(e), parent=self)

    # ── customer loyalty lookup ────────────────────────────────────────────────

    def _lookup_customer(self):
        phone = self._phone_var.get().strip()
        if not phone:
            return
        client = db.get_client_by_phone(phone)
        if client:
            self._set_customer(dict(client))
        else:
            self._prompt_new_customer(phone)

    def _set_customer(self, client: dict):
        self._selected_client = client
        name = client.get("name", "Customer")
        pts  = int(client.get("loyalty_points") or 0)
        pts_text = f"  •  ⭐ {pts} pts" if pts else ""
        self._cust_lbl.configure(
            text=f"👤  {name}{pts_text}    ✕ clear",
            text_color="#2dd4bf")
        self._cust_lbl.bind("<Button-1>", lambda _: self._clear_customer())

    def _clear_customer(self):
        self._selected_client = None
        if hasattr(self, "_phone_var"):
            self._phone_var.set("")
        if hasattr(self, "_cust_lbl"):
            self._cust_lbl.configure(text="👤  Walk-in customer", text_color="#64748b")
            self._cust_lbl.unbind("<Button-1>")

    def _prompt_new_customer(self, phone: str):
        dlg = ctk.CTkToplevel(self)
        dlg.title("New Customer")
        dlg.geometry("340x170")
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.lift()
        dlg.update()          # force the window to render before grab
        dlg.grab_set()
        dlg.focus_force()

        ctk.CTkLabel(dlg, text=f"Phone {phone} not found.",
                     font=ctk.CTkFont(size=12)).pack(pady=(14, 2))
        ctk.CTkLabel(dlg, text="Enter name to register as new customer:",
                     font=ctk.CTkFont(size=11), text_color="#94a3b8").pack()

        name_var = ctk.StringVar()
        name_entry = ctk.CTkEntry(dlg, textvariable=name_var,
                                   placeholder_text="Customer name", height=34)
        name_entry.pack(fill="x", padx=20, pady=8)
        name_entry.focus()

        def _save_new():
            name = name_var.get().strip()
            if not name:
                return
            cid = db.add_client_quick(name, phone)
            dlg.destroy()
            self._set_customer({"id": cid, "name": name,
                                 "phone": phone, "loyalty_points": 0})

        name_entry.bind("<Return>", lambda _: _save_new())

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 10))
        ctk.CTkButton(btn_row, text="Skip (Walk-in)", width=120, height=32,
                      fg_color="#1a2235", hover_color="#2a3245",
                      command=dlg.destroy).pack(side="left")
        ctk.CTkButton(btn_row, text="Add Customer", height=32,
                      fg_color="#0d9488", hover_color="#0a7a70",
                      command=_save_new).pack(side="left", fill="x",
                                              expand=True, padx=(8, 0))

    # ── save bill ──────────────────────────────────────────────────────────────

    def _save_bill(self):
        if not self._cart:
            messagebox.showwarning("Empty Cart", "Add items before saving.", parent=self)
            return
        # Re-check live stock before committing
        live = {p["id"]: int(p.get("stock_quantity") or 0)
                for p in self._all_products}
        over = []
        for e in self._cart:
            pid   = e["product"]["id"]
            avail = live.get(pid, 0)
            if e["qty"] > avail:
                over.append(f"{e['product']['name']}: need {e['qty']}, only {avail} in stock")
        if over:
            messagebox.showerror(
                "Stock exceeded",
                "Cannot save bill — quantity exceeds available stock:\n\n" + "\n".join(over),
                parent=self,
            )
            return
        try:
            client_id  = (self._selected_client["id"] if self._selected_client
                          else db.get_or_create_walkin_client())
            billed_to  = (self._selected_client.get("name", "Customer")
                          if self._selected_client else "Walk-in")
            inv_number = db.generate_invoice_number()
            today      = datetime.now().strftime("%Y-%m-%d")
            items = [{
                "description": e["product"]["name"],
                "hsn_code":    e["product"].get("hsn_code", ""),
                "quantity":    e["qty"],
                "unit":        e["product"].get("unit", "pcs"),
                "unit_price":  e["product"]["unit_price"],
                "gst_rate":    e["product"].get("gst_rate", 18),
                "product_id":  e["product"]["id"],
            } for e in self._cart]
            db.create_invoice(
                invoice_number=inv_number,
                client_id=client_id,
                invoice_date=today,
                due_date=today,
                supply_type="intra",
                items=items,
                notes=f"Payment: {self._payment_mode}",
                status="Paid",
                shift_id=self._shift_id,
            )
            # Reload stock counts, clear cart (which also clears customer selection)
            self._load_products()
            self._clear_cart()
            # ── Thermal receipt printing ──────────────────────────────────
            self._maybe_print_receipt(inv_number, today, items)
            messagebox.showinfo(
                "Bill Saved",
                f"Bill {inv_number} saved.\nCustomer: {billed_to}\nPaid via: {self._payment_mode}",
                parent=self)
        except Exception as e:
            import traceback
            messagebox.showerror("Error", traceback.format_exc(), parent=self)

    # ── Phase 6: shift management ─────────────────────────────────────────────

    def _resume_existing_shift(self):
        """Pick up any already-open shift silently; never block the POS on startup."""
        uid = int(self.current_user.get("id") or 0)
        existing = db.get_open_shift(uid)
        if existing:
            self._shift_id        = existing["id"]
            self._shift_cash      = float(existing.get("opening_cash") or 0)
            self._shift_opened_at = str(existing.get("opened_at") or "")
            self._shift_btn.configure(text="🔒  Close Shift")

    def _ensure_shift(self):
        """Check for an open shift; show OpenShiftDialog if none exists."""
        uid = int(self.current_user.get("id") or 0)
        existing = db.get_open_shift(uid)
        if existing:
            self._shift_id        = existing["id"]
            self._shift_cash      = float(existing.get("opening_cash") or 0)
            self._shift_opened_at = str(existing.get("opened_at") or "")
        else:
            OpenShiftDialog(self, self.current_user,
                            on_opened=self._on_shift_opened,
                            on_exit=self._exit_no_shift)

    def _on_shift_opened(self, shift_id: int, opening_cash: float):
        self._shift_id        = shift_id
        self._shift_cash      = opening_cash
        self._shift_opened_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        self._shift_btn.configure(text="🔒  Close Shift")

    def _exit_no_shift(self):
        """User chose to exit instead of opening a shift."""
        self._shift_id = None
        self._quit_to_login()

    def _close_shift_clicked(self):
        if self._shift_id is None:
            # No shift open — offer to open one; Exit just closes the dialog
            dlg_holder = []
            dlg = OpenShiftDialog(self, self.current_user,
                                  on_opened=self._on_shift_opened,
                                  on_exit=lambda: dlg_holder[0].destroy() if dlg_holder else None)
            dlg_holder.append(dlg)
            return
        CloseShiftDialog(self, self._shift_id, self._shift_cash,
                         on_closed=self._on_shift_closed)

    def _on_shift_closed(self, result: dict):
        disc = result["discrepancy"]
        if disc == 0:
            disc_str = "₹ 0.00  — exact ✓"
        else:
            disc_str = f"₹ {disc:+,.2f}"
        messagebox.showinfo(
            "Shift Closed",
            f"Sales:        {result['sales_count']} bills\n"
            f"Sales Total:  ₹ {result['sales_total']:,.2f}\n"
            f"Opening Cash: ₹ {result['opening_cash']:,.2f}\n"
            f"Expected:     ₹ {result['expected_cash']:,.2f}\n"
            f"Closing Cash: ₹ {result['closing_cash']:,.2f}\n"
            f"Discrepancy:  {disc_str}",
            parent=self,
        )
        self._shift_id = None
        self._shift_btn.configure(text="🔓  Open Shift")

    def _quit_to_login(self):
        """Destroy the POS and return to the login screen."""
        super().destroy()
        win = LoginWindow()
        win.mainloop()

    def _on_shift_closed_then_exit(self, result: dict):
        self._on_shift_closed(result)
        self.after(100, self._quit_to_login)

    def destroy(self):
        if self._shift_id is not None:
            choice = messagebox.askyesnocancel(
                "Exit POS",
                "Close shift before exiting?\n\n"
                "Yes  — close shift then exit\n"
                "No   — exit without closing shift\n"
                "Cancel — stay in POS",
                parent=self,
            )
            if choice is None:
                return
            if choice:
                CloseShiftDialog(self, self._shift_id, self._shift_cash,
                                 on_closed=self._on_shift_closed_then_exit)
                return
        self._quit_to_login()

    def _maybe_print_receipt(self, inv_number: str, inv_date: str, items: list):
        """Print receipt if printer is enabled. Auto-print or ask based on config."""
        try:
            import thermal_receipt
            if not thermal_receipt.is_enabled():
                return
            cfg = thermal_receipt.load_config()
            auto = cfg.get("auto_print", True)
            if not auto:
                if not messagebox.askyesno(
                        "Print Receipt",
                        f"Print receipt for bill {inv_number}?",
                        parent=self):
                    return
            firm = dict(db.get_firm_settings() or {})
            cashier = (self.current_user.get("full_name")
                       or self.current_user.get("username", "Cashier"))
            # Compute totals from items (same logic as create_invoice, intra supply)
            subtotal = gst_total = 0.0
            for it in items:
                taxable = round(it["quantity"] * it["unit_price"], 2)
                gst_amt = round(taxable * it["gst_rate"] / 100, 2)
                subtotal  += taxable
                gst_total += gst_amt
            grand_total = round(subtotal + gst_total, 2)
            thermal_receipt.print_receipt(
                firm           = firm,
                items          = items,
                invoice_number = inv_number,
                invoice_date   = inv_date,
                cashier_name   = cashier,
                subtotal       = round(subtotal, 2),
                gst_total      = round(gst_total, 2),
                grand_total    = grand_total,
            )
        except Exception as e:
            messagebox.showerror("Print Error",
                                 f"Receipt not printed:\n{e}", parent=self)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import app_config
    app_config.load()
    login = LoginWindow()
    login.mainloop()
