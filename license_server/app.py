import os
import uuid
from datetime import datetime, timedelta
from functools import wraps

import hmac

import psycopg2
from flask import Flask, jsonify, request

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL env var must be set")
if not ADMIN_API_KEY or len(ADMIN_API_KEY) < 32:
    raise RuntimeError("ADMIN_API_KEY must be set to a random string of at least 32 characters")


def get_db():
    return psycopg2.connect(DATABASE_URL)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-Admin-Key", "")
        if not hmac.compare_digest(key, ADMIN_API_KEY):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


# ── Public endpoints ──────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})


@app.route("/activate", methods=["POST"])
def activate():
    """First-time activation: bind license key to machine."""
    data = request.json or {}
    license_key = data.get("license_key", "").strip().upper()
    machine_id  = data.get("machine_id", "").strip()
    product_id  = data.get("product_id", "").strip()

    if not all([license_key, machine_id, product_id]):
        return jsonify({"valid": False, "error": "Missing fields"}), 400

    conn = get_db()
    cur  = conn.cursor()
    cur.execute(
        "SELECT id, machine_id, is_active, expires_at, plan "
        "FROM licenses WHERE license_key = %s AND product_id = %s",
        (license_key, product_id),
    )
    row = cur.fetchone()

    if not row:
        cur.close(); conn.close()
        return jsonify({"valid": False, "error": "Invalid license key"})

    lic_id, bound_machine, is_active, expires_at, plan = row

    if not is_active:
        cur.close(); conn.close()
        return jsonify({"valid": False, "error": "License has been deactivated"})

    if expires_at and expires_at < datetime.utcnow():
        cur.close(); conn.close()
        return jsonify({"valid": False, "error": "License expired"})

    if bound_machine and bound_machine != machine_id:
        cur.close(); conn.close()
        return jsonify({"valid": False, "error": "License is already bound to another machine"})

    cur.execute(
        "UPDATE licenses "
        "SET machine_id = %s, activated_at = COALESCE(activated_at, NOW()), last_seen = NOW() "
        "WHERE id = %s",
        (machine_id, lic_id),
    )
    conn.commit()
    cur.close(); conn.close()

    return jsonify({
        "valid": True,
        "plan": plan,
        "expires_at": expires_at.isoformat() if expires_at else None,
    })


@app.route("/check", methods=["POST"])
def check():
    """Startup phone-home: validate license is still active."""
    data = request.json or {}
    license_key = data.get("license_key", "").strip().upper()
    machine_id  = data.get("machine_id", "").strip()
    product_id  = data.get("product_id", "").strip()

    if not all([license_key, machine_id, product_id]):
        return jsonify({"valid": False, "error": "Missing fields"}), 400

    conn = get_db()
    cur  = conn.cursor()
    cur.execute(
        "SELECT is_active, expires_at, plan, machine_id "
        "FROM licenses WHERE license_key = %s AND product_id = %s",
        (license_key, product_id),
    )
    row = cur.fetchone()

    if not row:
        cur.close(); conn.close()
        return jsonify({"valid": False, "error": "Invalid license"})

    is_active, expires_at, plan, bound_machine = row

    if not is_active:
        cur.close(); conn.close()
        return jsonify({"valid": False, "error": "License deactivated"})

    if expires_at and expires_at < datetime.utcnow():
        cur.close(); conn.close()
        return jsonify({"valid": False, "error": "License expired"})

    if bound_machine != machine_id:
        cur.close(); conn.close()
        return jsonify({"valid": False, "error": "Machine mismatch"})

    cur.execute("UPDATE licenses SET last_seen = NOW() WHERE license_key = %s", (license_key,))
    conn.commit()
    cur.close(); conn.close()

    return jsonify({
        "valid": True,
        "plan": plan,
        "expires_at": expires_at.isoformat() if expires_at else None,
    })


@app.route("/version/<product_id>")
def version(product_id):
    """Return latest version info for auto-updater."""
    conn = get_db()
    cur  = conn.cursor()
    cur.execute(
        "SELECT current_version, download_url, release_notes "
        "FROM products WHERE product_id = %s",
        (product_id,),
    )
    row = cur.fetchone()
    cur.close(); conn.close()

    if not row:
        return jsonify({"error": "Product not found"}), 404

    ver, url, notes = row
    return jsonify({"version": ver, "download_url": url, "release_notes": notes})


