import asyncio
import sqlite3
import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.abspath("."))

from config import settings
from integrations.meta_api import fetch_lead_details, parse_lead_fields
from integrations.whatsapp_api import send_whatsapp_template
from integrations.airtable_api import create_airtable_record

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("reprocess")

async def main():
    db_path = "leads.db"
    if not os.path.exists(db_path):
        logger.error("No leads.db found in current directory. Make sure you run this in the app folder.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT leadgen_id, status, created_at FROM leads ORDER BY created_at ASC")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        logger.info("No leads found in leads.db.")
        return

    logger.info(f"Found {len(rows)} lead IDs in leads.db. Processing...")

    for leadgen_id, status, created_at in rows:
        logger.info(f"--- Processing Lead ID: {leadgen_id} (Received: {created_at}) ---")
        try:
            raw = await fetch_lead_details(leadgen_id)
            parsed = parse_lead_fields(raw)

            client_phone = parsed.get("phone_number")
            name = parsed.get("full_name") or "Valued Lead"
            campaign = parsed.get("campaign_name") or "Lead Form"
            answers_text = "\n".join(f"{k}: {v}" for k, v in parsed.get("answers", {}).items()) or "N/A"

            logger.info(f"Fetched Meta Data -> Name: {name} | Phone: {client_phone} | Campaign: {campaign}")

            # 1. Store real data in Airtable
            config_val = parsed.get("configuration") or ", ".join(str(v) for v in parsed.get("answers", {}).values() if v) or "N/A"
            try:
                rec = await create_airtable_record({
                    "Client Name": str(name),
                    "Phone Number": str(client_phone or ""),
                    "Configuration": str(config_val),
                    "Remark": "",
                    "Campaign Name": str(campaign),
                })
                if rec:
                    logger.info("✓ Lead saved to Airtable successfully")
            except Exception as airtable_err:
                logger.error(f"✗ Failed to save to Airtable: {airtable_err}")

            # 2. Send WhatsApp Owner Alert
            if settings.OWNER_WHATSAPP_NUMBER:
                try:
                    await send_whatsapp_template(
                        to_number=settings.OWNER_WHATSAPP_NUMBER,
                        template_name=settings.ALERT_TEMPLATE_NAME,
                        body_params=[campaign, name, client_phone or "Not provided", answers_text],
                    )
                    logger.info("✓ Owner alert sent via WhatsApp")
                except Exception as wa_err:
                    logger.error(f"✗ Failed to send owner WhatsApp alert: {wa_err}")

            # 3. Send WhatsApp Client Welcome Message
            if client_phone:
                owner_clean = settings.OWNER_WHATSAPP_NUMBER.replace("+", "").replace(" ", "").strip() if settings.OWNER_WHATSAPP_NUMBER else ""
                client_clean = client_phone.replace("+", "").replace(" ", "").strip()

                if owner_clean and client_clean == owner_clean:
                    logger.info("Client phone equals owner phone - skipping client welcome message")
                else:
                    try:
                        config_val = parsed.get("configuration") or ""
                        await send_whatsapp_template(
                            to_number=client_phone,
                            template_name=settings.CLIENT_TEMPLATE_NAME,
                            body_params=[name, campaign, config_val],
                        )
                        logger.info(f"✓ Client welcome message sent to {client_phone}")
                    except Exception as client_wa_err:
                        logger.error(f"✗ Failed to send client WhatsApp message: {client_wa_err}")
            else:
                logger.warning(f"No client phone found for lead {leadgen_id} - skipping client welcome message")

        except Exception as err:
            logger.error(f"✗ Could not fetch Meta Graph API details for lead {leadgen_id}: {err}")

    logger.info("Processing complete!")

if __name__ == "__main__":
    asyncio.run(main())
