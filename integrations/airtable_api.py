import httpx
from config import settings


async def lead_already_stored(lead_id: str) -> bool:
    """Checks Airtable itself for this Lead ID. This is the durable dedup check -
    it survives restarts even on hosts (like Render's free tier) where local
    disk doesn't persist between spin-down/spin-up cycles."""
    url = f"https://api.airtable.com/v0/{settings.AIRTABLE_BASE_ID}/{settings.AIRTABLE_TABLE_NAME}"
    headers = {"Authorization": f"Bearer {settings.AIRTABLE_API_KEY}"}
    params = {"filterByFormula": f"{{Lead ID}}='{lead_id}'", "maxRecords": 1}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return len(resp.json().get("records", [])) > 0


async def create_airtable_record(fields: dict):
    url = f"https://api.airtable.com/v0/{settings.AIRTABLE_BASE_ID}/{settings.AIRTABLE_TABLE_NAME}"
    headers = {
        "Authorization": f"Bearer {settings.AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"fields": fields}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()
