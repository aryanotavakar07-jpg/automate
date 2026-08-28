import httpx
import logging

logger = logging.getLogger("whatsapp_api")
WHATSAPP_SERVICE_URL = "http://localhost:3000/send-message"


async def send_whatsapp_template(to_number: str, template_name: str, body_params: list[str]):
    """Sends a plain-text WhatsApp message via the local Baileys QR Code WhatsApp service."""
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

    payload = {
        "to": to_number,
        "message": message_text
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(WHATSAPP_SERVICE_URL, json=payload)
        resp.raise_for_status()
        return resp.json()