# ── Admin endpoints ───────────────────────────────────────────────────────────

@app.route("/admin/generate", methods=["POST"])
@admin_required
def generate_license():
    """Generate a new license key for a client."""
    data       = request.json or {}
    product_id = data.get("product_id", "stockaccounts-pro")
    plan       = data.get("plan", "monthly")
    email      = data.get("email", "")
    months     = int(data.get("months", 1))

    raw = uuid.uuid4().hex.upper()
    license_key = "-".join(raw[i:i+4] for i in range(0, 16, 4))  # XXXX-XXXX-XXXX-XXXX

    expires_at = datetime.utcnow() + timedelta(days=30 * months)

    conn = get_db()
    cur  = conn.cursor()
    cur.execute(
        "INSERT INTO licenses (license_key, product_id, plan, email, expires_at, is_active) "
        "VALUES (%s, %s, %s, %s, %s, TRUE)",
        (license_key, product_id, plan, email, expires_at),
    )
    conn.commit()
    cur.close(); conn.close()

    return jsonify({
        "license_key": license_key,
        "product_id": product_id,
        "plan": plan,
        "email": email,
        "expires_at": expires_at.isoformat(),
    })


@app.route("/admin/licenses")
@admin_required
def list_licenses():
    product_id = request.args.get("product_id")
    conn = get_db()
    cur  = conn.cursor()

    if product_id:
        cur.execute(
            "SELECT license_key, product_id, plan, email, machine_id, "
            "activated_at, expires_at, is_active, last_seen "
            "FROM licenses WHERE product_id = %s ORDER BY created_at DESC",
            (product_id,),
        )
    else:
        cur.execute(
            "SELECT license_key, product_id, plan, email, machine_id, "
            "activated_at, expires_at, is_active, last_seen "
            "FROM licenses ORDER BY created_at DESC"
        )

    rows = cur.fetchall()
    cur.close(); conn.close()

    licenses = [
        {
            "license_key": r[0],
            "product_id":  r[1],
            "plan":        r[2],
            "email":       r[3],
            "machine_id":  (r[4][:8] + "...") if r[4] else None,
            "activated_at": r[5].isoformat() if r[5] else None,
            "expires_at":   r[6].isoformat() if r[6] else None,
            "is_active":   r[7],
            "last_seen":   r[8].isoformat() if r[8] else None,
        }
        for r in rows
    ]
    return jsonify({"licenses": licenses, "total": len(licenses)})


@app.route("/admin/deactivate", methods=["POST"])
@admin_required
def deactivate():
    license_key = (request.json or {}).get("license_key", "").strip().upper()
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("UPDATE licenses SET is_active = FALSE WHERE license_key = %s", (license_key,))
    conn.commit()
    affected = cur.rowcount
    cur.close(); conn.close()
    return jsonify({"success": bool(affected)})


@app.route("/admin/reset-machine", methods=["POST"])
@admin_required
def reset_machine():
    """Allow license transfer to a new machine (client upgraded PC)."""
    license_key = (request.json or {}).get("license_key", "").strip().upper()
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("UPDATE licenses SET machine_id = NULL WHERE license_key = %s", (license_key,))
    conn.commit()
    affected = cur.rowcount
    cur.close(); conn.close()
    return jsonify({"success": bool(affected)})


@app.route("/admin/update-version", methods=["POST"])
@admin_required
def update_version():
    """Push a new version + download URL for all clients to pick up."""
    data        = request.json or {}
    product_id  = data.get("product_id", "stockaccounts-pro")
    version     = data.get("version")
    download_url = data.get("download_url")
    notes       = data.get("release_notes", "")

    if not version or not download_url:
        return jsonify({"error": "version and download_url required"}), 400

    conn = get_db()
    cur  = conn.cursor()
    cur.execute(
        "UPDATE products SET current_version = %s, download_url = %s, "
        "release_notes = %s, updated_at = NOW() WHERE product_id = %s",
        (version, download_url, notes, product_id),
    )
    conn.commit()
    affected = cur.rowcount
    cur.close(); conn.close()
    return jsonify({"success": bool(affected), "version": version})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
