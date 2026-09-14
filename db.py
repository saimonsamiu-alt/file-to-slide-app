"""
PostgreSQL data layer (persistent — survives redeploys, unlike the
ephemeral SQLite file this used to be). Requires a DATABASE_URL
environment variable pointing at a Postgres instance (a free Neon.tech
or Supabase database both work fine for this scale — see README).
"""

import os
import uuid
import time
import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash, check_password_hash

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set. This app needs a Postgres connection "
            "string (a free one from neon.tech or supabase.com works) — set "
            "it as an environment variable. See README for setup steps."
        )
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
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
        credits_cents INTEGER DEFAULT 0,
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
        role TEXT NOT NULL,
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
        subject_id TEXT PRIMARY KEY,
        subject_type TEXT NOT NULL,
        window_start INTEGER NOT NULL,
        count INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS org_uploads (
        id TEXT PRIMARY KEY,
        org_id TEXT NOT NULL,
        uploaded_by TEXT NOT NULL,
        filename TEXT NOT NULL,
        file_data BYTEA,
        storage_key TEXT,
        content_hash TEXT,
        rights_confirmed INTEGER DEFAULT 0,
        status TEXT DEFAULT 'pending',
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

    CREATE TABLE IF NOT EXISTS parsed_slides (
        id TEXT PRIMARY KEY,
        upload_id TEXT NOT NULL,
        org_id TEXT NOT NULL,
        slide_index INTEGER,
        raw_text TEXT,
        bullet_count INTEGER,
        has_image INTEGER,
        category TEXT,
        created_at INTEGER,
        FOREIGN KEY (upload_id) REFERENCES org_uploads(id),
        FOREIGN KEY (org_id) REFERENCES organizations(id)
    );
    """)
    conn.commit()

    # Lightweight migration: add columns that might not exist on a
    # database created before this update, instead of requiring a
    # manual reset.
    c.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'")
    existing_cols = {row["column_name"] for row in c.fetchall()}
    for col, ddl in [
        ("default_watermark_text", "ALTER TABLE users ADD COLUMN default_watermark_text TEXT"),
        ("default_watermark_color", "ALTER TABLE users ADD COLUMN default_watermark_color TEXT"),
        ("default_template", "ALTER TABLE users ADD COLUMN default_template TEXT DEFAULT 'classic'"),
        ("default_tuition_mode", "ALTER TABLE users ADD COLUMN default_tuition_mode INTEGER DEFAULT 0"),
        ("default_whatsapp", "ALTER TABLE users ADD COLUMN default_whatsapp TEXT"),
    ]:
        if col not in existing_cols:
            c.execute(ddl)

    c.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'org_uploads'")
    existing_upload_cols = {row["column_name"] for row in c.fetchall()}
    if "file_data" not in existing_upload_cols:
        c.execute("ALTER TABLE org_uploads ADD COLUMN file_data BYTEA")
    if "content_hash" not in existing_upload_cols:
        c.execute("ALTER TABLE org_uploads ADD COLUMN content_hash TEXT")
    if "storage_key" not in existing_upload_cols:
        c.execute("ALTER TABLE org_uploads ADD COLUMN storage_key TEXT")
    conn.commit()

    # Ensure the "Public" org exists (Section 6 of the spec — shared template library home)
    c.execute("SELECT id FROM organizations WHERE is_public = 1")
    existing = c.fetchone()
    if not existing:
        c.execute(
            "INSERT INTO organizations (id, name, is_public, plan, created_at) VALUES (%s,%s,%s,%s,%s)",
            (str(uuid.uuid4()), "Public", 1, "free", int(time.time())),
        )

    conn.commit()
    conn.close()


def get_public_org_id():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM organizations WHERE is_public = 1")
    row = c.fetchone()
    conn.close()
    return row["id"] if row else None


# ---------- Users ----------

def create_user(email, password, display_name=None):
    conn = get_db()
    c = conn.cursor()
    user_id = str(uuid.uuid4())
    try:
        c.execute(
            "INSERT INTO users (id, email, password_hash, display_name, plan, credits_cents, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (user_id, email.lower().strip(), generate_password_hash(password), display_name, "free", 0, int(time.time())),
        )
        org_id = str(uuid.uuid4())
        c.execute(
            "INSERT INTO organizations (id, name, is_public, plan, created_at) VALUES (%s,%s,%s,%s,%s)",
            (org_id, f"{display_name or email}'s Org", 0, "free", int(time.time())),
        )
        c.execute(
            "INSERT INTO org_members (org_id, user_id, role) VALUES (%s,%s,%s)",
            (org_id, user_id, "owner"),
        )
        conn.commit()
        return user_id
    except psycopg2.IntegrityError:
        conn.rollback()
        return None
    finally:
        conn.close()


def get_user_by_email(email):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE email = %s", (email.lower().strip(),))
    row = c.fetchone()
    conn.close()
    return row


def get_user_by_id(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    row = c.fetchone()
    conn.close()
    return row


def verify_password(email, password):
    user = get_user_by_email(email)
    if user and check_password_hash(user["password_hash"], password):
        return user
    return None


def set_user_plan(user_id, plan):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET plan = %s WHERE id = %s", (plan, user_id))
    conn.commit()
    conn.close()


def update_user_defaults(user_id, watermark_text=None, watermark_color=None,
                          template=None, tuition_mode=None, whatsapp=None):
    fields, values = [], []
    if watermark_text is not None:
        fields.append("default_watermark_text = %s"); values.append(watermark_text)
    if watermark_color is not None:
        fields.append("default_watermark_color = %s"); values.append(watermark_color)
    if template is not None:
        fields.append("default_template = %s"); values.append(template)
    if tuition_mode is not None:
        fields.append("default_tuition_mode = %s"); values.append(int(tuition_mode))
    if whatsapp is not None:
        fields.append("default_whatsapp = %s"); values.append(whatsapp)
    if not fields:
        return
    values.append(user_id)
    conn = get_db()
    c = conn.cursor()
    c.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = %s", values)
    conn.commit()
    conn.close()


def add_user_credit(user_id, cents):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET credits_cents = credits_cents + %s WHERE id = %s", (cents, user_id))
    conn.commit()
    conn.close()


# ---------- Password reset (demo mode: token shown on-screen, no real email sending wired up) ----------

def create_password_reset(user_id):
    conn = get_db()
    c = conn.cursor()
    token = uuid.uuid4().hex
    c.execute(
        "INSERT INTO password_resets (token, user_id, created_at, used) VALUES (%s,%s,%s,0)",
        (token, user_id, int(time.time())),
    )
    conn.commit()
    conn.close()
    return token


def use_password_reset(token, new_password):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM password_resets WHERE token = %s AND used = 0", (token,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False
    if int(time.time()) - row["created_at"] > 3600:
        conn.close()
        return False
    c.execute("UPDATE users SET password_hash = %s WHERE id = %s", (generate_password_hash(new_password), row["user_id"]))
    c.execute("UPDATE password_resets SET used = 1 WHERE token = %s", (token,))
    conn.commit()
    conn.close()
    return True


# ---------- Organizations ----------

def get_user_orgs(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """SELECT o.*, m.role FROM organizations o
           JOIN org_members m ON o.id = m.org_id
           WHERE m.user_id = %s AND o.is_public = 0""",
        (user_id,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def create_org_invite(org_id, role="contributor"):
    conn = get_db()
    c = conn.cursor()
    code = uuid.uuid4().hex[:10]
    c.execute(
        "INSERT INTO org_invites (code, org_id, role, created_at, revoked) VALUES (%s,%s,%s,%s,0)",
        (code, org_id, role, int(time.time())),
    )
    conn.commit()
    conn.close()
    return code


def redeem_invite(code, user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM org_invites WHERE code = %s AND revoked = 0", (code,))
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    c.execute(
        """INSERT INTO org_members (org_id, user_id, role) VALUES (%s,%s,%s)
           ON CONFLICT (org_id, user_id) DO UPDATE SET role = EXCLUDED.role""",
        (row["org_id"], user_id, row["role"]),
    )
    conn.commit()
    org_id = row["org_id"]
    conn.close()
    return org_id


def revoke_member(org_id, user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM org_members WHERE org_id = %s AND user_id = %s", (org_id, user_id))
    conn.commit()
    conn.close()


def get_org_members(org_id):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """SELECT u.id, u.email, u.display_name, m.role FROM users u
           JOIN org_members m ON u.id = m.user_id
           WHERE m.org_id = %s""",
        (org_id,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def add_org_upload(org_id, uploaded_by, filename, rights_confirmed, file_data=None, content_hash=None):
    """
    file_data: raw bytes of the uploaded file. If R2 is configured
    (storage_r2.is_configured()), the bytes are uploaded to R2 and
    only a storage_key reference is kept in Postgres — this keeps the
    database small (Neon's free tier is only 0.5GB) and avoids R2
    egress fees since files are read back by this same server.
    Falls back to storing bytes directly in Postgres if R2 isn't set
    up, so this works either way.
    content_hash: sha256 hex digest of file_data — used for duplicate
    detection (find_upload_by_hash) so the same file re-uploaded
    doesn't get credited/processed twice.
    """
    import storage_r2

    upload_id = str(uuid.uuid4())
    storage_key = None
    db_file_data = None

    if file_data:
        if storage_r2.is_configured():
            storage_key = f"org_uploads/{org_id}/{upload_id}_{filename}"
            storage_r2.upload_bytes(storage_key, file_data)
        else:
            db_file_data = file_data

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO org_uploads (id, org_id, uploaded_by, filename, file_data, storage_key, content_hash, rights_confirmed, status, created_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (upload_id, org_id, uploaded_by, filename,
         psycopg2.Binary(db_file_data) if db_file_data else None,
         storage_key, content_hash,
         int(rights_confirmed), "pending", int(time.time())),
    )
    conn.commit()
    conn.close()
    return upload_id


def find_upload_by_hash(org_id, content_hash):
    """Returns the existing upload row with this content hash in this
    org, or None — used to detect and skip duplicate uploads."""
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT id, filename, status FROM org_uploads WHERE org_id = %s AND content_hash = %s LIMIT 1",
        (org_id, content_hash),
    )
    row = c.fetchone()
    conn.close()
    return row


def get_org_uploads(org_id):
    conn = get_db()
    c = conn.cursor()
    # file_data excluded here deliberately — it can be large, and this
    # is only used to render the upload-history list.
    c.execute(
        "SELECT id, org_id, uploaded_by, filename, rights_confirmed, status, created_at "
        "FROM org_uploads WHERE org_id = %s ORDER BY created_at DESC",
        (org_id,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def get_org_upload_file(upload_id):
    """
    Returns {"filename": ..., "file_data": <bytes>} — fetched from R2
    if storage_key is set, otherwise from the legacy Postgres bytea
    column. Either way the caller gets plain bytes back, transparently.
    """
    import storage_r2

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT filename, file_data, storage_key FROM org_uploads WHERE id = %s", (upload_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    if row["storage_key"]:
        data = storage_r2.download_bytes(row["storage_key"])
    else:
        data = bytes(row["file_data"]) if row["file_data"] else None
    return {"filename": row["filename"], "file_data": data}


def set_upload_status(upload_id, status):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE org_uploads SET status = %s WHERE id = %s", (status, upload_id))
    conn.commit()
    conn.close()


def save_parsed_slides(upload_id, org_id, slides):
    """slides: list of {"raw_text","bullet_count","has_image","category"}"""
    conn = get_db()
    c = conn.cursor()
    now = int(time.time())
    for i, s in enumerate(slides):
        c.execute(
            "INSERT INTO parsed_slides (id, upload_id, org_id, slide_index, raw_text, bullet_count, has_image, category, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (str(uuid.uuid4()), upload_id, org_id, i, s["raw_text"], s["bullet_count"], int(s["has_image"]), s["category"], now),
        )
    conn.commit()
    conn.close()


def get_category_counts(org_id=None):
    """
    Counts labeled slides per category — this is exactly the number
    the spec's Section 12 threshold (~500-1000 per category) tracks
    against, to know when there's "enough" data for a category.
    """
    conn = get_db()
    c = conn.cursor()
    if org_id:
        c.execute("SELECT category, COUNT(*) as n FROM parsed_slides WHERE org_id = %s GROUP BY category", (org_id,))
    else:
        c.execute("SELECT category, COUNT(*) as n FROM parsed_slides GROUP BY category")
    rows = c.fetchall()
    conn.close()
    return {r["category"]: r["n"] for r in rows}


# ---------- Usage / rolling-window limiter (Section 8 of the spec) ----------
#
# Two separate limits, because they protect different things:
#   - General generation (rule engine only) costs nothing to run, so its
#     limit only exists to stop abuse/server load — it can be generous.
#   - AI-powered generation (tuition mode, real Gemini API calls) costs
#     real quota per use, so it needs its own, much tighter budget-based
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
    c = conn.cursor()
    c.execute("SELECT * FROM usage_tracking WHERE subject_id = %s", (subject_id,))
    row = c.fetchone()

    if row is None:
        c.execute(
            "INSERT INTO usage_tracking (subject_id, subject_type, window_start, count) VALUES (%s,%s,%s,1)",
            (subject_id, subject_type, now),
        )
        conn.commit()
        conn.close()
        return True, limit - 1, window_seconds

    elapsed = now - row["window_start"]
    if elapsed >= window_seconds:
        c.execute(
            "UPDATE usage_tracking SET window_start = %s, count = 1 WHERE subject_id = %s",
            (now, subject_id),
        )
        conn.commit()
        conn.close()
        return True, limit - 1, window_seconds

    if row["count"] >= limit:
        conn.close()
        return False, 0, window_seconds - elapsed

    c.execute("UPDATE usage_tracking SET count = count + 1 WHERE subject_id = %s", (subject_id,))
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
