import asyncio
import os
import sys
import logging
import httpx
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.abspath("."))

from config import settings
from integrations.meta_api import fetch_lead_details, parse_lead_fields
from integrations.airtable_api import create_airtable_record

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_sorted")

AIRTABLE_BASE_URL = f"https://api.airtable.com/v0/{settings.AIRTABLE_BASE_ID}/{settings.AIRTABLE_TABLE_NAME}"
AIRTABLE_HEADERS = {
    "Authorization": f"Bearer {settings.AIRTABLE_API_KEY}",
    "Content-Type": "application/json",
}

ALL_LEAD_IDS = [
    '2558868477912282', '1712514736621026', '1092772906627776', '1046727704834268',
    '1966693307351635', '1575548004113038', '1067176055697550', '991752933878513',
    '1096317319486091', '1082726227591530', '1996548427716072', '1554890243101284',
    '2470905476762752', '1753561969258409', '2288790555252788', '1718261346095458',
    '1440251758160206', '881093944989812', '1070548095468626', '959405139866946',
    '1078185541396788', '1013047901771463', '1594182935489581', '2131456858247669',
    '2839029216449886', '1461255199147927', '1630248371999485', '1473117224840522',
    '1744162913534029', '1101363268900821', '1428809345831835', '2070095287205957',
    '965001579957711', '1068338179263602', '946999037730889', '1596475125603355',
    '1615546300244186', '1735232624408573', '1080977827717272', '1591293816004254',
    '1784411482980429', '1038446915666084', '1372477538355333', '1754754268796143'
]

async def clear_all_airtable_records():
    """Fetch and delete all records currently in Airtable."""
    records = []
    offset = None
    async with httpx.AsyncClient(timeout=15) as client:
        while True:
            params = {}
            if offset:
                params["offset"] = offset
            resp = await client.get(AIRTABLE_BASE_URL, headers=AIRTABLE_HEADERS, params=params)
            if resp.status_code != 200:
                break
            data = resp.json()
            recs = data.get("records", [])
            records.extend(recs)
            offset = data.get("offset")
            if not offset:
                break

    if records:
        logger.info(f"Deleting {len(records)} records from Airtable to re-order chronologically...")
        record_ids = [r["id"] for r in records]
        async with httpx.AsyncClient(timeout=20) as client:
            for i in range(0, len(record_ids), 10):
                chunk = record_ids[i:i + 10]
                params = [("records[]", r_id) for r_id in chunk]
                await client.delete(AIRTABLE_BASE_URL, headers=AIRTABLE_HEADERS, params=params)

async def main():
    if not settings.META_ACCESS_TOKEN:
        logger.error("No META_ACCESS_TOKEN set!")
        return

    # Step 1: Clear current Airtable table
    await clear_all_airtable_records()

    # Step 2: Fetch Meta details for all lead IDs
    logger.info("Fetching Meta Graph API details for all leads...")
    lead_objects = []

    for leadgen_id in ALL_LEAD_IDS:
        try:
            raw = await fetch_lead_details(leadgen_id)
            parsed = parse_lead_fields(raw)
            lead_objects.append({
                "leadgen_id": leadgen_id,
                "created_time": raw.get("created_time", ""),
                "parsed": parsed,
                "raw": raw
            })
        except Exception as err:
            logger.warning(f"Could not fetch details for lead {leadgen_id}: {err}")

    # Step 3: Sort chronologically ascending (oldest first -> latest/newest at bottom)
    lead_objects.sort(key=lambda x: x.get("created_time", ""))
    logger.info(f"Sorted {len(lead_objects)} leads chronologically by created_time (Oldest to Newest).")

    # Step 4: Insert sorted leads into Airtable
    success_count = 0
    for item in lead_objects:
        parsed = item["parsed"]
        leadgen_id = item["leadgen_id"]
        created_time = item["created_time"]

        client_phone = parsed.get("phone_number")
        name = parsed.get("full_name") or "Valued Lead"
        campaign = parsed.get("campaign_name") or "Lead Form"
        config_val = parsed.get("configuration") or ", ".join(str(v) for v in parsed.get("answers", {}).values() if v) or "N/A"

        logger.info(f"Inserting [{created_time}] -> Name: {name} | Phone: {client_phone}")

        rec = await create_airtable_record({
            "Client Name": str(name),
            "Phone Number": str(client_phone or ""),
            "Configuration": str(config_val),
            "Remark": "",
            "Campaign Name": str(campaign),
        })
        if rec:
            success_count += 1

    logger.info(f"\n==========================================")
    logger.info(f"Chronological Backfill Complete!")
    logger.info(f"Successfully inserted into Airtable: {success_count}")
    logger.info(f"The most latest lead (Ulka Parmar) is now at the very bottom!")
    logger.info(f"==========================================")

if __name__ == "__main__":
    asyncio.run(main())
