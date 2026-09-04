# Lead Automation System - Complete Setup & Maintenance Guide

## 1. System Overview
This project is an automated lead-processing backend built with Python (FastAPI) and Node.js (Baileys WhatsApp QR engine).

### Workflow Flowchart
1. **Meta Lead Ads Webhook** → Receives instant HTTP POST at `/webhook`.
2. **SQLite Queue (`leads.db`)** → Enqueues lead ID instantly and responds to Meta with `200 OK`.
3. **Background Queue Workers (`worker.py`)** → Pick up lead ID in parallel (5 concurrent workers).
4. **Meta Graph API** → Fetches lead details (name, phone, BHK configuration, campaign name).
5. **Airtable API (`integrations/airtable_api.py`)** → Creates/updates lead record in Airtable table (`tblginmsgXxiJ3K19`).
6. **WhatsApp QR Engine (`whatsapp_server.js`)** → Sends WhatsApp alert to Business Owner and Welcome message to Client.

---

## 2. Key Code Enhancements & Fixes Implemented

### A. Meta API Error Fallback (`worker.py`)
- **Problem:** If Meta Graph API returned permission error (`pages_manage_ads` missing) or network error, the worker previously crashed and retried until failure, losing the lead.
- **Fix:** If Meta API fails to return full lead details, `worker.py` creates a fallback payload:
  - Client Name: `Lead <leadgen_id>`
  - Campaign Name: `Meta Lead Form (API Error)`
  - Remark / Notes: `Meta API error for Lead ID <leadgen_id>`
  - **Result:** **No lead is ever lost or dropped**, even if Meta API has token/permission issues.

### B. Phone Number Parsing (`integrations/meta_api.py`)
- **Fix:** Added normalization for all Indian phone number variations:
  - 10 digits (`9892749953` → `+919892749953`)
  - 11 digits starting with zero (`09892749953` → `+919892749953`)
  - 12 digits starting with `91` (`919892749953` → `+919892749953`)
  - International formats starting with `+`

### C. Non-Blocking WhatsApp Timeout (`integrations/whatsapp_api.py`)
- **Fix:** Set a **5.0 second strict timeout** on WhatsApp calls. If WhatsApp is unlinked or QR code is waiting to be scanned, the call logs a warning and skips gracefully without hanging HTTP endpoints or blocking Airtable record creation.

### D. Duplicate Process Protection & Webhook Safety (`main.py`)
- **Fix:** On startup, `main.py` checks if port 3000 is already active before attempting to launch `node whatsapp_server.js`.
- **Fix:** Wrapped `/webhook` endpoint in top-level `try...except` so any unexpected payload structure always returns `{"status": "ok"}` to Meta, preventing Meta from disabling the webhook subscription.

---

## 3. Deployment & Cloud Setup (Render + UptimeRobot)

- **GitHub Repository:** `https://github.com/aryanotavakar07-jpg/automate.git`
- **Branch:** `main`
- **Render Auto-Deploy:** Render builds and deploys automatically on every `git push origin main`.
- **Uptime Keeping (24/7 Awake):** Render free tier sleeps after 15 minutes of inactivity. To prevent cold-start webhook timeouts from Meta:
  - **UptimeRobot Monitor URL:** `https://<your-render-url>.onrender.com/health`
  - **Interval:** Every 5 minutes (keeps Render warm 24/7).

---

## 4. Manual Lead Processing Commands

If a lead ever needs to be added or reprocessed manually:

### Option A: Via Terminal (Script)
```bash
# Add lead by Name & Phone
python add_lead.py "Client Name" "+919892749953" "2 BHK" "Silver 26 August"

# Add lead by Meta Lead ID
python add_lead.py 1044971085049692
```

### Option B: Via HTTP Endpoint
```http
GET https://<your-render-url>.onrender.com/send-manual-lead?name=Ashish&phone=%2B919892749953&configuration=2_bhk&campaign=Silver%2026%20August&force=true
```

---

## 5. Environment Variables (`.env`) Reference
```ini
META_ACCESS_TOKEN=EAAdalBvu...
META_VERIFY_TOKEN=mysecretverifytoken123
META_APP_SECRET=2939d8232b1c6e6bb4e10e7f576bd88a

OWNER_WHATSAPP_NUMBER=917738382905
ALERT_TEMPLATE_NAME=lead_alert
CLIENT_TEMPLATE_NAME=lead_welcome
TEMPLATE_LANGUAGE=en_US

AIRTABLE_API_KEY=pateDYmhG...
AIRTABLE_BASE_ID=appnn2bLWJJFH4ceD
AIRTABLE_TABLE_NAME=tblginmsgXxiJ3K19

WORKER_COUNT=5
MAX_RETRIES=5
```
