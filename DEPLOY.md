# 🚀 Deployment Guide — Irish Visa Tracker Starter

Complete step-by-step instructions to go from zero to a live public URL.
Total time: 20–30 minutes.
Total cost: ₹0.

---

## What you need before starting

- A computer with a browser (nothing to install)
- An email address (used to create accounts)
- The starter ZIP file extracted on your desktop

You do NOT need: any programming knowledge, a credit card, or any paid services.

---

## Overview — 3 stages

```
Stage 1: Supabase    (10 min)  — create the database
Stage 2: GitHub      (5 min)   — host the code
Stage 3: Streamlit   (5 min)   — deploy the app
```

---

## STAGE 1 — Supabase (Database)

Supabase is a free PostgreSQL database. It stores community submissions and email alert registrations.

### Step 1.1 — Create account

1. Open **supabase.com** in your browser
2. Click **Start your project** (top right)
3. Click **Sign up with GitHub** — this is the easiest option
   - If you don't have a GitHub account yet, click **Sign up** on GitHub first, it's free
   - After GitHub login, Supabase will redirect you back automatically
4. You are now in the Supabase dashboard

### Step 1.2 — Create a new project

1. Click **New project** (green button)
2. Fill in the form:
   - **Name:** `irish-visa-tracker` (or any name you like)
   - **Database Password:** click **Generate a password** — copy this somewhere safe (you won't need it often but don't lose it)
   - **Region:** `Southeast Asia (Singapore)` — closest to India, fastest for your users
   - **Plan:** Free (already selected)
3. Click **Create new project**
4. Wait 1–2 minutes while Supabase sets up your project. You will see a progress bar.

### Step 1.3 — Run the schema

This creates the two database tables the app needs: `community` and `alerts`.

1. In the left sidebar, click **SQL Editor** (looks like `</>`)
2. Click **New query** (top left of the editor)
3. Open the file `schema.sql` from your extracted ZIP on your computer
4. Select all the text in that file (Ctrl+A / Cmd+A) and copy it
5. Paste it into the Supabase SQL editor
6. Click the **Run** button (green, bottom right) or press **Ctrl+Enter**
7. You should see: `Success. No rows returned`
8. To confirm tables were created: click **Table Editor** in the left sidebar
   - You should see `community` and `alerts` listed

### Step 1.4 — Get your API keys

Supabase is updating how API keys work in 2026. You may see either the old or new key format — both work. Here is how to find them:

1. In the left sidebar, click **Settings** (gear icon, bottom of sidebar)
2. Click **API Keys** (under Configuration)
3. You will see either:
   - **New format (preferred):** Click **API Keys** tab → Copy the **Publishable key** (use this as `anon_key`) and **Secret key** (use this as `service_key`)
   - **Legacy format:** Click **Legacy API Keys** tab → Copy **anon** key and **service_role** key

4. Also copy your **Project URL** — it looks like:
   `https://abcdefghijkl.supabase.co`
   Find it at Settings → API → Project URL

5. Write down or save these three values:
   ```
   Project URL:  https://xxxxxxxxxxxx.supabase.co
   Anon key:     eyJhbGc... (long string) OR sb_publishable_...
   Service key:  eyJhbGc... (long string) OR sb_secret_...
   ```

**Stage 1 complete.** The database is ready.

---

## STAGE 2 — GitHub (Code Repository)

GitHub stores your code and automatically triggers a redeploy every time you change a file.

### Step 2.1 — Create account (skip if you already have one)

1. Open **github.com**
2. Click **Sign up**
3. Enter email, password, username
4. Verify your email address
5. Choose the **Free** plan

### Step 2.2 — Create a new repository

1. Click the **+** icon (top right) → **New repository**
2. Fill in:
   - **Repository name:** `irish-visa-tracker`
   - **Description:** `Free Irish visa application tracker`
   - **Visibility:** ✅ **Public** (required for free Streamlit hosting)
   - Leave everything else as default
