# Lead Automation System - Complete Architecture & Technical Documentation

## 1. System Overview & Architecture

This project is an enterprise-grade, zero-cost automated lead-processing pipeline. It connects **Meta Lead Ads (Facebook/Instagram)** to **Airtable** for storage and **WhatsApp** for instant notification alerts to both the Business Owner and the incoming Prospect. It supports **Multi-Campaign Routing** across multiple Meta Lead Forms.

### System Architecture Flow

```mermaid
flowchart TD
    Meta[Meta Lead Ads Webhook] -->|HTTP POST /webhook| FastAPI[FastAPI Application main.py]
    FastAPI -->|Instant Ack 200 OK| Meta
    FastAPI -->|Enqueue Lead ID| DB[(Queue DB: Postgres / SQLite)]
    FastAPI -->|Put in Async Queue| Queue[asyncio.Queue]
    
    subgraph Async Processing Pipeline
        Queue --> Worker1[Worker 1]
        Queue --> Worker2[Worker 2]
        Queue --> WorkerN[Worker N]
        
        Worker1 --> MetaGraph[Meta Graph API v21.0]
        MetaGraph -->|Fetch Name, Phone, Form ID| Parser[Field Parser & Phone Standardizer]
        Parser --> CampResolver[Campaign Config Resolver campaigns.json]
        CampResolver --> Airtable[Airtable Base / Table Target]
        CampResolver --> WA_Owner[WhatsApp Alert -> Campaign Admin]
        CampResolver --> WA_Client[WhatsApp Welcome -> Client Prospect]
    end

    subgraph Dual WhatsApp Transport
        WA_Owner -->|Cloud API or Local QR| WAServer[Meta Cloud API / Baileys Engine]
        WA_Client -->|Cloud API or Local QR| WAServer
        WAServer -->|WhatsApp Message| WA_Net[WhatsApp Network]
    end
```

---

## 2. Component Breakdown & Core Files

