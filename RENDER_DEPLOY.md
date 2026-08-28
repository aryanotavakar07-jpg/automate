# Deploying on Render (Free Tier)

Render is much simpler than a raw VM — it gives you free HTTPS automatically, no
domain or reverse-proxy setup needed. Two things to know going in:

- **Sleep on inactivity**: the free plan spins your service down after ~15 minutes
  of no traffic, and takes ~30-50 seconds to wake up on the next request. Meta
  retries failed webhook deliveries automatically, so leads aren't lost — but an
  alert could arrive a bit late if things were quiet. Step 6 below shows a free
  way to minimize this.
- **Ephemeral disk**: local files (like the SQLite log) don't survive a restart on
  the free plan. The code has already been adjusted so the important thing —
  never double-messaging the same lead — is checked against Airtable itself
  instead of the local file, so this is safe even with disk resets.

## Steps

1. **Push the code to a GitHub repo** (Render deploys from Git):
   ```bash
   cd lead-automation
   git init
   git add .
   git commit -m "Initial commit"
   # create a repo on github.com, then:
   git remote add origin https://github.com/yourusername/lead-automation.git
   git push -u origin main
   ```
   Make sure `.env` is in a `.gitignore` — never commit real secrets. Create one:
   ```bash
   echo ".env" > .gitignore
   echo "leads.db" >> .gitignore
   echo "venv/" >> .gitignore
   ```

2. **Create a new Web Service on Render**:
   - Go to render.com → New → Web Service
   - Connect your GitHub repo
   - Environment: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python main.py`
   - Instance Type: **Free**

3. **Add your environment variables**: In the service's "Environment" tab, add
   every variable from `.env.example` with your real values (`META_ACCESS_TOKEN`,
   `WHATSAPP_PHONE_NUMBER_ID`, `AIRTABLE_API_KEY`, etc.). Don't set `PORT` —
   Render sets that automatically and the app already reads it.

4. **Deploy**. Render builds and gives you a live URL like
   `https://lead-automation-xxxx.onrender.com` — with HTTPS already handled.

5. **Register the webhook in Meta**: App Dashboard → Webhooks → Add Callback URL:
   `https://lead-automation-xxxx.onrender.com/webhook`
   Verify token = whatever you set as `META_VERIFY_TOKEN`. Subscribe to the
   `leadgen` field under Page Webhooks.

6. **(Recommended) Keep it warm with a free uptime monitor**: sign up at
   uptimerobot.com (free) and add a monitor pinging
   `https://lead-automation-xxxx.onrender.com/health` every 5-10 minutes. This
   keeps the service from fully spinning down during business hours, so your
   WhatsApp alerts stay near-instant. It won't guarantee zero cold starts (Render
   may still cycle the instance periodically), but it significantly reduces them.

7. **Test it**: use Meta's test-lead tool (Ads Manager → your form → "..." →
   Test Form) with your own number, and confirm you get the WhatsApp alert, the
   client-side welcome message, and a new Airtable row.

## If reliability becomes important

Since missed/delayed leads can mean lost business, Render's paid Starter plan
($7/month) removes the sleep behavior entirely — worth it once this is actually
running your lead flow day to day. You can switch instance type later without
re-doing any of the setup above.
