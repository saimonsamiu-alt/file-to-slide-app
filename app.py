"""
Full MVP web app tying together every piece from the product spec that's
buildable without a live payment processor:
  - signup/login/logout/forgot-password
  - per-user personal Organization + invite/revoke members
  - guest mode with a real server-side rolling usage limit
  - file upload: pasted text OR a photo (OCR, Bangla+English)
  - rule-based engine -> template render -> downloadable .pptx
  - natural-language watermark instruction parsing (AI-optional, see
    instruction_parser.py)
  - "Train Me" upload area per organization (storage only in this MVP —
    the actual training pipeline from spec Section 5 is a later phase)
  - plan field + upgrade stub (no real payment gateway wired up yet)
"""

import os
import time
import functools
from flask import Flask, request, render_template, send_file, redirect, url_for, session, flash

import db
from engine import parse_content_to_slides, apply_watermark_instruction, TEMPLATES
from renderer import render_pptx
from ocr import extract_text_from_image
from instruction_parser import parse_instruction

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-this-in-production")

BASE_DIR = os.path.dirname(__file__)
GENERATED_DIR = os.path.join(BASE_DIR, "generated")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
ORG_UPLOAD_DIR = os.path.join(BASE_DIR, "org_uploads")
for d in (GENERATED_DIR, UPLOAD_DIR, ORG_UPLOAD_DIR):
    os.makedirs(d, exist_ok=True)

db.init_db()


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return db.get_user_by_id(uid)


@app.context_processor
def inject_user():
    return {"current_user": current_user()}


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        name = request.form.get("display_name", "").strip()
        if not email or not password:
            flash("Email and password are required.")
            return render_template("signup.html")
        user_id = db.create_user(email, password, name)
        if not user_id:
            flash("An account with that email already exists.")
            return render_template("signup.html")
        session["user_id"] = user_id
        return redirect(url_for("index"))
    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        user = db.verify_password(email, password)
        if not user:
            flash("Invalid email or password.")
            return render_template("login.html")
        session["user_id"] = user["id"]
        return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    reset_link = None
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        user = db.get_user_by_email(email)
        if user:
            token = db.create_password_reset(user["id"])
            reset_link = url_for("reset_password", token=token, _external=True)
            # DEMO MODE: showing the link directly on screen since no email
            # service is wired up yet. In production this must be emailed,
            # never shown in the UI.
        else:
            flash("If that email exists, a reset link has been created.")
    return render_template("forgot_password.html", reset_link=reset_link)


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if request.method == "POST":
        new_password = request.form.get("password", "")
        if db.use_password_reset(token, new_password):
            flash("Password updated. Please log in.")
            return redirect(url_for("login"))
        flash("That reset link is invalid or expired.")
    return render_template("reset_password.html", token=token)


@app.route("/", methods=["GET"])
def index():
    user = current_user()
    remaining = None
    if user:
        remaining = db.PLAN_LIMITS.get(user["plan"], db.PLAN_LIMITS["free"])
    return render_template("index.html", templates=TEMPLATES, remaining=remaining)