| File Path | Role & Key Functionality |
| :--- | :--- |
| [`main.py`](file:///d:/Downloads/lead-automation/main.py) | **FastAPI Core Service**: Receives Meta webhooks, verifies SHA-256 signatures, manages startup sequence, launches Node.js subprocess if port 3000 is inactive, handles `/qr` proxying, `/health` checks, `/send-manual-lead`, and `API_SECRET_KEY` authentication. |
| [`db.py`](file:///d:/Downloads/lead-automation/db.py) | **Dual Database Manager**: Supports Supabase / Postgres via `DATABASE_URL` for persistent queues across redeployments, with seamless fallback to local SQLite `leads.db`. Handles thread-safe atomic inserts, `leadgen_id` deduplication, and crash recovery. |
| [`worker.py`](file:///d:/Downloads/lead-automation/worker.py) | **Background Queue Workers**: Runs parallel worker loops. Resolves campaign configuration by `form_id`, executes Meta Graph API fetch, Airtable insertion, owner alert, client welcome message, and admin failure alerts on max retries. |
| [`integrations/meta_api.py`](file:///d:/Downloads/lead-automation/integrations/meta_api.py) | **Meta Graph API Client**: Fetches lead details for a given `leadgen_id`. Parses complex field structures, configuration/BHK answers, and normalizes Indian phone numbers into clean `+91` format. |
| [`integrations/airtable_api.py`](file:///d:/Downloads/lead-automation/integrations/airtable_api.py) | **Airtable API Client**: Creates records in Airtable (`Client Name`, `Phone Number`, `Configuration`, `Remark`, `Campaign Name`). Supports dynamic campaign `base_id` and `table_name` targets with schema adaptation. |
| [`integrations/whatsapp_api.py`](file:///d:/Downloads/lead-automation/integrations/whatsapp_api.py) | **WhatsApp Integration Layer**: Dual transport layer. Uses Meta Official WhatsApp Cloud API if credentials exist, or falls back to local Baileys service. Supports custom campaign welcome text. |
| [`whatsapp_server.js`](file:///d:/Downloads/lead-automation/whatsapp_server.js) | **Baileys Node.js Service**: Maintains an active WhatsApp Web connection via `@whiskeysockets/baileys`. Exposes `/qr` HTML page for browser QR scanning, `/status`, and `/send-message`. |
| [`config.py`](file:///d:/Downloads/lead-automation/config.py) | **Configuration Manager & Campaign Resolver**: Reads `.env` settings and parses `campaigns.json` to resolve campaign-specific settings by `form_id`. |
| [`campaigns.json`](file:///d:/Downloads/lead-automation/campaigns.json) | **Multi-Campaign Config File**: Maps Meta Lead Form IDs (`form_id`) to campaign names, admin WhatsApp numbers, Airtable bases/tables, and custom welcome message templates. |
| [`add_lead.py`](file:///d:/Downloads/lead-automation/add_lead.py) | **CLI Manual Ingestion Tool**: Script to manually trigger lead processing either by Meta `LEAD_ID` or by explicit Name, Phone, BHK Config, and Campaign Name. |
| [`reprocess_past_leads.py`](file:///d:/Downloads/lead-automation/reprocess_past_leads.py) | **Batch Reprocessing Tool**: Iterates through past lead IDs stored in database, re-fetches details from Meta, updates Airtable, and dispatches WhatsApp messages. |

---

## 3. Multi-Campaign Setup (`campaigns.json`)

To run multiple campaigns with distinct admin alert numbers, Airtable tables, or custom client messages, add your form IDs to [`campaigns.json`](file:///d:/Downloads/lead-automation/campaigns.json):

```json
{
  "1044971085049692": {
    "campaign_name": "Silver 26 August - Goregaon East",
    "owner_whatsapp_number": "917738382905",
    "airtable_base_id": "appnn2bLWJJFH4ceD",
    "airtable_table_name": "tblginmsgXxiJ3K19",
    "client_welcome_message": "Hello {name}! 👋\n\nThank you for your interest in *Silver 26 August*. We have received your enquiry for a *{configuration} property at GOREGAON EAST near OBEROI MALL*.\n\nWould you like us to share the *official E-Brochure & Floor Plans*, or would you prefer to *schedule a Site Visit*?"
  },
  "9876543210987654": {
    "campaign_name": "Luxury Residency - Malad West",
    "owner_whatsapp_number": "919876543210",
    "airtable_base_id": "appnn2bLWJJFH4ceD",
    "airtable_table_name": "tblginmsgXxiJ3K19",
    "client_welcome_message": "Hello {name}! 👋\n\nThank you for reaching out regarding *Luxury Residency, Malad West*. We have noted your request for a *{configuration} apartment*.\n\nOur sales team will contact you shortly. Shall we send the brochure PDF on WhatsApp?"
  }
}
```

> [!NOTE]
> **Fallback Mechanism**: If a lead comes from an unmapped `form_id` or if `campaigns.json` is absent, the system automatically falls back to your global `.env` settings (`OWNER_WHATSAPP_NUMBER`, default Airtable base/table, standard templates).

---

## 4. Key Engineering Enhancements & Resilience Features

### A. Dual Database Queue (Supabase Postgres + SQLite Fallback)
- **Problem:** Ephemeral hosting filesystems (like Render free tier) reset local SQLite files on redeployment.
- **Solution:** Add `DATABASE_URL=postgresql://user:pass@ephemeral-db.supabase.co:5432/postgres` in `.env`. If present, [`db.py`](file:///d:/Downloads/lead-automation/db.py) uses Supabase Postgres for durable queue storage across deploys. If omitted, it seamlessly uses local SQLite `leads.db`.

### B. Dual WhatsApp Transport (Meta Official Cloud API + Local Baileys)
- **Problem:** Businesses may want to use official Meta WhatsApp Cloud API for client messaging while having a zero-cost local Baileys QR engine fallback.
- **Solution:** Set `WA_CLOUD_ACCESS_TOKEN` and `WA_CLOUD_PHONE_NUMBER_ID` in `.env`. [`send_whatsapp_template`](file:///d:/Downloads/lead-automation/integrations/whatsapp_api.py) will route through Meta's Official WhatsApp Cloud API. If omitted or if Cloud API fails, it automatically routes through the local Baileys QR server.

### C. Meta Graph API Error Fallback (Zero Lead Loss)
- **Solution:** If Meta Graph API returns an access token error or permission issue, [`worker.py`](file:///d:/Downloads/lead-automation/worker.py) creates a fallback record (`Lead <leadgen_id>`, `Meta Lead Form (API Error)`), guaranteeing **no lead is ever dropped or lost**.

### D. Indian Phone Number Format Standardization
- **Solution:** [`parse_lead_fields`](file:///d:/Downloads/lead-automation/integrations/meta_api.py#L77-L92) normalizes 10-digit, 11-digit (with 0), and 12-digit (with 91) phone numbers into clean `+91` format.

### E. Dynamic Airtable Schema Adaptation
- **Solution:** [`create_airtable_record`](file:///d:/Downloads/lead-automation/integrations/airtable_api.py#L50-L74) detects `422 UNKNOWN_FIELD_NAME`, strips missing optional columns via regex matching, and retries up to 4 times automatically.

### F. Failure Alerts & Security
- **Failure Alert:** If a lead fails processing after max retry attempts, an instant WhatsApp alert is dispatched to the admin number.
- **Endpoint Security:** `/send-manual-lead` supports an optional `API_SECRET_KEY` query parameter or `X-API-Key` HTTP header.

---

## 5. API Endpoints Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/` | `GET`, `HEAD` | Redirects to `/qr` status page. |
| `/qr` | `GET` | Renders live WhatsApp Web QR Login UI. Auto-refreshes every 5 seconds until scanned. |
| `/webhook` | `GET` | Meta Webhook Verification challenge handler. |
| `/webhook` | `POST` | Meta Lead Webhook Ingress. Validates SHA-256 HMAC signature, enqueues lead, returns `200 OK`. |
| `/health` | `GET`, `POST`, `HEAD` | Health check endpoint for uptime monitoring (e.g., UptimeRobot). |
| `/send-manual-lead` | `GET`, `POST` | Manually triggers lead creation and notifications. Accepts `api_key`, `form_id`, `name`, `phone`, `configuration`, `campaign`. |

---

## 6. Manual CLI Commands & Maintenance Utilities

### A. Process Lead by ID or Details (`add_lead.py`)

```bash
# Option 1: Ingest via Meta Lead ID
python add_lead.py 1044971085049692

# Option 2: Ingest via Name, Phone, BHK Config, Campaign
python add_lead.py "Ashish Shukla" "+919892749953" "2 BHK" "Silver 26 August"
```

### B. Reprocess All Past Leads (`reprocess_past_leads.py`)

```bash
python reprocess_past_leads.py
```

---

## 7. Configuration & Environment Variables (`.env`)

```ini
# --- Meta / Facebook Lead Ads Credentials ---
META_ACCESS_TOKEN=EAAdalBvu...
META_VERIFY_TOKEN=mysecretverifytoken123
META_APP_SECRET=2939d8232b1c6e6bb4e10e7f576bd88a
ALLOWED_FORM_ID=                        # Optional fallback form ID

# --- WhatsApp Transport Settings ---
OWNER_WHATSAPP_NUMBER=917738382905       # Default Admin WhatsApp alert number
ALERT_TEMPLATE_NAME=lead_alert
CLIENT_TEMPLATE_NAME=lead_welcome
TEMPLATE_LANGUAGE=en_US

# Meta Official WhatsApp Cloud API (Optional - Dual Transport)
WA_CLOUD_ACCESS_TOKEN=
WA_CLOUD_PHONE_NUMBER_ID=

# --- Airtable Integration ---
AIRTABLE_API_KEY=pateDYmhG...
AIRTABLE_BASE_ID=appnn2bLWJJFH4ceD
AIRTABLE_TABLE_NAME=tblginmsgXxiJ3K19   # Default Airtable Table Name

# --- Database (Supabase / Postgres Optional) ---
DATABASE_URL=                           # e.g. postgresql://postgres:pass@db.supabase.co:5432/postgres

# --- Security & Auth ---
API_SECRET_KEY=                         # Optional secret key to protect /send-manual-lead

# --- App behavior ---
WORKER_COUNT=5
PORT=8000
MAX_RETRIES=5
```

---

## 8. Cloud Deployment & 24/7 Availability (Render + UptimeRobot)

1. **GitHub Synchronization:** Code resides on `main` branch of `https://github.com/aryanotavakar07-jpg/automate.git`.
2. **Render Auto-Deploy:** Render builds and starts the application using Python + Node environment.
3. **UptimeRobot Keep-Alive (24/7 Awake):**
   - **Target URL:** `https://<your-render-app>.onrender.com/health`
   - **Monitoring Interval:** Every 5 minutes (keeps Render warm 24/7).


