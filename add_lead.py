import asyncio
import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.abspath("."))

from config import settings
from integrations.airtable_api import create_airtable_record
from integrations.meta_api import fetch_lead_details, parse_lead_fields
from integrations.whatsapp_api import send_whatsapp_template

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("add_lead")


async def add_lead_by_id(leadgen_id: str):
    logger.info(f"Fetching Meta details for Lead ID: {leadgen_id}...")
    try:
        raw = await fetch_lead_details(leadgen_id)
        form_id = raw.get("form_id")
        parsed = parse_lead_fields(raw)
        
        camp_cfg = settings.get_campaign_config(form_id)

        name = parsed.get("full_name") or "Valued Lead"
        phone = parsed.get("phone_number") or ""
        campaign = camp_cfg.get("campaign_name") or parsed.get("campaign_name") or "Lead Form"
        config_val = parsed.get("configuration") or ", ".join(str(v) for v in parsed.get("answers", {}).values() if v) or "N/A"
        
        rec = await create_airtable_record(
            {
                "Client Name": str(name),
                "Phone Number": str(phone),
                "Configuration": str(config_val),
                "Remark": "",
                "Campaign Name": str(campaign),
            },
            base_id=camp_cfg.get("airtable_base_id"),
            table_name=camp_cfg.get("airtable_table_name"),
        )
        if rec:
            logger.info(f"Successfully added lead {name} ({phone}) to Airtable table '{camp_cfg.get('airtable_table_name')}'!")
            return rec
    except Exception as e:
        logger.error(f"Error fetching/saving lead {leadgen_id}: {e}")
        return None


async def add_manual_lead(name: str, phone: str, configuration: str = "N/A", campaign: str = "Lead Form", form_id: str = None):
    camp_cfg = settings.get_campaign_config(form_id)
    target_campaign = campaign if campaign != "Lead Form" else camp_cfg.get("campaign_name", "Lead Form")
    target_owner = camp_cfg.get("owner_whatsapp_number") or settings.OWNER_WHATSAPP_NUMBER

    rec = await create_airtable_record(
        {
            "Client Name": str(name),
            "Phone Number": str(phone),
            "Configuration": str(configuration),
            "Remark": "",
            "Campaign Name": str(target_campaign),
        },
        base_id=camp_cfg.get("airtable_base_id"),
        table_name=camp_cfg.get("airtable_table_name"),
    )
    if rec:
        logger.info(f"Successfully added manual record for {name} ({phone}) to Airtable!")

    # 1. Owner Alert
    if target_owner:
        try:
            answers_text = f"which_configuration_are_you_looking_for?: {configuration}"
            await send_whatsapp_template(
                to_number=target_owner,
                template_name=camp_cfg.get("alert_template_name", settings.ALERT_TEMPLATE_NAME),
                body_params=[target_campaign, name, phone or "Not provided", answers_text],
            )
            logger.info(f"WhatsApp alert sent to campaign owner ({target_owner}) successfully")
        except Exception as wa_err:
            logger.error(f"Failed to send owner WhatsApp alert: {wa_err}")

    # 2. Client Welcome
    if phone:
        try:
            await send_whatsapp_template(
                to_number=phone,
                template_name=camp_cfg.get("client_template_name", settings.CLIENT_TEMPLATE_NAME),
                body_params=[name, target_campaign, configuration],
                custom_message=camp_cfg.get("client_welcome_message"),
            )
            logger.info(f"WhatsApp welcome message sent to client ({phone}) successfully")
        except Exception as client_wa_err:
            logger.error(f"Failed to send client WhatsApp message: {client_wa_err}")

    return rec


if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg.isdigit():
            asyncio.run(add_lead_by_id(arg))
        else:
            name = sys.argv[1]
            phone = sys.argv[2] if len(sys.argv) > 2 else ""
            config_val = sys.argv[3] if len(sys.argv) > 3 else "N/A"
            campaign = sys.argv[4] if len(sys.argv) > 4 else "Lead Form"
            asyncio.run(add_manual_lead(name, phone, config_val, campaign))
    else:
        print("Usage:")
        print("  python add_lead.py <LEAD_ID>")
        print("  python add_lead.py 'Ashish Shukla' '+919876543210' '2_bhk' 'Silver 26 August'")