@app.route("/generate", methods=["POST"])
def generate():
    user = current_user()
    if user:
        subject_id, subject_type, plan = user["id"], "user", user["plan"]
    else:
        subject_id, subject_type, plan = f"guest:{request.remote_addr}", "guest", "free"

    allowed, remaining, seconds_left = db.check_and_increment_usage(subject_id, subject_type, plan)
    if not allowed:
        mins = seconds_left // 60
        return render_template(
            "index.html", templates=TEMPLATES,
            error=f"Limit reached for this window. Try again in ~{mins} minutes, "
                  f"or {'upgrade your plan' if user else 'sign up'} for more.",
        )

    text_content = request.form.get("content", "").strip()
    uploaded_file = request.files.get("photo")

    if uploaded_file and uploaded_file.filename:
        photo_path = os.path.join(UPLOAD_DIR, f"{int(time.time())}_{uploaded_file.filename}")
        uploaded_file.save(photo_path)
        ocr_text = extract_text_from_image(photo_path)
        text_content = (text_content + "\n\n" + ocr_text).strip() if text_content else ocr_text

    if not text_content:
        return render_template("index.html", templates=TEMPLATES, error="Please paste content or upload a photo.")

    template_key = request.form.get("template", "classic")
    template = TEMPLATES.get(template_key, TEMPLATES["classic"])

    watermark_instruction = request.form.get("watermark_instruction", "").strip()
    watermark = None
    if watermark_instruction:
        parsed = parse_instruction(watermark_instruction)
        watermark = apply_watermark_instruction(parsed)

    slides = parse_content_to_slides(text_content)
    filename = f"{int(time.time())}_{(user['id'] if user else 'guest')}.pptx"
    out_path = os.path.join(GENERATED_DIR, filename)
    render_pptx(slides, template, watermark=watermark, out_path=out_path)

    return send_file(out_path, as_attachment=True, download_name="presentation.pptx")


@app.route("/org")
@login_required
def org_dashboard():
    user = current_user()
    orgs = db.get_user_orgs(user["id"])
    org = orgs[0] if orgs else None
    members = db.get_org_members(org["id"]) if org else []
    uploads = db.get_org_uploads(org["id"]) if org else []
    return render_template("org.html", org=org, members=members, uploads=uploads)


@app.route("/org/invite", methods=["POST"])
@login_required
def org_invite():
    user = current_user()
    orgs = db.get_user_orgs(user["id"])
    if not orgs:
        return redirect(url_for("org_dashboard"))
    role = request.form.get("role", "contributor")
    code = db.create_org_invite(orgs[0]["id"], role)
    flash(f"Invite code created: {code} (share this with the contributor)")
    return redirect(url_for("org_dashboard"))


@app.route("/org/join/<code>")
@login_required
def org_join(code):
    user = current_user()
    org_id = db.redeem_invite(code, user["id"])
    if org_id:
        flash("Joined organization successfully.")
    else:
        flash("Invalid or revoked invite code.")
    return redirect(url_for("org_dashboard"))


@app.route("/org/revoke", methods=["POST"])
@login_required
def org_revoke():
    user = current_user()
    orgs = db.get_user_orgs(user["id"])
    if orgs and orgs[0]["role"] == "owner":
        db.revoke_member(orgs[0]["id"], request.form.get("user_id"))
        flash("Access revoked.")
    return redirect(url_for("org_dashboard"))


@app.route("/org/upload", methods=["POST"])
@login_required
def org_upload():
    user = current_user()
    orgs = db.get_user_orgs(user["id"])
    if not orgs:
        return redirect(url_for("org_dashboard"))
    org = orgs[0]
    f = request.files.get("deck")
    rights_confirmed = request.form.get("rights_confirmed") == "on"
    if not f or not f.filename:
        flash("Please choose a file.")
        return redirect(url_for("org_dashboard"))
    if not rights_confirmed:
        flash("You must confirm you have rights to upload this file.")
        return redirect(url_for("org_dashboard"))
    save_path = os.path.join(ORG_UPLOAD_DIR, f"{org['id']}_{int(time.time())}_{f.filename}")
    f.save(save_path)
    db.add_org_upload(org["id"], user["id"], f.filename, rights_confirmed=True)
    flash("Uploaded — thanks for contributing to training data!")
    db.add_user_credit(user["id"], 300)  # $3 in-app credit, non-cash (spec Section 7)
    return redirect(url_for("org_dashboard"))


@app.route("/upgrade", methods=["GET", "POST"])
@login_required
def upgrade():
    user = current_user()
    if request.method == "POST":
        new_plan = request.form.get("plan")
        if new_plan in db.PLAN_LIMITS:
            db.set_user_plan(user["id"], new_plan)
            flash(f"Plan updated to {new_plan} (demo only — no real payment was charged).")
        return redirect(url_for("upgrade"))
    return render_template("upgrade.html", plans=db.PLAN_LIMITS, user=user)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
