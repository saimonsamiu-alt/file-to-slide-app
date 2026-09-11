"""
SQLite data layer. Simple and dependency-light on purpose for the MVP —
swap for Postgres later if/when scale needs it, the schema shape carries over.
"""

import sqlite3
import os
import uuid
import time
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), "app.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS organizations (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        is_public INTEGER DEFAULT 0,
        plan TEXT DEFAULT 'free',
        created_at INTEGER
    );

    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        display_name TEXT,
        plan TEXT DEFAULT 'free',
        credits_cents INTEGER DEFAULT 0,   -- in-app credit, non-cash (Section 7 of spec)
        default_watermark_text TEXT,
        default_watermark_color TEXT,
        default_template TEXT DEFAULT 'classic',
        default_tuition_mode INTEGER DEFAULT 0,
        default_whatsapp TEXT,
        created_at INTEGER
    );

    CREATE TABLE IF NOT EXISTS org_members (
        org_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,   -- 'owner' | 'admin' | 'contributor'
        PRIMARY KEY (org_id, user_id),
        FOREIGN KEY (org_id) REFERENCES organizations(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS org_invites (
        code TEXT PRIMARY KEY,
        org_id TEXT NOT NULL,
        role TEXT NOT NULL,
        created_at INTEGER,
        revoked INTEGER DEFAULT 0,
        FOREIGN KEY (org_id) REFERENCES organizations(id)
    );

    CREATE TABLE IF NOT EXISTS usage_tracking (
        subject_id TEXT PRIMARY KEY,   -- user_id for logged-in, ip/device id for guests
        subject_type TEXT NOT NULL,    -- 'user' | 'guest'
        window_start INTEGER NOT NULL,
        count INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS org_uploads (
        id TEXT PRIMARY KEY,
        org_id TEXT NOT NULL,
        uploaded_by TEXT NOT NULL,
        filename TEXT NOT NULL,
        rights_confirmed INTEGER DEFAULT 0,
        status TEXT DEFAULT 'pending',  -- pending | processed
        created_at INTEGER,
        FOREIGN KEY (org_id) REFERENCES organizations(id),
        FOREIGN KEY (uploaded_by) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS password_resets (
        token TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        created_at INTEGER,
        used INTEGER DEFAULT 0
    );
    """)

    # Lightweight migration: if an existing users table predates the
    # default_* columns (e.g. a local app.db from before this update),
    # add them rather than requiring the user to delete their database.
    existing_cols = {row["name"] for row in c.execute("PRAGMA table_info(users)").fetchall()}
    for col, ddl in [
        ("default_watermark_text", "ALTER TABLE users ADD COLUMN default_watermark_text TEXT"),
        ("default_watermark_color", "ALTER TABLE users ADD COLUMN default_watermark_color TEXT"),
        ("default_template", "ALTER TABLE users ADD COLUMN default_template TEXT DEFAULT 'classic'"),
        ("default_tuition_mode", "ALTER TABLE users ADD COLUMN default_tuition_mode INTEGER DEFAULT 0"),
        ("default_whatsapp", "ALTER TABLE users ADD COLUMN default_whatsapp TEXT"),
    ]:
        if col not in existing_cols:
            c.execute(ddl)
    conn.commit()

    # Ensure the "Public" org exists (Section 6 of the spec — shared template library home)
    existing = c.execute("SELECT id FROM organizations WHERE is_public = 1").fetchone()
    if not existing:
        c.execute(
            "INSERT INTO organizations (id, name, is_public, plan, created_at) VALUES (?,?,?,?,?)",
            (str(uuid.uuid4()), "Public", 1, "free", int(time.time())),
        )

    conn.commit()
    conn.close()


def get_public_org_id():
    conn = get_db()
    row = conn.execute("SELECT id FROM organizations WHERE is_public = 1").fetchone()
    conn.close()
    return row["id"] if row else None


# ---------- Users ----------

def create_user(email, password, display_name=None):
    conn = get_db()
    user_id = str(uuid.uuid4())
    try:
        conn.execute(
            "INSERT INTO users (id, email, password_hash, display_name, plan, credits_cents, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (user_id, email.lower().strip(), generate_password_hash(password), display_name, "free", 0, int(time.time())),
        )
        # every user gets their own personal organization (owner role)
        org_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO organizations (id, name, is_public, plan, created_at) VALUES (?,?,?,?,?)",
            (org_id, f"{display_name or email}'s Org", 0, "free", int(time.time())),
        )
        conn.execute(
            "INSERT INTO org_members (org_id, user_id, role) VALUES (?,?,?)",
            (org_id, user_id, "owner"),
        )
        conn.commit()
        return user_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_user_by_email(email):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),)).fetchone()
    conn.close()
    return row


def get_user_by_id(user_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return row


def verify_password(email, password):
    user = get_user_by_email(email)
    if user and check_password_hash(user["password_hash"], password):
        return user
    return None


def set_user_plan(user_id, plan):
    conn = get_db()
    conn.execute("UPDATE users SET plan = ? WHERE id = ?", (plan, user_id))
    conn.commit()
    conn.close()


def update_user_defaults(user_id, watermark_text=None, watermark_color=None,
                          template=None, tuition_mode=None, whatsapp=None):
    """
    Only overwrites fields that were actually provided (non-None) —
    so submitting a generation without touching, say, the watermark
    field doesn't erase a previously saved default.
    """
    fields, values = [], []
    if watermark_text is not None:
        fields.append("default_watermark_text = ?"); values.append(watermark_text)
    if watermark_color is not None:
        fields.append("default_watermark_color = ?"); values.append(watermark_color)
    if template is not None:
        fields.append("default_template = ?"); values.append(template)
    if tuition_mode is not None:
        fields.append("default_tuition_mode = ?"); values.append(int(tuition_mode))
    if whatsapp is not None:
        fields.append("default_whatsapp = ?"); values.append(whatsapp)
    if not fields:
        return
    values.append(user_id)
    conn = get_db()
    conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    conn.close()


def add_user_credit(user_id, cents):
    conn = get_db()
    conn.execute("UPDATE users SET credits_cents = credits_cents + ? WHERE id = ?", (cents, user_id))
    conn.commit()
    conn.close()


# ---------- Password reset (demo mode: token shown on-screen, no real email sending wired up) ----------

def create_password_reset(user_id):
    conn = get_db()
    token = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO password_resets (token, user_id, created_at, used) VALUES (?,?,?,0)",
        (token, user_id, int(time.time())),
    )
    conn.commit()
    conn.close()
    return token


def use_password_reset(token, new_password):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM password_resets WHERE token = ? AND used = 0", (token,)
    ).fetchone()
    if not row:
        conn.close()
        return False
    # tokens valid for 1 hour
    if int(time.time()) - row["created_at"] > 3600:
        conn.close()
        return False
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(new_password), row["user_id"]))
    conn.execute("UPDATE password_resets SET used = 1 WHERE token = ?", (token,))
    conn.commit()
    conn.close()
    return True


# ---------- Organizations ----------

def get_user_orgs(user_id):
    conn = get_db()
    rows = conn.execute(
        """SELECT o.*, m.role FROM organizations o
           JOIN org_members m ON o.id = m.org_id
           WHERE m.user_id = ? AND o.is_public = 0""",
        (user_id,),
    ).fetchall()
    conn.close()
    return rows


def create_org_invite(org_id, role="contributor"):
    conn = get_db()
    code = uuid.uuid4().hex[:10]
    conn.execute(
        "INSERT INTO org_invites (code, org_id, role, created_at, revoked) VALUES (?,?,?,?,0)",
        (code, org_id, role, int(time.time())),
    )
    conn.commit()
    conn.close()
    return code


def redeem_invite(code, user_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM org_invites WHERE code = ? AND revoked = 0", (code,)).fetchone()
    if not row:
        conn.close()
        return None
    conn.execute(
        "INSERT OR REPLACE INTO org_members (org_id, user_id, role) VALUES (?,?,?)",
        (row["org_id"], user_id, row["role"]),
    )
    conn.commit()
    org_id = row["org_id"]
    conn.close()
    return org_id


def revoke_member(org_id, user_id):
    conn = get_db()
    conn.execute("DELETE FROM org_members WHERE org_id = ? AND user_id = ?", (org_id, user_id))
    conn.commit()
    conn.close()


def get_org_members(org_id):
    conn = get_db()
    rows = conn.execute(
        """SELECT u.id, u.email, u.display_name, m.role FROM users u
           JOIN org_members m ON u.id = m.user_id
           WHERE m.org_id = ?""",
        (org_id,),
    ).fetchall()
    conn.close()
    return rows


def add_org_upload(org_id, uploaded_by, filename, rights_confirmed):
    conn = get_db()
    upload_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO org_uploads (id, org_id, uploaded_by, filename, rights_confirmed, status, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (upload_id, org_id, uploaded_by, filename, int(rights_confirmed), "pending", int(time.time())),
    )
    conn.commit()
    conn.close()
    return upload_id


def get_org_uploads(org_id):
    conn = get_db()
    rows = conn.execute("SELECT * FROM org_uploads WHERE org_id = ? ORDER BY created_at DESC", (org_id,)).fetchall()
    conn.close()
    return rows


# ---------- Usage / rolling-window limiter (Section 8 of the spec) ----------
#
# Two separate limits, because they protect different things:
#   - General generation (rule engine only) costs nothing to run, so its
#     limit only exists to stop abuse/server load — it can be generous.
#   - AI-powered generation (tuition mode, real Claude API calls) costs
#     real money per use, so it needs its own, much tighter budget-based
#     limit, tracked separately and on a longer (daily) window.

PLAN_LIMITS = {
    "free": 30,
    "basic": 150,
    "pro": 500,
    "organization": 5000,
}
WINDOW_SECONDS = 4 * 60 * 60  # 4-hour rolling window, general usage

AI_PLAN_LIMITS = {
    "free": 3,
    "basic": 15,
    "pro": 60,
    "organization": 300,
}
AI_WINDOW_SECONDS = 24 * 60 * 60  # 24-hour rolling window, AI usage only


def _check_and_increment(subject_id, plan, limits, window_seconds, subject_type="user"):
    limit = limits.get(plan, limits["free"])
    now = int(time.time())
    conn = get_db()
    row = conn.execute("SELECT * FROM usage_tracking WHERE subject_id = ?", (subject_id,)).fetchone()

    if row is None:
        conn.execute(
            "INSERT INTO usage_tracking (subject_id, subject_type, window_start, count) VALUES (?,?,?,1)",
            (subject_id, subject_type, now),
        )
        conn.commit()
        conn.close()
        return True, limit - 1, window_seconds

    elapsed = now - row["window_start"]
    if elapsed >= window_seconds:
        conn.execute(
            "UPDATE usage_tracking SET window_start = ?, count = 1 WHERE subject_id = ?",
            (now, subject_id),
        )
        conn.commit()
        conn.close()
        return True, limit - 1, window_seconds

    if row["count"] >= limit:
        conn.close()
        return False, 0, window_seconds - elapsed

    conn.execute("UPDATE usage_tracking SET count = count + 1 WHERE subject_id = ?", (subject_id,))
    conn.commit()
    conn.close()
    return True, limit - row["count"] - 1, window_seconds - elapsed


def check_and_increment_usage(subject_id, subject_type, plan="free"):
    """General (no-AI) generation limit. Returns (allowed, remaining, seconds_until_reset)."""
    return _check_and_increment(subject_id, plan, PLAN_LIMITS, WINDOW_SECONDS, subject_type)


def check_and_increment_ai_usage(subject_id, subject_type, plan="free"):
    """AI-powered (tuition mode) generation limit — separate budget, separate window."""
    ai_subject_id = f"ai:{subject_id}"
    return _check_and_increment(ai_subject_id, plan, AI_PLAN_LIMITS, AI_WINDOW_SECONDS, subject_type)
