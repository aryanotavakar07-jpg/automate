import asyncio
import logging

import db
from config import settings
from integrations.meta_api import fetch_lead_details, parse_lead_fields
from integrations.whatsapp_api import send_whatsapp_template
from integrations.airtable_api import create_airtable_record, lead_already_stored

logger = logging.getLogger("worker")


async def process_lead(leadgen_id: str, queue: "asyncio.Queue" = None):
    try:
        db.mark_status(leadgen_id, "processing")

        # Durable dedup check - protects against Meta re-delivering the same
        # webhook after a Render free-tier restart wipes the local SQLite log
        if await lead_already_stored(leadgen_id):
            logger.info(f"Lead {leadgen_id} already in Airtable, skipping (duplicate webhook)")
            db.mark_status(leadgen_id, "done")
            return

        raw = await fetch_lead_details(leadgen_id)
        parsed = parse_lead_fields(raw)

        phone = parsed["phone_number"]
        name = parsed["full_name"] or "Unknown"
        campaign = parsed["campaign_name"]
        answers_text = "\n".join(f"{k}: {v}" for k, v in parsed["answers"].items()) or "N/A"

        # 1. Alert to you, the business owner
        await send_whatsapp_template(
            to_number=settings.OWNER_WHATSAPP_NUMBER,
            template_name=settings.ALERT_TEMPLATE_NAME,
            body_params=[campaign, name, phone or "N/A", answers_text],
        )

        # 2. Automated message to the client
        if phone:
            await send_whatsapp_template(
                to_number=phone,
                template_name=settings.CLIENT_TEMPLATE_NAME,
                body_params=[name, campaign],
            )
        else:
            logger.warning(f"Lead {leadgen_id} has no phone number, skipping client message")

        # 3. Store everything in Airtable
        await create_airtable_record(
            {
                "Lead ID": leadgen_id,
                "Campaign Name": campaign,
                "Ad Name": parsed["ad_name"],
                "Form Name": parsed["form_name"],
                "Client Name": name,
                "Phone Number": phone or "",
                "Form Answers": answers_text,
                "Created Time": parsed["created_time"],
            }
        )

        db.mark_status(leadgen_id, "done")
        logger.info(f"Lead {leadgen_id} processed successfully")

    except Exception as e:
        logger.exception(f"Failed to process lead {leadgen_id}: {e}")
        retries = db.increment_retry(leadgen_id)
        db.mark_status(leadgen_id, "failed", error=str(e))

        # simple retry with backoff, re-queued instead of lost
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
