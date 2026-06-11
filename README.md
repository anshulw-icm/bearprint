# Bearprint — Deployment Guide

A fullstack market breadth index. Zero cost. Live in ~1 hour.

---

## What you're deploying

```
NSE Bhavcopy (free CSV)
        ↓
Python compute.py  ← runs daily via GitHub Actions
        ↓
Supabase PostgreSQL (free hosted database)
        ↓
FastAPI backend    ← hosted free on Render.com
        ↓
HTML frontend      ← hosted free on GitHub Pages / Netlify
```

---

## Step 1 — Set up Supabase (10 min)

1. Go to **supabase.com** → "Start your project" → sign up free
2. Create a new project (name it `bearprint`, pick any region, set a DB password)
3. Wait ~2 min for provisioning
4. Go to **SQL Editor** → "New query"
5. Paste the entire contents of `backend/schema.sql` and click **Run**
6. You should see tables `bearprint_daily` and `feedback` created
7. Go to **Settings → API** and copy:
   - **Project URL** → save as `SUPABASE_URL`
   - **anon/public key** → save as `SUPABASE_KEY`

---

## Step 2 — Push code to GitHub (5 min)

1. Create a new repo at github.com (name it `bearprint`, set to Public)
2. Push this entire folder:
   ```bash
   git init
   git add .
   git commit -m "Initial Bearprint POC"
   git remote add origin https://github.com/YOUR_USERNAME/bearprint.git
   git push -u origin main
   ```
3. Go to **Settings → Secrets and variables → Actions → New repository secret**
   - Add `SUPABASE_URL` (your Supabase project URL)
   - Add `SUPABASE_KEY` (your Supabase anon key)
4. Copy `scheduler/cron.yml` to `.github/workflows/cron.yml` in your repo
   ```bash
   mkdir -p .github/workflows
   cp scheduler/cron.yml .github/workflows/cron.yml
   git add .github/workflows/cron.yml
   git commit -m "Add daily compute action"
   git push
   ```

---

## Step 3 — Deploy API on Render (10 min)

1. Go to **render.com** → sign up free with GitHub
2. "New Web Service" → connect your `bearprint` GitHub repo
3. Settings:
   - **Root directory**: `backend`
   - **Build command**: `pip install -r requirements.txt`
   - **Start command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Free
4. Add environment variables:
   - `SUPABASE_URL` = your Supabase URL
   - `SUPABASE_KEY` = your Supabase key
5. Click **Deploy** — takes ~3 min
6. Your API URL will be: `https://bearprint-api.onrender.com`
7. Test it: visit `https://bearprint-api.onrender.com/today` in your browser

---

## Step 4 — Update frontend with your API URL (2 min)

Open `frontend/index.html` and find this line near the top of the `<script>` block:

```js
const API = window.BEARPRINT_API || "https://bearprint-api.onrender.com";
```

Replace the URL with your actual Render URL. Save the file.

---

## Step 5 — Deploy frontend on Netlify (5 min)

1. Go to **netlify.com** → sign up free
2. Drag and drop the `frontend/` folder onto the Netlify deploy area
3. You get a live URL instantly: `https://random-name.netlify.app`
4. Optional: set a custom domain or rename it in Netlify settings

---

## Step 6 — Run first compute manually (5 min)

The GitHub Action runs daily at 4pm IST, but to seed data immediately:

1. Go to your GitHub repo → **Actions** → "Bearprint daily compute"
2. Click **Run workflow** → Run
3. Watch the logs — it will fetch NSE data and write to your DB
4. Refresh your live webapp — hero number should update from live data

> **Note**: The schema.sql file includes 30 days of seed data so your webapp
> looks meaningful even before the first live compute run.

---

## File structure

```
bearprint/
├── backend/
│   ├── compute.py        # NSE fetcher + Bearprint calculator
│   ├── main.py           # FastAPI server (3 endpoints)
│   ├── schema.sql        # Supabase database setup
│   └── requirements.txt  # Python dependencies
├── frontend/
│   └── index.html        # Complete webapp (Apple design system)
├── scheduler/
│   └── cron.yml          # GitHub Actions daily job
├── render.yaml           # Render.com deployment config
└── README.md             # This file
```

---

## Endpoints reference

| Endpoint | Method | What it returns |
|---|---|---|
| `/today` | GET | Today's Bearprint value, zone, losers, avg_7d |
| `/history?days=30` | GET | Last N days of data for chart + table |
| `/feedback` | POST | Saves user feedback from the form |
| `/health` | GET | Health check for Render |

---

## Troubleshooting

**API returns 404 on /today**
→ The compute script hasn't run yet. Trigger it manually from GitHub Actions.

**Frontend shows "Could not load live data"**
→ Your Render URL in `index.html` is wrong, or Render is spinning up (free tier sleeps after 15min). Wait 30s and refresh.

**Bhavcopy download fails in compute.py**
→ NSE sometimes changes the URL format. Check `nseindia.com/market-data/live-equity-market` for the current Bhavcopy link and update `BHAVCOPY_URL_TEMPLATE` in compute.py.

**Supabase RLS blocking inserts**
→ Make sure you're using the `service_role` key (not `anon`) in compute.py. For the frontend, the `anon` key is correct.