3. Click **Create repository**

### Step 2.3 — Upload your files

You will upload files directly in the browser — no Git commands needed.

1. You should now see your empty repository page
2. Click **uploading an existing file** (link in the middle of the page)
   - If you don't see this link, click **Add file** → **Upload files**
3. Open your extracted ZIP folder on your computer
4. Drag ALL of these files and folders into the GitHub upload box:
   ```
   app.py
   database.py
   requirements.txt
   schema.sql
   README.md
   .gitignore
   .streamlit/          ← drag the whole folder
   ```
   
   **Important:** Upload the `.streamlit` folder. It contains `config.toml` and `secrets.toml.template`. The `.gitignore` file ensures your real `secrets.toml` (with passwords) is never uploaded.

5. Scroll down to **Commit changes**
   - Leave the commit message as is, or type: `Initial deployment`
   - Click **Commit changes**

6. Your repository now looks like this:
   ```
   irish-visa-tracker/
   ├── app.py
   ├── database.py
   ├── requirements.txt
   ├── schema.sql
   ├── README.md
   ├── .gitignore
   └── .streamlit/
       ├── config.toml
       └── secrets.toml.template
   ```

### Step 2.4 — Update your personal details in app.py

Before deploying, update three lines in `app.py` with your own links:

1. In your GitHub repository, click `app.py`
2. Click the **pencil icon** (Edit this file) — top right of the file view
3. Find these lines near the top (around line 25–30):

   ```python
   KOFI_URL  = "https://ko-fi.com/yourname"
   UPI_ID    = "yourname@upi"
   WISE_AFF  = "https://wise.com/invite/u/yourref"
   NIYO_AFF  = "https://goniyo.com/yourref"
   INSURE_AFF = "https://www.policybazaar.com/?ref=visa"
   ```

4. Replace each value:
   - `KOFI_URL`: Create a free account at **ko-fi.com** → your page URL
   - `UPI_ID`: Your UPI ID (e.g. `yourname@okicici`)
   - `WISE_AFF`: Sign up at **wise.com/partners** for affiliate link (or leave as is for now)
   - `NIYO_AFF`: Sign up at **goniyo.com** affiliate program (or leave as is for now)

5. Scroll down → Click **Commit changes** → **Commit changes**

**Stage 2 complete.** Your code is on GitHub.

---

## STAGE 3 — Streamlit Cloud (App Hosting)

Streamlit Cloud reads your code from GitHub and hosts it as a public web app.

### Step 3.1 — Create account

1. Open **share.streamlit.io**
2. Click **Continue with GitHub**
3. Authorize Streamlit to access your GitHub repositories
4. Fill in your name and email if asked
5. Click **I accept**

### Step 3.2 — Deploy the app

