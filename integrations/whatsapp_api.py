import httpx
import logging
from config import settings

logger = logging.getLogger("whatsapp_api")
LOCAL_WA_URL = "http://localhost:3000/send-message"


async def send_whatsapp_template(to_number: str, template_name: str, body_params: list[str]):
    """Sends WhatsApp message via Green-API (cloud QR service) or local QR service."""
    if template_name == "lead_alert":
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

    clean_phone = to_number.replace("+", "").replace(" ", "").strip()

    # Prioritize 100% Free Local Baileys WhatsApp Engine
    payload = {"to": clean_phone, "message": message_text}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(LOCAL_WA_URL, json=payload)
            resp.raise_for_status()
            logger.info(f"WhatsApp message sent to {to_number} via local QR server (100% Free)")
            return resp.json()
    except Exception as local_err:
        logger.warning(f"Local WhatsApp server not ready or failed ({local_err}). Checking Green-API fallback...")
        if settings.GREEN_API_INSTANCE_ID and settings.GREEN_API_TOKEN:
            chat_id = f"{clean_phone}@c.us" if "@" not in clean_phone else clean_phone
            inst_id = str(settings.GREEN_API_INSTANCE_ID).strip()
            prefix = inst_id[:4] if len(inst_id) >= 4 else ""

            primary_host = f"https://{prefix}.api.greenapi.com" if prefix else "https://api.green-api.com"
            url = f"{primary_host}/waInstance{inst_id}/sendMessage/{settings.GREEN_API_TOKEN}"
            green_payload = {"chatId": chat_id, "message": message_text}

            async with httpx.AsyncClient(timeout=15) as client:
                try:
                    resp = await client.post(url, json=green_payload)
                    resp.raise_for_status()
                    logger.info(f"WhatsApp message sent to {to_number} via Green-API ({primary_host})")
                    return resp.json()
                except Exception as e:
                    logger.error(f"Green-API sending failed: {e}")
                    raise e
        else:
            raise local_err
