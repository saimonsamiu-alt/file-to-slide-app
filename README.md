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
  rolling usage limit (Postgres-backed, survives server restarts).
- **R2 file storage (`storage_r2.py`):** Train Me uploads now go to
  Cloudflare R2 (S3-compatible, 10GB free, no egress fees) when
  configured, instead of Postgres — Neon's free tier is only 0.5GB,
  which fills up fast storing files as bytea. Falls back to storing
  in Postgres automatically if R2 env vars aren't set, so this is
  safe to deploy either way. See "R2 setup" below.
- **Memory-crash fixes:** the service was hitting Render's 512MB
  free-tier RAM limit and getting force-restarted (which shows up as
  a 502 to the browser). Fixed by: resizing uploaded photos to a
  reasonable max dimension before OCR/vision (phone photos are often
  3000px+ and several MB), lowering PDF page-render resolution,
  releasing PyMuPDF page memory promptly, and reducing gunicorn to a
  single worker with periodic recycling (`--max-requests`) instead of
  2 workers that could together exceed the RAM limit under load.
- **Bangla PDF text extraction fix:** many real-world Bangla PDFs
  (including ones built by embedding a custom font) don't carry a
  correct Unicode mapping in their text layer — extracting text
  directly yields garbled control-character soup even though the page
  displays correctly. Fixed by rendering each PDF page to an image
  (PyMuPDF) and reading it via the same vision-based extraction as
  photo uploads, instead of pulling the embedded text layer. Verified
  against a real affected file — output went from unreadable garbage
  to clean Bangla text.
- **Math equation rendering (`math_render.py` + `vision_ocr.py`):**
  plain OCR (Tesseract) cannot read mathematical notation — fractions,
  roots, trig functions come out as garbled characters. For photo
  uploads, the app now tries Gemini's vision understanding first
  (`vision_ocr.py`) to transcribe the image, marking any equation as
  a `$...$` mathtext expression; falls back to plain Tesseract OCR if
  no API key or the vision call fails. Tuition mode's renderer then
  detects `$...$` segments in the AI-rewritten question text and draws
  them as properly typeset math images (`math_render.py`, via
  matplotlib's mathtext — no LaTeX install needed) instead of broken
  plain text. Tested end-to-end with a real trigonometry identity.
  plain OCR (Tesseract) cannot read mathematical notation — fractions,
  roots, trig functions come out as garbled characters. For photo
  uploads, the app now tries Gemini's vision understanding first
  (`vision_ocr.py`) to transcribe the image, marking any equation as
  a `$...$` mathtext expression; falls back to plain Tesseract OCR if
  no API key or the vision call fails. Tuition mode's renderer then
  detects `$...$` segments in the AI-rewritten question text and draws
  them as properly typeset math images (`math_render.py`, via
  matplotlib's mathtext — no LaTeX install needed) instead of broken
  plain text. Tested end-to-end with a real trigonometry identity.
- **File input:** paste text, upload up to 20 photos (click, drag, or
  paste with Ctrl+V — a proper multi-box picker, not just a plain file
  input), or both. Each photo becomes its own slide/question.
- **Persistent database (PostgreSQL):** all accounts, organizations,
  usage counters, and Train Me uploads (including the actual file
  bytes, stored directly in the database) now live in a real Postgres
  database via `DATABASE_URL` — **this survives redeploys.** The app
  used to use a local SQLite file, which reset every time the server
  redeployed (Render's free tier has no persistent disk) — that's why
  accounts and uploads kept disappearing. See "Database setup" below.
- **Tuition mode (`tuition_rewrite.py` + `render_pptx_tuition` in
  `renderer.py`):** a checkbox that runs the content through a real AI
  call (Gemini) which rewrites each question in new wording, strips
  answers, lightly varies numbers while preserving constants/atomic
  masses/balanced equations, keeps board/university references (in a
  separate right-aligned tag line), and renders using Samiu's
  Tuition's own polished design — dark header bar with topic label +
  page counter, the diagonal watermark, title slide with WhatsApp
  contact — ported from a Node/pptxgenjs script the user already had
  and validated against. **Requires `GEMINI_API_KEY`** set as an
  environment variable, or it returns a clear error explaining that
  instead of crashing.
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

## R2 setup (optional but recommended)

Without this, uploaded training files are stored directly in Postgres
(works fine at small scale, but Neon's free tier is only 0.5GB total).
To use Cloudflare R2 instead (10GB free, no egress fees):

1. Sign up at cloudflare.com, go to R2 in the dashboard, create a bucket
   (any name, e.g. `slideapp-uploads`).
2. Create an R2 API token (R2 → Manage API Tokens → Create API Token)
   with read/write access to that bucket. Note the Account ID, Access
   Key ID, and Secret Access Key it gives you.
3. Set these environment variables (locally and on Render):
   - `R2_ACCOUNT_ID`
   - `R2_ACCESS_KEY_ID`
   - `R2_SECRET_ACCESS_KEY`
   - `R2_BUCKET_NAME` (the bucket name from step 1)

The app detects these automatically — no code change needed. Existing
files already stored in Postgres stay there and still work; only new
uploads after this is configured go to R2.

## Database setup (required — do this first)

This app needs a PostgreSQL database. A free one is enough for this
scale. Two good free options:

1. **Neon** (neon.tech) — sign up, create a project, copy the
   "Connection string" it gives you (looks like
   `postgresql://user:password@ep-xxxx.neon.tech/dbname?sslmode=require`).
2. **Supabase** (supabase.com) — sign up, create a project, go to
   Project Settings → Database → Connection string (URI format).

Either way, set the connection string as an environment variable
named `DATABASE_URL` — locally (`export DATABASE_URL=...`) and on
Render (Environment tab → Add Environment Variable). The app creates
its own tables automatically on first run (`db.init_db()` is called
at startup) — no manual schema setup needed.

**Why this matters:** without `DATABASE_URL` set, the app cannot start
— there is no SQLite fallback anymore, specifically so that data never
silently lives somewhere non-persistent again.

## Run it locally

```bash
# system dependency for OCR (Ubuntu/Debian):
sudo apt-get install tesseract-ocr tesseract-ocr-ben

pip install -r requirements.txt
export DATABASE_URL=your-postgres-connection-string
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
6. **The remaining training pipeline steps** (spec Section 5) — Train Me
   now parses .pptx/.pdf uploads and labels each slide's category via
   AI (`training_pipeline.py`), storing the results in `parsed_slides`.
   What's still missing: automatic dedup of near-identical uploads,
   the "enough data per category" reward phase-out, and — once each
   category has enough labeled examples (~500-1,000, tracked live on
   the `/org` page) — actually training a small classifier on that
   data and wiring it into the app as Tier 2.
7. **Production-grade server** — `app.py`'s `debug=True` dev server must
   be replaced with a real WSGI server (gunicorn/uwsgi) behind a reverse
   proxy before going live.
8. **Mobile apps** — this is the web app phase; iOS/Android wrapping or
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
