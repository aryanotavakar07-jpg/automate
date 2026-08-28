import httpx
from config import settings

GRAPH_API_VERSION = "v21.0"


async def fetch_lead_details(leadgen_id: str) -> dict:
    """The webhook only tells us a lead ID exists. This calls the Graph API
    to get the actual campaign name, form answers, name, and phone number."""
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{leadgen_id}"
    params = {
        "access_token": settings.META_ACCESS_TOKEN,
        "fields": "field_data,campaign_name,ad_name,form_name,created_time,platform",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


def parse_lead_fields(lead_data: dict) -> dict:
    """Turns Meta's raw field_data array into a clean, usable dict."""
    parsed = {
        "campaign_name": lead_data.get("campaign_name") or "Unknown Campaign",
        "ad_name": lead_data.get("ad_name", ""),
        "form_name": lead_data.get("form_name", ""),
        "created_time": lead_data.get("created_time", ""),
        "full_name": None,
        "phone_number": None,
        "configuration": None,
        "answers": {},
    }

    for field in lead_data.get("field_data", []):
        name = field.get("name", "")
        values = field.get("values", [])
        value = values[0] if values else ""
        key = name.lower().replace(" ", "_")

        if key in ("full_name", "name"):
            parsed["full_name"] = value
        elif key in ("phone_number", "phone"):
            parsed["phone_number"] = value
        else:
            parsed["answers"][name] = value
            # Check if this question is about configuration or BHK selection
            if any(t in key for t in ("config", "bhk", "type", "flat", "room", "size", "requirement", "option", "unit")):
                parsed["configuration"] = value
            elif "bhk" in str(value).lower():
                parsed["configuration"] = value

    return parsed
