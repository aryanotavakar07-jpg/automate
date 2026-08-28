# Meta Lead Ads → WhatsApp + Airtable Automation

A self-hosted, always-on Python service that:
1. Receives an instant webhook the moment someone submits your Meta lead form
2. Fetches the full lead (campaign name, name, phone, every question/answer)
3. Sends you a WhatsApp alert
4. Sends the client an automated WhatsApp welcome message
5. Stores everything in Airtable

Leads are processed through an internal queue with multiple parallel workers, so
several leads arriving at once are all handled concurrently, not one-by-one. A local
SQLite file tracks status so nothing is lost if the server restarts.

---

## 1. Prerequisites to gather first

You need these five things before the code will work:

| What | Where to get it |
|---|---|
| Meta App + Graph API access token | developers.facebook.com → create an app → add "Facebook Login for Business" + "WhatsApp" products |
| `META_APP_SECRET` | Your Meta App's dashboard → Settings → Basic |
| WhatsApp Phone Number ID | Meta App dashboard → WhatsApp → API Setup |
| Airtable Personal Access Token + Base ID | airtable.com/create/tokens, and your base's URL contains the Base ID (starts with `app...`) |
| A domain or subdomain pointing at your server | Needed because Meta requires webhook URLs to be HTTPS |

### WhatsApp templates
Business-initiated messages require pre-approved templates. In Meta's WhatsApp Manager,
create two templates with the exact variable structure this code expects:

**`lead_alert`** (sent to you):
```
New lead from {{1}}!
Name: {{2}}
Phone: {{3}}
Answers: {{4}}
```

**`lead_welcome`** (sent to the client):
```
Hi {{1}}, thanks for your interest in {{2}}! We'll be in touch shortly.
```
Submit both for approval (usually approved within minutes to a few hours).

### Airtable base
Create a base with a table (default name `Leads`) with these columns:
`Lead ID`, `Campaign Name`, `Ad Name`, `Form Name`, `Client Name`, `Phone Number`,
`Form Answers`, `Created Time` — all as "Single line text" or "Long text".

---

## 2. Local setup

```bash
cd lead-automation
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# now edit .env with your real values
python main.py
```

The server starts on port 8000. `/webhook` is what Meta will call, `/health` is for
uptime monitoring.

---

## 3. Deploying for free, 24/7: Oracle Cloud "Always Free" tier

Render/Railway free tiers sleep after inactivity, which breaks instant webhook
responses. Oracle Cloud's Always Free tier gives you a real small VM that runs
forever at no cost — this is the most reliable free option for this use case.

1. **Create an account** at oracle.com/cloud/free and create a free "Ampere A1" or
   "VM.Standard.E2.1.Micro" compute instance (Ubuntu 22.04 image).
2. **Open the firewall** for ports 80 and 443 in the instance's Security List/Network
   Security Group (Networking → Virtual Cloud Networks → your VCN → Security Lists).
3. **SSH into the instance** and install dependencies:
   ```bash
   sudo apt update && sudo apt install -y python3-pip python3-venv git caddy
   ```
   (Caddy gives you automatic free HTTPS certificates — required since Meta only
   accepts HTTPS webhook URLs.)
4. **Upload your code** (e.g. via `scp` or `git clone` if you push it to a repo):
   ```bash
   scp -r lead-automation ubuntu@YOUR_SERVER_IP:~/
   ```
5. **Set up the Python environment** on the server:
   ```bash
   cd lead-automation
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env && nano .env   # fill in real values
   ```
6. **Point Caddy at your domain** — edit `/etc/caddy/Caddyfile`:
   ```
   yourdomain.com {
       reverse_proxy localhost:8000
   }
   ```
   Then `sudo systemctl restart caddy`. Caddy automatically gets you a free HTTPS
   certificate.
7. **Run the app as a persistent service** so it survives reboots. Create
   `/etc/systemd/system/leadbot.service`:
   ```ini
   [Unit]
   Description=Lead Automation Service
   After=network.target

   [Service]
   User=ubuntu
   WorkingDirectory=/home/ubuntu/lead-automation
   ExecStart=/home/ubuntu/lead-automation/venv/bin/python main.py
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```
   Then:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable leadbot
   sudo systemctl start leadbot
   ```
8. **Register the webhook** in your Meta App dashboard → Webhooks → Add Callback URL:
   `https://yourdomain.com/webhook`, verify token = whatever you set as
   `META_VERIFY_TOKEN`. Subscribe to the `leadgen` field under Page Webhooks.
9. **(Optional) Free uptime monitor**: add `https://yourdomain.com/health` to
   uptimerobot.com (free) so you get an alert if the service ever goes down.

---

## 4. Testing

Use Meta's built-in test lead tool (Ads Manager → your form → "..." → Test Form) to
submit a fake lead and confirm:
- You get a WhatsApp alert
- The fake number gets a welcome message (use your own number as the test to check)
- A new row appears in Airtable

Check logs anytime with:
```bash
sudo journalctl -u leadbot -f
```

## 5. Notes on scaling and limits

- `WORKER_COUNT` in `.env` controls how many leads are processed simultaneously —
  raise it if you expect bursts of leads.
- WhatsApp Cloud API has messaging rate limits based on your number's tier (starts
  around 250 unique conversations/day, and increases automatically with good
  engagement/quality ratings).
- The Oracle free VM is small (1 OCPU, 1GB RAM on the Micro shape) — plenty for this
  workload, but not for much beyond it.
