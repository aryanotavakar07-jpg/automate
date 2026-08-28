import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # --- Meta / Facebook Lead Ads ---
    META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
    META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN")
    META_APP_SECRET = os.getenv("META_APP_SECRET")

    # --- WhatsApp QR Code API (Green-API / Local) ---
    GREEN_API_INSTANCE_ID = os.getenv("GREEN_API_INSTANCE_ID")
    GREEN_API_TOKEN = os.getenv("GREEN_API_TOKEN")
    OWNER_WHATSAPP_NUMBER = os.getenv("OWNER_WHATSAPP_NUMBER")

    ALERT_TEMPLATE_NAME = os.getenv("ALERT_TEMPLATE_NAME", "lead_alert")
    CLIENT_TEMPLATE_NAME = os.getenv("CLIENT_TEMPLATE_NAME", "lead_welcome")
    TEMPLATE_LANGUAGE = os.getenv("TEMPLATE_LANGUAGE", "en_US")

    # --- Airtable ---
    AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
    AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
    AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME", "Leads")

    # --- App behavior ---
    WORKER_COUNT = int(os.getenv("WORKER_COUNT", "5"))
    PORT = int(os.getenv("PORT", "8000"))
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", "5"))


settings = Settings()
