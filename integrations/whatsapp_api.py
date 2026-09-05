import httpx
import re
import logging
from config import settings

logger = logging.getLogger("whatsapp_api")
LOCAL_WA_URL = "http://localhost:3000/send-message"


async def send_whatsapp_template(to_number: str, template_name: str, body_params: list[str], custom_message: str = None, session_id: str = None):
    """Sends WhatsApp message via Meta Official Cloud API (if configured) or multi-session local Baileys QR service."""
    clean_phone = re.sub(r"\D", "", to_number)
    if clean_phone.startswith("0") and len(clean_phone) == 11:
        clean_phone = clean_phone[1:]
    if len(clean_phone) == 10:
        clean_phone = "91" + clean_phone

    # 1. Determine message text
    if custom_message:
        name = body_params[0] if len(body_params) >= 1 else "Customer"
        campaign = body_params[1] if len(body_params) >= 2 else "Lead Form"
        config_val = body_params[2] if len(body_params) >= 3 else "N/A"
        message_text = custom_message.format(name=name, campaign=campaign, configuration=config_val)
    elif template_name == "lead_alert":
        campaign, name, phone, answers = body_params if len(body_params) == 4 else ("N/A", "N/A", "N/A", "N/A")
        message_text = (
            f"🚨 *New Lead Alert!*\n\n"
            f"📌 *Campaign:* {campaign}\n"
            f"👤 *Name:* {name}\n"
            f"📞 *Phone:* {phone}\n\n"
            f"📋 *Answers:*\n{answers}"
        )
    elif template_name == "lead_welcome":
        name = body_params[0] if len(body_params) >= 1 else "Customer"
        config_val = body_params[2] if len(body_params) >= 3 and body_params[2] else ""
        
        if config_val:
            bhk_text = f"*{config_val} property at GOREGAON EAST near OBEROI MALL*"
        else:
            bhk_text = "*property at GOREGAON EAST near OBEROI MALL*"

        message_text = (
            f"Hello {name}! 👋\n\n"
            f"Thank you for your interest. We have received your enquiry for a {bhk_text}.\n\n"
            f"Would you like us to share the *official E-Brochure & Floor Plans*, or would you prefer to *schedule a Site Visit*?"
        )
    else:
        message_text = "\n".join(body_params)

    # 2. Priority 1: Meta Official WhatsApp Business Cloud API (if configured)
    if settings.WA_CLOUD_ACCESS_TOKEN and settings.WA_CLOUD_PHONE_NUMBER_ID:
        cloud_url = f"https://graph.facebook.com/v21.0/{settings.WA_CLOUD_PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {settings.WA_CLOUD_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": clean_phone,
            "type": "text",
            "text": {"body": message_text},
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(cloud_url, headers=headers, json=payload)
                resp.raise_for_status()
                logger.info(f"WhatsApp Cloud API message sent successfully to {to_number}")
                return resp.json()
        except Exception as cloud_err:
            logger.warning(f"WhatsApp Cloud API send failed ({cloud_err}). Falling back to local Baileys QR service...")

    # 3. Priority 2: Multi-Session Baileys WhatsApp Engine
    payload = {"to": clean_phone, "message": message_text, "session": session_id}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(LOCAL_WA_URL, json=payload)
            resp.raise_for_status()
            logger.info(f"WhatsApp message sent to {to_number} via local QR server (Session: {session_id})")
            return resp.json()
    except Exception as err:
        logger.warning(f"WhatsApp message to {to_number} skipped/failed: {err}")
        return {"status": "skipped", "error": str(err)}
