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

PLAN_LIMITS = {
    "free": 5,
    "basic": 30,
    "pro": 150,
    "organization": 1000,
}
WINDOW_SECONDS = 4 * 60 * 60  # 4-hour rolling window


def check_and_increment_usage(subject_id, subject_type, plan="free"):
    """
    Returns (allowed: bool, remaining: int, seconds_until_reset: int)
    """
    limit = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
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
        return True, limit - 1, WINDOW_SECONDS

    elapsed = now - row["window_start"]
    if elapsed >= WINDOW_SECONDS:
        conn.execute(
            "UPDATE usage_tracking SET window_start = ?, count = 1 WHERE subject_id = ?",
            (now, subject_id),
        )
        conn.commit()
        conn.close()
        return True, limit - 1, WINDOW_SECONDS

    if row["count"] >= limit:
        conn.close()
        return False, 0, WINDOW_SECONDS - elapsed

    conn.execute("UPDATE usage_tracking SET count = count + 1 WHERE subject_id = ?", (subject_id,))
    conn.commit()
    conn.close()
    return True, limit - row["count"] - 1, WINDOW_SECONDS - elapsed
