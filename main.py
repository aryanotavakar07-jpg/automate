import asyncio
import hmac
import hashlib
import logging
import subprocess

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
import httpx
import uvicorn

import db
from config import settings
from worker import worker_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("main")

app = FastAPI(title="Meta Lead Ads -> WhatsApp + Airtable Automation")
lead_queue: asyncio.Queue = asyncio.Queue()


@app.on_event("startup")
async def startup_event():
    db.init_db()

    # Check if local Node WhatsApp QR Server (Baileys) is already running on port 3000
    wa_running = False
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            resp = await client.get("http://localhost:3000/status")
            if resp.status_code == 200:
                wa_running = True
                logger.info("Local Node WhatsApp QR Server is already active on port 3000")
    except Exception:
        pass

    if not wa_running:
        try:
            subprocess.Popen(["node", "whatsapp_server.js"])
            logger.info("Started Node WhatsApp QR Server subprocess (Baileys Engine)")
        except Exception as err:
            logger.warning(f"Local whatsapp_server.js not launched: {err}")

    # Recover anything that didn't finish before a restart/crash
    for leadgen_id in db.get_unfinished_leads(settings.MAX_RETRIES):
        await lead_queue.put(leadgen_id)
        logger.info(f"Requeued unfinished lead {leadgen_id} from a previous run")

    # Start N workers so leads are handled in parallel, not one at a time
    for i in range(settings.WORKER_COUNT):
        asyncio.create_task(worker_loop(lead_queue, i))
    logger.info(f"Started {settings.WORKER_COUNT} workers")


@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    """Live dashboard landing page."""
    return RedirectResponse(url="/qr")


@app.get("/qr")
async def qr_page():
    """Exposes the WhatsApp QR code login webpage on your live server URL."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get("http://localhost:3000/qr")
            return Response(content=resp.text, media_type="text/html")
        except Exception as e:
            return Response(
                content=f"<h2 style='font-family:sans-serif;text-align:center;margin-top:20%;'>WhatsApp QR Service initializing... ({e})</h2><script>setTimeout(() => location.reload(), 3000);</script>",
                media_type="text/html",
            )


@app.get("/webhook")
async def verify_webhook(request: Request):
    """Meta calls this once, when you first set up the webhook in your app dashboard,
    to confirm you control this server."""
    params = request.query_params
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == settings.META_VERIFY_TOKEN
    ):
        return Response(content=params.get("hub.challenge"), media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


def verify_signature(body: bytes, signature_header: str) -> bool:
    """Confirms the webhook payload really came from Meta and wasn't spoofed."""
    if not settings.META_APP_SECRET or not signature_header:
        logger.warning("META_APP_SECRET not set - skipping signature check (not recommended)")
        return True
    expected = "sha256=" + hmac.new(
        settings.META_APP_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


@app.post("/webhook")
async def receive_webhook(request: Request):
    """This fires every time someone submits a lead form. It must respond fast,
    so it just queues the lead ID and returns immediately - the actual work
    (WhatsApp messages, Airtable) happens in the background workers."""
    try:
        body = await request.body()
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not verify_signature(body, signature):
            raise HTTPException(status_code=403, detail="Invalid signature")

        payload = await request.json()
        logger.info(f"Webhook payload received: {payload}")
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                leadgen_id = value.get("leadgen_id")
                form_id = value.get("form_id")

                if settings.ALLOWED_FORM_ID and form_id:
                    if str(form_id).strip() != str(settings.ALLOWED_FORM_ID).strip():
                        logger.info(f"Skipping lead {leadgen_id}: form_id {form_id} != ALLOWED_FORM_ID {settings.ALLOWED_FORM_ID}")
                        continue

                if leadgen_id:
                    is_new = db.enqueue_lead(str(leadgen_id))
                    if is_new:
                        await lead_queue.put(str(leadgen_id))
                        logger.info(f"Queued new lead {leadgen_id}")
                    else:
                        logger.info(f"Duplicate webhook for lead {leadgen_id} ignored")

        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as err:
        logger.error(f"Error handling webhook payload: {err}", exc_info=True)
        return {"status": "ok", "error": str(err)}


from integrations.airtable_api import create_airtable_record, lead_already_stored
from integrations.whatsapp_api import send_whatsapp_template

@app.api_route("/health", methods=["GET", "HEAD", "POST"])
async def health():
    """Useful for uptime monitors (e.g. UptimeRobot) to confirm the server is alive."""
    return {"status": "healthy"}


@app.api_route("/send-manual-lead", methods=["GET", "POST"])
async def send_manual_lead(name: str = "Valued Lead", phone: str = "", configuration: str = "N/A", campaign: str = "Lead Form", force: bool = False):
    """Allows manual lead processing (Airtable + Owner WhatsApp Alert + Client WhatsApp Welcome) with dedup protection."""
    # Dedup check
    if phone and not force:
        if await lead_already_stored(phone):
            logger.info(f"Manual lead {phone} already processed/stored in Airtable. Skipping duplicate message.")
            return {"status": "skipped", "message": f"Lead for {phone} is already in Airtable. Message skipped to prevent duplicates."}

    # 1. Airtable
    await create_airtable_record({
        "Client Name": str(name),
        "Phone Number": str(phone),
        "Configuration": str(configuration),
        "Remark": "",
        "Campaign Name": str(campaign),
    })

    owner_status = "skipped"
    client_status = "skipped"

    # 2. Owner Alert
    if settings.OWNER_WHATSAPP_NUMBER:
        try:
            answers_text = f"which_configuration_are_you_looking_for?: {configuration}"
            await send_whatsapp_template(
                to_number=settings.OWNER_WHATSAPP_NUMBER,
                template_name=settings.ALERT_TEMPLATE_NAME,
                body_params=[campaign, name, phone or "Not provided", answers_text],
            )
            owner_status = "sent"
        except Exception as e:
            owner_status = f"error: {e}"

    # 3. Client Welcome Message
    if phone:
        try:
            await send_whatsapp_template(
                to_number=phone,
                template_name=settings.CLIENT_TEMPLATE_NAME,
                body_params=[name, campaign, configuration],
            )
            client_status = "sent"
        except Exception as e:
            client_status = f"error: {e}"

    return {
        "status": "success",
        "client_name": name,
        "phone": phone,
        "owner_whatsapp_alert": owner_status,
        "client_whatsapp_message": client_status
    }



if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
