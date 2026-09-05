import os
import json
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("config")


class Settings:
    # --- Meta / Facebook Lead Ads ---
    META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
    META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN")
    META_APP_SECRET = os.getenv("META_APP_SECRET")
    ALLOWED_FORM_ID = os.getenv("ALLOWED_FORM_ID")

    # --- WhatsApp Transport Credentials ---
    OWNER_WHATSAPP_NUMBER = os.getenv("OWNER_WHATSAPP_NUMBER")
    ALERT_TEMPLATE_NAME = os.getenv("ALERT_TEMPLATE_NAME", "lead_alert")
    CLIENT_TEMPLATE_NAME = os.getenv("CLIENT_TEMPLATE_NAME", "lead_welcome")
    TEMPLATE_LANGUAGE = os.getenv("TEMPLATE_LANGUAGE", "en_US")

    # Meta Official WhatsApp Business Cloud API (Optional - Dual Transport)
    WA_CLOUD_ACCESS_TOKEN = os.getenv("WA_CLOUD_ACCESS_TOKEN")
    WA_CLOUD_PHONE_NUMBER_ID = os.getenv("WA_CLOUD_PHONE_NUMBER_ID")

    # --- Airtable ---
    AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
    AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
    AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME", "Leads")

    # --- Database (Supabase Postgres URL or SQLite fallback) ---
    DATABASE_URL = os.getenv("DATABASE_URL")

    # --- Security & Auth ---
    API_SECRET_KEY = os.getenv("API_SECRET_KEY")

    # --- App behavior ---
    WORKER_COUNT = int(os.getenv("WORKER_COUNT", "5"))
    PORT = int(os.getenv("PORT", "8000"))
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", "5"))

    def get_campaign_config(self, form_id: str = None) -> dict:
        """Dynamically resolves settings for a given form_id from campaigns.json.
        If form_id is not found or campaigns.json is missing, returns default .env configuration."""
        default_config = {
            "form_id": form_id or self.ALLOWED_FORM_ID or "default",
            "campaign_name": "Lead Form",
            "owner_whatsapp_number": self.OWNER_WHATSAPP_NUMBER,
            "airtable_base_id": self.AIRTABLE_BASE_ID,
            "airtable_table_name": self.AIRTABLE_TABLE_NAME,
            "alert_template_name": self.ALERT_TEMPLATE_NAME,
            "client_template_name": self.CLIENT_TEMPLATE_NAME,
            "client_welcome_message": None,
        }

        campaigns_file = os.path.join(os.path.dirname(__file__), "campaigns.json")
        if not os.path.exists(campaigns_file):
            return default_config

        try:
            with open(campaigns_file, "r", encoding="utf-8") as f:
                campaigns_data = json.load(f)

            form_key = str(form_id).strip() if form_id else None
            matched = None

            if isinstance(campaigns_data, dict):
                if form_key and form_key in campaigns_data:
                    matched = campaigns_data[form_key]
                elif "default" in campaigns_data:
                    matched = campaigns_data["default"]
            elif isinstance(campaigns_data, list):
                for item in campaigns_data:
                    if str(item.get("form_id")).strip() == form_key:
                        matched = item
                        break

            if matched:
                cfg = dict(default_config)
                cfg.update({
                    "campaign_name": matched.get("campaign_name", default_config["campaign_name"]),
                    "owner_whatsapp_number": matched.get("owner_whatsapp_number") or default_config["owner_whatsapp_number"],
                    "airtable_base_id": matched.get("airtable_base_id") or default_config["airtable_base_id"],
                    "airtable_table_name": matched.get("airtable_table_name") or default_config["airtable_table_name"],
                    "alert_template_name": matched.get("alert_template_name") or default_config["alert_template_name"],
                    "client_template_name": matched.get("client_template_name") or default_config["client_template_name"],
                    "client_welcome_message": matched.get("client_welcome_message"),
                })
                return cfg

        except Exception as e:
            logger.warning(f"Error reading campaigns.json: {e}. Using default settings.")

        return default_config


settings = Settings()

