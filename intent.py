# intent.py
import os
import re
from typing import Dict, Any

USE_GPT = bool(os.getenv("OPENAI_API_KEY"))

# --- 規則解析 ---

def parse_intent_rules(text: str) -> Dict[str, Any]:
    t = text.strip().lower()

    # license expiry
    if any(k in t for k in ["license", "licence", "到期", "過期", "expire", "expiring"]):
        # 抽出天數（30, 60... 支援中文/英文）
        m = re.search(r"(\d+)[\s\-]*(day|days|天)", t)
        days = int(m.group(1)) if m else 30
        return {"intent": "license_expiry", "days": days}

    # old laptops
    if any(k in t for k in ["laptop", "notebook", "筆電", "電腦"]):
        m = re.search(r"(\d+)\s*(year|years|年)", t)
        years = int(m.group(1)) if m else 3
        if any(k in t for k in ["old", "over", "older", "超過", ">", "大於"]):
            return {"intent": "old_laptops", "years": years}

    # default: user or asset lookup
    return {"intent": "user_or_asset_lookup", "query": text.strip()}

# --- （可選）GPT 解析：當規則不確定時強化 ---

def parse_intent_gpt(text: str) -> Dict[str, Any]:
    if not USE_GPT:
        return parse_intent_rules(text)

    try:
        from openai import OpenAI
        client = OpenAI()
        sys = (
            "Extract a JSON with keys: intent(one of: license_expiry, old_laptops, user_or_asset_lookup), "
            "days(optional), years(optional), query(optional). The user may speak Chinese or English."
        )
        msg = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": text}
            ],
            temperature=0
        )
        content = msg.choices[0].message.content
        # 嘗試提取 JSON（為簡化起見，假設模型直接回 JSON）
        import json
        data = json.loads(content)
        return data
    except Exception:
        return parse_intent_rules(text)


def parse_intent(text: str) -> Dict[str, Any]:
    # 先規則 → 再 GPT（可選）
    base = parse_intent_rules(text)
    if base.get("intent") == "user_or_asset_lookup" and USE_GPT:
        g = parse_intent_gpt(text)
        # 若 GPT 判斷出別的意圖就採用
        if g.get("intent") != "user_or_asset_lookup":
            return g
    return base