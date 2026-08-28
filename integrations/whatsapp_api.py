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
        name, campaign = body_params if len(body_params) == 2 else ("Customer", "our offer")
        message_text = f"Hi {name}, thanks for your interest in {campaign}! We'll be in touch shortly."
    else:
        message_text = "\n".join(body_params)

    clean_phone = to_number.replace("+", "").replace(" ", "").strip()

    # If Green-API is configured, use Green-API cloud QR service (best for Render)
    if settings.GREEN_API_INSTANCE_ID and settings.GREEN_API_TOKEN:
        chat_id = f"{clean_phone}@c.us" if "@" not in clean_phone else clean_phone
        url = f"https://api.green-api.com/waInstance{settings.GREEN_API_INSTANCE_ID}/sendMessage/{settings.GREEN_API_TOKEN}"
        payload = {"chatId": chat_id, "message": message_text}

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            logger.info(f"WhatsApp message sent to {to_number} via Green-API")
            return resp.json()
    else:
        # Fallback to local server
        payload = {"to": clean_phone, "message": message_text}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(LOCAL_WA_URL, json=payload)
            resp.raise_for_status()
            logger.info(f"WhatsApp message sent to {to_number} via local QR server")
            return resp.json()
