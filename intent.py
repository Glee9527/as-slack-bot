import os
import json
from openai import OpenAI
import re

print("DEBUG intent.py loaded from:", __file__)

# --- 新增：Email 偵測與強制規則 ---
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
FORCED_EMAIL_FIELDS = [
    "asset_name",
    "ain",
    "serial_number",
    "purchased_on",
    "assigned_to_user_name",
    "assigned_to_user_email",
]

def _forced_email_intent(email: str):
    """建立強制 email 規則的 intent 結構"""
    return {
        "intent": "user_or_asset_lookup",
        "query": email,
        "fields": FORCED_EMAIL_FIELDS,
    }

KEYWORDS_LICENSE = ["license", "licenses", "授權", "到期"]

def parse_intent(text: str):
    # 清理 Slack 可能加的 Markdown 標記
    cleaned = text.strip("*_`")
    text_lower = cleaned.lower()
    print("DEBUG cleaned text:", text_lower)

    # --- 強制規則：Email ---
    m = EMAIL_RE.search(text or "")
    if m:
        email = m.group(0)
        intent = _forced_email_intent(email)
        try:
            print("DEBUG intent (forced email):", intent)
        except Exception:
            pass
        return intent

    # --- 強制規則 ---
    if re.search(r"(license|licenses|授權|到期)", text_lower):
        days = 30
        match = re.search(r"(\d+)", text_lower)
        if match:
            days = int(match.group(1))
        intent = {
            "intent": "license_expiry",
            "days": days,
            "fields": ["asset_name", "ain", "serial_number", "purchased_on", "assigned_to_user_name"],
        }
        print("DEBUG intent (forced license):", intent)
        return intent

    # --- 強制規則 for location ---
    loc_match = re.search(r"\b([A-Z]{2})\b", text_upper := cleaned.upper())
    if ("device" in text_lower or "設備" in text_lower) and loc_match:
        loc = loc_match.group(1)
        intent = {
            "intent": "location_assets",
            "location": loc,
            "fields": ["asset_name", "ain", "serial_number", "purchased_on", "assigned_to_user_name"],
        }
        print("DEBUG intent (forced location):", intent)
        return intent

    # --- 需要 GPT 的情況才初始化 client ---
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("⚠️ WARNING: OPENAI_API_KEY not set, fallback to user_or_asset_lookup")
        return {
            "intent": "user_or_asset_lookup",
            "query": text,
            "fields": ["asset_name", "ain", "serial_number", "purchased_on", "assigned_to_user_name"],
        }

    client = OpenAI(api_key=api_key)

    system_prompt = """You are an intent parser for an IT asset management bot.
The user may type queries in Chinese, English, or mixed.
Always normalize into structured JSON in English.

Supported intents:
- user_or_asset_lookup
- license_expiry
- old_laptops
- location_assets
- group_assets
- vendor_assets
- age_assets

Fields you may extract:
- query: for user_or_asset_lookup
- days: for license_expiry (integer)
- years: for old_laptops / age_assets (integer)
- location: for location_assets
- group: for group_assets (Mac/Windows)
- vendor: for vendor_assets
- fields: list of requested fields

Rules:
1. Always return valid JSON only.
2. Default fields = ["asset_name","ain","serial_number","purchased_on","assigned_to_user_name"].
3. If parsing fails, fallback to {"intent":"user_or_asset_lookup","query":<text>}.
"""

    user_prompt = f"User query: {text}\nReturn intent JSON only."

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )
        intent = json.loads(response.choices[0].message.content.strip())
    except Exception as e:
        print("DEBUG intent (GPT error):", e)
        intent = {
            "intent": "user_or_asset_lookup",
            "query": text,
            "fields": ["asset_name", "ain", "serial_number", "purchased_on", "assigned_to_user_name"],
        }

    print("DEBUG intent (GPT):", intent)
    return intent