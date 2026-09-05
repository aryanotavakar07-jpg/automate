import httpx
import logging
from config import settings

logger = logging.getLogger("airtable_api")


async def lead_already_stored(identifier: str, base_id: str = None, table_name: str = None) -> bool:
    """Checks Airtable for Phone Number or Client Name dedup. If Airtable API fails or hits rate limits,
    it returns False gracefully so WhatsApp messages are never blocked."""
    if not identifier:
        return False

    target_base = base_id or settings.AIRTABLE_BASE_ID
    target_table = table_name or settings.AIRTABLE_TABLE_NAME

    if not target_base or not settings.AIRTABLE_API_KEY:
        return False

    url = f"https://api.airtable.com/v0/{target_base}/{target_table}"
    headers = {"Authorization": f"Bearer {settings.AIRTABLE_API_KEY}"}
    params = {"filterByFormula": f"OR({{Phone Number}}='{identifier}', {{Client Name}}='{identifier}')", "maxRecords": 1}
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


async def create_airtable_record(fields: dict, base_id: str = None, table_name: str = None):
    target_base = base_id or settings.AIRTABLE_BASE_ID
    target_table = table_name or settings.AIRTABLE_TABLE_NAME

    if not target_base or not settings.AIRTABLE_API_KEY:
        logger.warning("AIRTABLE_BASE_ID or AIRTABLE_API_KEY is not set. Skipping Airtable record creation.")
        return None

    url = f"https://api.airtable.com/v0/{target_base}/{target_table}"
    headers = {
        "Authorization": f"Bearer {settings.AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }

    current_fields = dict(fields)
    max_attempts = 4

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            for attempt in range(max_attempts):
                resp = await client.post(url, headers=headers, json={"fields": current_fields})
                if resp.status_code in (200, 201):
                    logger.info(f"Successfully created Airtable record in {target_table} for Client Name: {current_fields.get('Client Name')}")
                    return resp.json()
                elif resp.status_code == 422 and "UNKNOWN_FIELD_NAME" in resp.text:
                    # Parse unknown field name from error response if possible
                    import re
                    match = re.search(r'Unknown field name:\s*"([^"]+)"', resp.text)
                    if match:
                        bad_field = match.group(1)
                        if bad_field in current_fields:
                            logger.warning(f"Airtable table missing column '{bad_field}'. Removing and retrying...")
                            current_fields.pop(bad_field)
                            continue
                    
                    # Fallback stripping of optional columns
                    if "Remark" in current_fields:
                        current_fields.pop("Remark")
                        continue
                    elif "Remarks" in current_fields:
                        current_fields.pop("Remarks")
                        continue
                    elif "Campaign Name" in current_fields:
                        current_fields.pop("Campaign Name")
                        continue
                    elif "Configuration" in current_fields:
                        current_fields.pop("Configuration")
                        continue
                
                logger.error(f"Airtable record creation failed (HTTP {resp.status_code}): {resp.text}")
                return None
    except Exception as e:
        logger.error(f"Airtable record creation exception: {e}")
        return None



