import httpx
import logging
from config import settings

logger = logging.getLogger("airtable_api")


async def lead_already_stored(lead_id: str) -> bool:
    """Checks Airtable for Lead ID dedup. If Airtable API fails or hits rate limits,
    it returns False gracefully so WhatsApp messages are never blocked."""
    url = f"https://api.airtable.com/v0/{settings.AIRTABLE_BASE_ID}/{settings.AIRTABLE_TABLE_NAME}"
    headers = {"Authorization": f"Bearer {settings.AIRTABLE_API_KEY}"}
    params = {"filterByFormula": f"{{Lead ID}}='{lead_id}'", "maxRecords": 1}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 200:
                return len(resp.json().get("records", [])) > 0
            else:
                logger.warning(f"Airtable API returned status {resp.status_code}: {resp.text}")
                return False
    except Exception as e:
        logger.warning(f"Airtable check failed: {e}. Allowing lead to proceed.")
        return False


async def create_airtable_record(fields: dict):
    url = f"https://api.airtable.com/v0/{settings.AIRTABLE_BASE_ID}/{settings.AIRTABLE_TABLE_NAME}"
    headers = {
        "Authorization": f"Bearer {settings.AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"fields": fields}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code in (200, 201):
                return resp.json()
            else:
                logger.warning(f"Airtable record creation failed ({resp.status_code}): {resp.text}")
                return None
    except Exception as e:
        logger.warning(f"Airtable record creation error: {e}")
        return None
