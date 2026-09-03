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
    if not settings.AIRTABLE_BASE_ID or not settings.AIRTABLE_API_KEY:
        logger.warning("AIRTABLE_BASE_ID or AIRTABLE_API_KEY is not set. Skipping Airtable record creation.")
        return None

    url = f"https://api.airtable.com/v0/{settings.AIRTABLE_BASE_ID}/{settings.AIRTABLE_TABLE_NAME}"
    headers = {
        "Authorization": f"Bearer {settings.AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, headers=headers, json={"fields": fields})
            if resp.status_code in (200, 201):
                logger.info(f"Successfully created Airtable record for Lead ID: {fields.get('Lead ID')}")
                return resp.json()
            elif resp.status_code == 422 and "UNKNOWN_FIELD_NAME" in resp.text:
                # If Remark column doesn't exist in user's Airtable yet, strip Remark and retry
                if "Remark" in fields or "Remarks" in fields:
                    fields_copy = {k: v for k, v in fields.items() if k not in ("Remark", "Remarks")}
                    resp_retry = await client.post(url, headers=headers, json={"fields": fields_copy})
                    if resp_retry.status_code in (200, 201):
                        logger.info(f"Created Airtable record (without Remark column) for Lead ID: {fields.get('Lead ID')}")
                        return resp_retry.json()
                logger.error(f"Airtable record creation failed (HTTP 422): {resp.text}")
                logger.error("HINT: Please add a column named 'Remark' or 'Form Answers' in your Airtable base if missing.")
                return None
            else:
                logger.error(f"Airtable record creation failed (HTTP {resp.status_code}): {resp.text}")
                return None
    except Exception as e:
        logger.error(f"Airtable record creation exception: {e}")
        return None


