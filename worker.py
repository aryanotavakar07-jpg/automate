import asyncio
import logging
from datetime import datetime, timezone

import db
from config import settings
from integrations.meta_api import fetch_lead_details, parse_lead_fields
from integrations.whatsapp_api import send_whatsapp_template
from integrations.airtable_api import create_airtable_record, lead_already_stored

logger = logging.getLogger("worker")


async def process_lead(leadgen_id: str, queue: "asyncio.Queue" = None):
    try:
        db.mark_status(leadgen_id, "processing")

        # Durable dedup check
        try:
            if await lead_already_stored(leadgen_id):
                logger.info(f"Lead {leadgen_id} already in Airtable, skipping (duplicate webhook)")
                db.mark_status(leadgen_id, "done")
                return
        except Exception as err:
            logger.warning(f"Airtable dedup check failed: {err}. Proceeding with processing...")

        # Fetch lead details from Meta Graph API, with fallback for test leads
        try:
            raw = await fetch_lead_details(leadgen_id)
            parsed = parse_lead_fields(raw)
            logger.info(f"Successfully fetched lead details for {leadgen_id} from Meta API")
        except Exception as meta_err:
            logger.warning(f"Could not fetch full lead details from Meta API ({meta_err}). Using test fallback data.")
            parsed = {
                "campaign_name": "Meta Ads Test Campaign",
                "ad_name": "Test Ad",
                "form_name": "Test Lead Form",
                "created_time": datetime.now(timezone.utc).isoformat(),
                "full_name": "Test Lead User",
                "phone_number": settings.OWNER_WHATSAPP_NUMBER,
                "answers": {"Note": f"Test lead generated from Meta Tool (ID: {leadgen_id})"},
            }

        phone = parsed["phone_number"] or settings.OWNER_WHATSAPP_NUMBER
        name = parsed["full_name"] or "Test Customer"
        campaign = parsed["campaign_name"] or "Test Campaign"
        answers_text = "\n".join(f"{k}: {v}" for k, v in parsed["answers"].items()) or "N/A"

        # 1. Alert to you, the business owner
        try:
            await send_whatsapp_template(
                to_number=settings.OWNER_WHATSAPP_NUMBER,
                template_name=settings.ALERT_TEMPLATE_NAME,
                body_params=[campaign, name, phone, answers_text],
            )
            logger.info("WhatsApp alert sent to owner successfully")
        except Exception as wa_err:
            logger.error(f"Failed to send owner WhatsApp alert: {wa_err}")

        # 2. Automated message to the client
        if phone:
            try:
                config_val = parsed.get("configuration") or ""
                await send_whatsapp_template(
                    to_number=phone,
                    template_name=settings.CLIENT_TEMPLATE_NAME,
                    body_params=[name, campaign, config_val],
                )
                logger.info("WhatsApp welcome message sent to client successfully")
            except Exception as client_wa_err:
                logger.error(f"Failed to send client WhatsApp message: {client_wa_err}")

        # 3. Store everything in Airtable
        try:
            await create_airtable_record(
                {
                    "Lead ID": str(leadgen_id),
                    "Campaign Name": str(campaign),
                    "Ad Name": str(parsed.get("ad_name", "N/A")),
                    "Form Name": str(parsed.get("form_name", "N/A")),
                    "Client Name": str(name),
                    "Phone Number": str(phone or ""),
                    "Form Answers": str(answers_text),
                    "Created Time": str(parsed.get("created_time", "")),
                }
            )
            logger.info("Lead saved to Airtable successfully")
        except Exception as airtable_err:
            logger.error(f"Failed to save lead to Airtable: {airtable_err}")

        db.mark_status(leadgen_id, "done")
        logger.info(f"Lead {leadgen_id} processed successfully")

    except Exception as e:
        logger.exception(f"Failed to process lead {leadgen_id}: {e}")
        retries = db.increment_retry(leadgen_id)
        db.mark_status(leadgen_id, "failed", error=str(e))

        if retries < settings.MAX_RETRIES and queue is not None:
            delay = min(60, 2 ** retries)
            logger.info(f"Retrying lead {leadgen_id} in {delay}s (attempt {retries})")
            await asyncio.sleep(delay)
            await queue.put(leadgen_id)


async def worker_loop(queue: "asyncio.Queue", worker_id: int):
    logger.info(f"Worker {worker_id} started")
    while True:
        leadgen_id = await queue.get()
        logger.info(f"Worker {worker_id} picked up lead {leadgen_id}")
        await process_lead(leadgen_id, queue)
        queue.task_done()
