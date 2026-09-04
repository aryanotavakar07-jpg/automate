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

        # Fetch lead details from Meta Graph API
        is_test_lead = str(leadgen_id).startswith("4444") or "test" in str(leadgen_id).lower() or not settings.META_ACCESS_TOKEN
        try:
            raw = await fetch_lead_details(leadgen_id)
            parsed = parse_lead_fields(raw)
            logger.info(f"Successfully fetched lead details for {leadgen_id} from Meta API")
        except Exception as meta_err:
            if is_test_lead:
                logger.warning(f"Could not fetch lead details for test lead {leadgen_id}: {meta_err}. Using test fallback data.")
                parsed = {
                    "campaign_name": "Meta Ads Test Campaign",
                    "ad_name": "Test Ad",
                    "form_name": "Test Lead Form",
                    "created_time": datetime.now(timezone.utc).isoformat(),
                    "full_name": "Test Customer",
                    "phone_number": settings.OWNER_WHATSAPP_NUMBER or None,
                    "answers": {"Note": f"Test lead generated from Meta Tool (ID: {leadgen_id})"},
                }
            else:
                logger.error(f"Failed to fetch lead details from Meta API for lead {leadgen_id}: {meta_err}")
                parsed = {
                    "campaign_name": "Meta Lead Form (API Error)",
                    "ad_name": "Unknown",
                    "form_name": "Unknown",
                    "created_time": datetime.now(timezone.utc).isoformat(),
                    "full_name": f"Lead {leadgen_id}",
                    "phone_number": None,
                    "answers": {"Note": f"Meta API error for Lead ID {leadgen_id}: {meta_err}"},
                }

        client_phone = parsed.get("phone_number")
        name = parsed.get("full_name") or "Valued Lead"
        campaign = parsed.get("campaign_name") or "Lead Form"
        answers_text = "\n".join(f"{k}: {v}" for k, v in parsed.get("answers", {}).items()) or "N/A"

        # 1. Alert to the business owner
        if settings.OWNER_WHATSAPP_NUMBER:
            try:
                display_phone = client_phone or "Not provided"
                await send_whatsapp_template(
                    to_number=settings.OWNER_WHATSAPP_NUMBER,
                    template_name=settings.ALERT_TEMPLATE_NAME,
                    body_params=[campaign, name, display_phone, answers_text],
                )
                logger.info("WhatsApp alert sent to owner successfully")
            except Exception as wa_err:
                logger.error(f"Failed to send owner WhatsApp alert: {wa_err}")

        # 2. Automated message to the client
        if client_phone:
            try:
                config_val = parsed.get("configuration") or ""
                await send_whatsapp_template(
                    to_number=client_phone,
                    template_name=settings.CLIENT_TEMPLATE_NAME,
                    body_params=[name, campaign, config_val],
                )
                logger.info(f"WhatsApp welcome message sent to client ({client_phone}) successfully")
            except Exception as client_wa_err:
                logger.error(f"Failed to send client WhatsApp message to {client_phone}: {client_wa_err}")
        else:
            logger.warning(f"No valid phone number found for lead {leadgen_id} - skipping client WhatsApp welcome message")

        # 3. Store in Airtable (Client Name, Phone Number, Configuration, Remark, Campaign Name)
        config_val = parsed.get("configuration") or ", ".join(str(v) for v in parsed.get("answers", {}).values() if v) or "N/A"
        try:
            airtable_res = await create_airtable_record(
                {
                    "Client Name": str(name),
                    "Phone Number": str(client_phone or ""),
                    "Configuration": str(config_val),
                    "Remark": "",
                    "Campaign Name": str(campaign),
                }
            )
            if airtable_res:
                logger.info(f"Lead {name} saved to Airtable successfully")
            else:
                logger.warning(f"Airtable record creation returned None for lead {name}")
        except Exception as airtable_err:
            logger.error(f"Failed to save lead to Airtable: {airtable_err}")

        db.mark_status(leadgen_id, "done")
        logger.info(f"Lead {leadgen_id} processed successfully")

    except Exception as e:
        logger.exception(f"Failed to process lead {leadgen_id}: {e}")
        try:
            retries = db.increment_retry(leadgen_id)
            db.mark_status(leadgen_id, "failed", error=str(e))

            if retries < settings.MAX_RETRIES and queue is not None:
                delay = min(60, 2 ** retries)
                logger.info(f"Retrying lead {leadgen_id} in {delay}s (attempt {retries})")
                await asyncio.sleep(delay)
                await queue.put(leadgen_id)
        except Exception as db_err:
            logger.error(f"Error updating retry DB status for lead {leadgen_id}: {db_err}")


async def worker_loop(queue: "asyncio.Queue", worker_id: int):
    logger.info(f"Worker {worker_id} started")
    while True:
        try:
            leadgen_id = await queue.get()
            logger.info(f"Worker {worker_id} picked up lead {leadgen_id}")
            await process_lead(leadgen_id, queue)
            queue.task_done()
        except Exception as err:
            logger.error(f"Worker {worker_id} encountered top-level loop error: {err}", exc_info=True)
            await asyncio.sleep(2)

