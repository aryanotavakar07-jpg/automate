import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # --- Meta / Facebook Lead Ads ---
    META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")           # Graph API access token
    META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN")           # Your own made-up string, used during webhook setup
    META_APP_SECRET = os.getenv("META_APP_SECRET")               # Used to verify webhook payloads are really from Meta

    # --- WhatsApp Cloud API ---
    WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", META_ACCESS_TOKEN)
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")   # The "From" number's ID from Meta
    OWNER_WHATSAPP_NUMBER = os.getenv("OWNER_WHATSAPP_NUMBER")         # Your number, e.g. 91XXXXXXXXXX (no +, no spaces)

    ALERT_TEMPLATE_NAME = os.getenv("ALERT_TEMPLATE_NAME", "lead_alert")
    CLIENT_TEMPLATE_NAME = os.getenv("CLIENT_TEMPLATE_NAME", "lead_welcome")
    TEMPLATE_LANGUAGE = os.getenv("TEMPLATE_LANGUAGE", "en_US")

    # --- Airtable ---
    AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
    AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
    AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME", "Leads")

    # --- App behavior ---
    WORKER_COUNT = int(os.getenv("WORKER_COUNT", "5"))   # how many leads can be processed in parallel
    PORT = int(os.getenv("PORT", "8000"))
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", "5"))


settings = Settings()
