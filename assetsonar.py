print("DEBUG assetsonar.py loaded from:", __file__)

import os
import re
import requests
from datetime import datetime, timedelta
from dateutil import parser as dtparser

AS_SECRET = os.getenv("AS_SECRET_KEY")
AS_SUBDOMAIN = os.getenv("AS_SUBDOMAIN")
BASE_URL = f"https://shopback.assetsonar.com"
HEADERS = {"Authorization": f"token 65c020957ea3152a3267ec4b30240192"}

PAGE_SIZE = 25


def _get(path, params=None):
    url = f"{BASE_URL}/{path}"
    r = requests.get(url, headers=HEADERS, params=params or {}, timeout=30)
    r.raise_for_status()
    return r.json()


def parse_date(value):
    if not value:
        return None
    try:
        return dtparser.parse(value).date()
    except Exception:
        return None


def quick_search(query: str):
    """Fast search by AIN/Serial using search.api"""
    try:
        data = _get("search.api", params={
            "search": query,
            "facet": "FixedAsset",
            "include_custom_fields": "true"
        })
        return data.get("assets", [])
    except Exception as e:
        print(f"Quick search error: {e}")
        return []


def find_user_assets(query: str, limit=200):
    """
    Search assets by user email, name, AIN, or serial.
    Email/name → 全分頁；AIN/Serial → 嘗試 quick_search。
    """
    query_lower = query.lower()

    is_email = "@" in query
    is_ain = re.match(r"^[A-Za-z]{2}\d{3,}$", query)  # e.g. TW0237
    is_serial = len(query) > 6 and query.isalnum()

    matched = []

    # Quick path for AIN/Serial
    if is_ain or is_serial:
        quick = quick_search(query)
        if quick:
            return {"user": None, "assets": quick}

    # Full scan for user/email
    page = 1
    while True:
        data = _get("assets.api", params={"page": page, "limit": limit})
        assets = data.get("assets", [])
        if not assets:
            break

        for a in assets:
            fields = [
                a.get("identifier"),
                a.get("bios_serial_number"),
                a.get("assigned_to_user_name"),
                a.get("assigned_to_user_email"),
            ]
            if any(query_lower in str(f).lower() for f in fields if f):
                matched.append(a)

        if page >= data.get("total_pages", 1):
            break
        page += 1

    if matched:
        if is_email:
            return {"user": {"name": query}, "assets": matched}
        else:
            return {"user": None, "assets": matched}

    return {"user": None, "assets": []}


def licenses_expiring_within(days: int = 10):
    """Fetch ALL software licenses expiring within N days."""
    today = datetime.utcnow().date()
    cutoff = today + timedelta(days=days)
    results = []
    seen_ids = set()
    page = 1

    while True:
        params = {
            "status": "expiring_in",
            "filter_param_val": str(days),
            "page": page,
            "limit": PAGE_SIZE,
            "include_custom_fields": "true",
        }
        data = _get("software_licenses/filter.api", params=params)

        items = data.get("licenses") or data.get("software_licenses") or []
        count = len(items)
        print(f"[licenses_expiring_within] page={page} items={count}")

        if count == 0:
            break

        for lic in items:
            lic_id = lic.get("license_id") or lic.get("id")
            if lic_id and lic_id in seen_ids:
                continue
            if lic_id:
                seen_ids.add(lic_id)

            expiry_raw = lic.get("end_date") or lic.get("expiry_date") or lic.get("expires_on")
            d = parse_date(expiry_raw)
            if d and d <= cutoff:
                results.append({
                    "name": lic.get("name") or lic.get("software_name") or "(unknown)",
                    "expires_on": d.isoformat(),
                    "license_id": lic_id,
                })

        # ✅ 判斷是否需要繼續翻頁：小於 PAGE_SIZE 就代表到尾了
        if count < PAGE_SIZE:
            break
        page += 1

    return sorted(results, key=lambda x: x["expires_on"])


def laptops_older_than(years: int = 3):
    """
    Find Apple/Lenovo/Dell/HP laptops older than N years (strictly by purchased_on).
    Laptop 判斷依據: asset name 或 group name 包含 laptop/notebook/macbook/desktop/pc。
    """
    cutoff = datetime.utcnow().date() - timedelta(days=365 * years)
    results = []
    page = 1

    print(f"[laptops_older_than] cutoff={cutoff} years={years}")

    while True:
        data = _get("assets.api", params={"page": page, "limit": 200})
        assets = data.get("assets", [])
        if not assets:
            break

        for a in assets:
            name = (a.get("name") or "").lower()
            group = (a.get("group_name") or "").lower()
            pd_raw = a.get("purchased_on")
            pd = parse_date(pd_raw)

            # ✅ 品牌 + 類別都符合才算 laptop
            if any(b in name for b in ["apple", "lenovo", "dell", "hp"]):
                if any(w in name or w in group for w in ["laptop", "notebook", "macbook", "desktop", "pc"]):
                    print(f"  candidate: {a.get('name')} | purchased_on={pd_raw} | parsed={pd}")
                    if pd and pd <= cutoff:
                        print(f"  ✅ MATCH: {a.get('name')} | {pd}")
                        results.append(a)

        if page >= data.get("total_pages", 1):
            break
        page += 1

    print(f"[laptops_older_than] total matches={len(results)}")
    return results
    
def find_assets_by_location(location: str):
    """
    Find all assets in a given location (by location_name).
    """
    results = []
    page = 1

    while True:
        data = _get("assets.api", params={"page": page, "limit": 200})
        assets = data.get("assets", [])
        if not assets:
            break

        for a in assets:
            loc = (a.get("location_name") or "").upper()
            if loc == location.upper():
                results.append(a)

        if page >= data.get("total_pages", 1):
            break
        page += 1

    return results