1. You are now in your Streamlit workspace
2. Click **Create app** (top right, blue button)
3. Choose **Deploy from an existing repo**
4. Fill in the form:
   - **Repository:** Select `your-github-username/irish-visa-tracker`
     (if it doesn't appear in the dropdown, type it manually)
   - **Branch:** `main`
   - **Main file path:** `app.py`
   - **App URL:** Choose something memorable, e.g. `irish-visa-tracker`
     → This makes your URL: `irish-visa-tracker.streamlit.app`
5. Click **Advanced settings** (important — don't skip this)

### Step 3.3 — Add your secrets (critical step)

When deploying your app, you can access Advanced settings to set your secrets.

In the **Advanced settings** dialog:

1. Click the **Secrets** tab
2. Paste the following, replacing the placeholder values with your real Supabase credentials from Stage 1:

   ```toml
   [supabase]
   url         = "https://YOUR-PROJECT-ID.supabase.co"
   anon_key    = "YOUR-ANON-KEY-HERE"
   service_key = "YOUR-SERVICE-KEY-HERE"
   ```

   Example with real values (yours will be different):
   ```toml
   [supabase]
   url         = "https://abcdefghijkl.supabase.co"
   anon_key    = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
   service_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
   ```

3. Click **Save**

### Step 3.4 — Deploy

1. Click **Deploy** (blue button)
2. You will see a log window showing the app being built:
   - Installing Python packages from `requirements.txt`
   - Starting the app
   - This takes 2–4 minutes the first time
3. When complete, your app opens automatically in the browser

Your app now has a unique URL that you can share with others.

Your live URL: `https://irish-visa-tracker.streamlit.app`
(or whatever subdomain you chose)

---

## Verify everything is working

Open your app URL and do these checks:

**Check 1 — ODS data loads**
- You should see "New Delhi X,XXX decisions" in the header
- If you see 0 or an error, click the Refresh button

**Check 2 — IRL search works**
- Enter `81818952` in the IRL field → Click Check Status
- Should show: `✅ Approved — IRL 81818952 · Source: New Delhi ODS`

**Check 3 — Community tab**
- Click Community tab
- Should show the submission form
- Try submitting a test entry with dummy dates

**Check 4 — Supabase connection**
- After submitting a test entry, go to your Supabase dashboard
- Click Table Editor → community
- You should see your test row

If Check 4 shows nothing, the secrets are not connected correctly. Go to Step 3.3 and re-paste your credentials.

---

## Updating the app after launch

Every time you change a file in GitHub, Streamlit automatically redeploys within seconds.

To edit a file:
1. Go to your GitHub repository
2. Click the file you want to edit (e.g. `app.py`)
3. Click the pencil icon (Edit)
4. Make your changes
5. Click **Commit changes**
6. Your live app updates within 30 seconds

To update secrets:
1. Go to **share.streamlit.io**
2. Find your app → click **⋮** (three dots) → **Settings**
3. Click **Secrets** → edit → **Save**
4. App restarts automatically

---

## If the Supabase database pauses

Free Supabase projects pause after 7 days of inactivity. If your app suddenly can't connect to the database:

1. Go to **supabase.com** → your project
2. You will see a banner: "Your project is paused"
3. Click **Restore project**
4. Wait 1–2 minutes
5. App reconnects automatically

This only happens if nobody visits the app for 7 days. Once you share the URL publicly, it will essentially never pause.

---

## Setting up Ko-fi (5 minutes)

1. Go to **ko-fi.com** → **Sign up**
2. Create your page:
   - Display name: `Irish Visa Tracker`
   - Bio: `Free tool to track Irish visa decisions. Community-powered.`
3. Your URL: `ko-fi.com/yourchosename`
4. Update `KOFI_URL` in `app.py` with this URL (edit via GitHub as shown above)

---

## Setting up UPI

Your UPI ID is the same as what you use for regular UPI payments (e.g. `yourname@okicici`). Just update the `UPI_ID` line in `app.py`. Users will see this ID and can manually enter it in any UPI app to send a payment. You don't need to do anything else.

---

## Sharing with the community

Once live, share in these places:

**Reddit:**
- r/IrishVisa
- r/india (tag: student visa)
- r/studyabroad

**Facebook groups:**
- Search "Ireland Student Visa India" — several active groups with 5,000–20,000 members

**WhatsApp:**
- Your college batch groups
- Any Ireland-bound student communities you're part of

**Template message:**
```
Found this free tool that tracks Irish visa decisions live from the embassy:
[your URL]

Enter your IRL number to check your status, see how your wait compares
to others, and get email alerts when your decision comes.
No ads, no payment required.
```

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| App shows 0 decisions | Embassy website unreachable | Click Refresh; check ireland.ie is accessible |
| Community submission not saving | Supabase secrets wrong | Re-paste secrets in Streamlit settings |
| App shows old data | Cache not expired | Click Refresh button in app |
| App fails to start | Package install error | Check Streamlit logs (click View logs on app page) |
| Supabase "connection refused" | Project paused | Restore project at supabase.com |
| Can't find secrets in Supabase | Key format changed | Use Settings → API Keys → copy publishable + secret keys |
