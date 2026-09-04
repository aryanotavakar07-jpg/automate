import httpx
from config import settings

GRAPH_API_VERSION = "v21.0"


async def fetch_lead_details(leadgen_id: str) -> dict:
    """The webhook only tells us a lead ID exists. This calls the Graph API
    to get the actual campaign name, form answers, name, and phone number."""
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{leadgen_id}"
    params = {
        "access_token": settings.META_ACCESS_TOKEN,
        "fields": "field_data,campaign_name,ad_name,form_id,created_time,platform",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)
        if resp.status_code != 200:
            try:
                err_body = resp.json().get("error", {})
                err_msg = err_body.get("message") or resp.text
                err_code = err_body.get("code") or resp.status_code
                err_subcode = err_body.get("error_subcode", "")
                subcode_str = f" (subcode {err_subcode})" if err_subcode else ""
                raise RuntimeError(f"Meta Graph API Error (Code {err_code}{subcode_str}): {err_msg}")
            except Exception as parse_err:
                if isinstance(parse_err, RuntimeError):
                    raise parse_err
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

    first_name = ""
    last_name = ""

    for field in lead_data.get("field_data", []):
        name = field.get("name", "")
        values = field.get("values", [])
        value = values[0] if values else ""
        if not value:
            continue

        key = name.lower().replace(" ", "_").replace("-", "_")

        if key in ("full_name", "name", "user_name") or "full_name" in key or "your_name" in key:
            parsed["full_name"] = str(value).strip()
        elif key in ("first_name", "given_name") or "first_name" in key:
            first_name = str(value).strip()
        elif key in ("last_name", "family_name", "surname") or "last_name" in key:
            last_name = str(value).strip()
        elif any(p in key for p in ("phone", "mobile", "contact", "whatsapp", "cell", "number")):
            parsed["phone_number"] = str(value).strip()
        else:
            parsed["answers"][name] = str(value).strip()
            # Check if this question is about configuration or BHK selection
            if any(t in key for t in ("config", "bhk", "type", "flat", "room", "size", "requirement", "option", "unit")):
                parsed["configuration"] = str(value).strip()
            elif "bhk" in str(value).lower():
                parsed["configuration"] = str(value).strip()

    # If full_name wasn't explicitly set, assemble from first_name and last_name
    if not parsed["full_name"] and (first_name or last_name):
        parsed["full_name"] = f"{first_name} {last_name}".strip()

    # Clean phone number format
    if parsed["phone_number"]:
        raw_phone = str(parsed["phone_number"]).strip()
        digits = "".join(c for c in raw_phone if c.isdigit())
        if digits.startswith("0") and len(digits) == 11:
            digits = digits[1:]
        if len(digits) == 10:
            parsed["phone_number"] = "+91" + digits
        elif len(digits) == 12 and digits.startswith("91"):
            parsed["phone_number"] = "+" + digits
        elif raw_phone.startswith("+"):
            parsed["phone_number"] = "+" + digits
        else:
            parsed["phone_number"] = "+" + digits

    return parsed

