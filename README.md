# File → Slide (Full MVP)

Turns pasted text and/or an uploaded photo (Bangla + English OCR) into a
downloadable PowerPoint (.pptx). Built around the product spec's cost
philosophy: a rule-based engine handles content → slide mapping with
**zero AI cost**, and AI is only used (optionally) for parsing free-text
watermark instructions.

## What's built and tested

- **Auth:** signup, login, logout, forgot-password → reset-password
  (demo mode: reset link is shown on-screen since no email service is
  wired up — see "Before real launch" below).
- **Organizations:** every signup gets a personal Organization
  automatically. Owners can generate invite codes (contributor/admin
  roles) and revoke members. A "Public" organization is created
  automatically for the future shared template library.
- **Guest mode:** no login required to try it, with a real **server-side**
  rolling usage limit (SQLite-backed, survives server restarts — not the
  in-memory placeholder from the earlier version).
- **File input:** paste text, upload up to 20 photos, or both. Each
  photo becomes its own slide/question. Photos run through Tesseract
  OCR with `ben+eng` (Bangla + English together, for code-switched
  content).
- **Tuition mode (`tuition_rewrite.py`):** a checkbox that runs the
  content through a real AI call (Claude) which rewrites each question
  in new wording, strips answers, lightly varies numbers while
  preserving constants/atomic masses/balanced equations, keeps
  board/university references, and auto-adds a title page (heading +
  topic + WhatsApp number) and the "Samiu's Tuition" watermark —
  encoding the exact rules given for Samiu's Tuition practice slides.
  **Requires `GEMINI_API_KEY`** set as an environment variable, or
  it returns a clear error explaining that instead of crashing.
- **PDF export:** tuition mode always outputs PDF (per the tuition
  rules); the regular flow has a "Generate as PDF instead" button.
  Conversion uses headless LibreOffice (`libreoffice-impress`, now in
  the Dockerfile) — this makes the Docker image noticeably larger and
  the first build slower, that's expected.
- **Two-tier usage limits:** general (rule-engine) generation is cheap
  to run, so its free-tier limit is generous (30 per 4-hour window).
  Tuition mode makes a real paid AI call, so it has its own, much
  tighter budget — 3 per 24 hours on the free plan — tracked
  completely separately in `db.py` (`PLAN_LIMITS` vs `AI_PLAN_LIMITS`).
  Turning tuition mode off has no AI limit at all. Adjust the numbers
  in `db.py` any time — they're just constants, not a fixed design.
- **Error handling:** `/generate` catches exceptions, logs the full
  traceback server-side (visible in Render's Logs tab), and shows the
  user a specific message instead of a bare "Internal Server Error" —
  if something breaks in production, check Render's logs first, the
  real cause will be there.
- **Rule engine (`engine.py`):** no AI — blank-line-separated blocks
  become slides, first line = title, rest = bullets.
- **Renderer (`renderer.py`):** builds an actual `.pptx` with 3 starter
  templates (Classic, Dark, Warm/Education) and a rule-based watermark
  (text, color, opacity-as-lightening, diagonal rotation).
- **Instruction parsing (`instruction_parser.py`):** free-text watermark
  commands (e.g. *"add a light watermark for 'Samiu's Tuition'"*) are
  parsed into structured params. Works with **zero AI cost** out of the
  box via a regex/keyword parser. If you set a `GEMINI_API_KEY`
  environment variable, it automatically upgrades to a real (cheap)
  Claude API call for more robust parsing of arbitrary phrasing, with
  automatic fallback to the free parser if the call fails.
- **Train Me (`/org` page):** organization owners can invite
  contributors, who can upload presentation files (with a required
  rights-confirmation checkbox) into that org's private pool. Each
  upload currently earns the uploader $3 of **in-app credit**
  (non-cash, stored on their account — spend it via `/upgrade`).
- **Plans (`/upgrade`):** Free/Basic/Pro/Organization tiers with
  different per-window generation limits — this is a **demo stub**,
  no real payment gateway is connected yet.

Every piece above was tested end-to-end with Flask's test client
(signup → generate → org invite/upload → credit awarded → plan switch →
password reset → re-login → guest limit correctly blocking after 5 uses).

## Run it locally

```bash
# system dependency for OCR (Ubuntu/Debian):
sudo apt-get install tesseract-ocr tesseract-ocr-ben

pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000`.

Optional — enable real AI-based instruction parsing:
```bash
export GEMINI_API_KEY=your-key-here
python app.py
```

## What's intentionally NOT built yet (next phases, per the product spec)

1. **Real email sending** for password reset — currently shown on-screen
   in demo mode. Needs a provider (SendGrid, SES, etc.) before real launch.
2. **Real payment gateway** on `/upgrade` — currently just flips a
   database field. Needs Stripe/local payment method (bKash, Nagad, etc.
   for the Bangladesh market) plus the store-specific subscription
   disclosure rules noted in the spec (Section 9).
3. **Tier 2 (classifier)** — automatic template selection based on
   content features, instead of manual template choice.
4. **Tier 3 (trained model)** — real custom-layout generation via a
   small model trained on accumulated data; currently only the AI
   fallback for *instruction parsing* exists, not full layout generation.
5. **Duplicate-upload detection and the "enough data per category"
   payout phase-out** for Train Me contributions (spec Section 7) —
   currently every valid upload earns credit with no dedup check.
6. **Production-grade server** — `app.py`'s `debug=True` dev server must
   be replaced with a real WSGI server (gunicorn/uwsgi) behind a reverse
   proxy before going live.
7. **Mobile apps** — this is the web app phase; iOS/Android wrapping or
   native rebuild comes after the web version is validated.

## Direction: what to do next

1. **Create your GitHub repo** and push this project as-is:
   ```bash
   git init
   git add .
   git commit -m "Initial MVP: auth, orgs, rule engine, OCR, watermark parsing"
   git branch -M main
   git remote add origin <your-repo-url>
   git push -u origin main
   ```
2. **Deploy the web app somewhere reachable** for real testing (not just
   localhost). A `Dockerfile` is included specifically because Tesseract
   OCR is a system-level package that plain "buildpack" deploys often
   can't install — Docker guarantees it's always there. Render and
   Railway both support "deploy from Dockerfile" directly from a GitHub
   repo, and redeploy automatically on every push (matching the
   "day by day" iteration plan):
   - **Render:** New → Web Service → connect your GitHub repo → it
     auto-detects the `Dockerfile` → set the `SECRET_KEY` environment
     variable → deploy. Free tier is enough to start.
   - **Railway:** New Project → Deploy from GitHub repo → it also
     auto-detects the `Dockerfile` → add `SECRET_KEY` under Variables →
     deploy.
   - A VPS (DigitalOcean/Linode) works too if you'd rather run
     `docker build` and `docker run` yourself — more control, more setup.
3. **Swap `SECRET_KEY`** to a real random value via an environment
   variable before deploying — don't leave the dev default in production.
4. **Start the 100–200 person beta** (as planned) once it's deployed
   somewhere real people can reach — this is what starts generating the
   real usage data the Section 5 training strategy depends on.
5. **Bring this repo + `slides-app-product-spec.md` into Claude Code**
   for the next build phase — email sending, real payments, and the
   classifier are the natural next pieces, roughly in that order of
   how soon you'll need them.
