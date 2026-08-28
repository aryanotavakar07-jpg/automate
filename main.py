import asyncio
import hmac
import hashlib
import logging

from fastapi import FastAPI, Request, Response, HTTPException
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

    # Recover anything that didn't finish before a restart/crash
    for leadgen_id in db.get_unfinished_leads(settings.MAX_RETRIES):
        await lead_queue.put(leadgen_id)
        logger.info(f"Requeued unfinished lead {leadgen_id} from a previous run")

    # Start N workers so leads are handled in parallel, not one at a time
    for i in range(settings.WORKER_COUNT):
        asyncio.create_task(worker_loop(lead_queue, i))
    logger.info(f"Started {settings.WORKER_COUNT} workers")


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
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            leadgen_id = value.get("leadgen_id")
            if leadgen_id:
                is_new = db.enqueue_lead(leadgen_id)
                if is_new:
                    await lead_queue.put(leadgen_id)
                    logger.info(f"Queued new lead {leadgen_id}")
                else:
                    logger.info(f"Duplicate webhook for lead {leadgen_id} ignored")

    return {"status": "ok"}


@app.get("/health")
async def health():
    """Useful for uptime monitors (e.g. UptimeRobot) to confirm the server is alive."""
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
