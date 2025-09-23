import os
import re
import requests
from datetime import datetime, timedelta
from dateutil import parser as dtparser

AS_SECRET = os.getenv("AS_SECRET_KEY")
AS_SUBDOMAIN = os.getenv("AS_SUBDOMAIN")
BASE_URL = f"https://shopback.assetsonar.com"
HEADERS = {"Authorization": f"token 65c020957ea3152a3267ec4b30240192"}

PAGE_SIZE = 25  # AssetSonar 預設一頁 25 筆


def _get(path, params=None):
    """Generic GET wrapper for AssetSonar API"""
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


# ---------------------------
# User / Asset 搜尋
# ---------------------------
def find_user_assets(query: str, limit=200):
    """
    Search assets by user email, name, AIN (identifier), or serial number.
    Auto-paginates through ALL assets and returns all matches.
    """
    page = 1
    matched = []
    query_lower = query.lower()

    # 判斷 query 類型
    is_email = "@" in query
    is_ain = re.match(r"^[A-Za-z]{2}\d{3,}$", query)  # e.g. TW0237
    is_serial = len(query) > 6 and query.isalnum()

    while True:
        data = _get("assets.api", params={"page": page, "limit": limit})
        assets = data.get("assets", [])
        if not assets:
            break

        for a in assets:
            fields = [
                a.get("identifier"),              # AIN
                a.get("bios_serial_number"),      # Serial
                a.get("assigned_to_user_name"),   # User name
                a.get("assigned_to_user_email"),  # User email
            ]
            if any(query_lower in str(f).lower() for f in fields if f):
                matched.append(a)

        # 翻頁直到最後一頁
        if page >= data.get("total_pages", 1):
            break
        page += 1

    if matched:
        if is_email or (not is_ain and not is_serial):
            return {"user": {"name": query}, "assets": matched}
        else:
            return {"user": None, "assets": matched}

    return {"user": None, "assets": []}


# ---------------------------
# Licenses Expiring Soon (multi-page)
# ---------------------------
def licenses_expiring_within(days: int = 30):
    """
    Fetch ALL software licenses expiring within N days.
    Robust pagination: keep requesting until API returns 0 items
    """
    today = datetime.utcnow().date()
    cutoff = today + timedelta(days=days)
    results = []
    seen_ids = set()
    page = 1

    while True:
        try:
            params = {
                "status": "expiring_in",
                "filter_param_val": str(days),
                "page": page,
                "limit": 200,
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

                expiry_raw = (
                    lic.get("end_date")
                    or lic.get("expiry_date")
                    or lic.get("expires_on")
                    or lic.get("software_license_end_date")
                )
                d = parse_date(expiry_raw)

                if d and d <= cutoff:
                    results.append({
                        "name": lic.get("name")
                                or lic.get("software_name")
                                or lic.get("title")
                                or "(unknown)",
                        "expires_on": d.isoformat(),
                        "vendor": lic.get("vendor_name") or lic.get("vendor") or "",
                        "license_key": lic.get("license_key") or "",
                        "license_id": lic_id,
                    })

            # 判斷是否繼續翻頁
            total_pages = (
                data.get("total_pages")
                or data.get("total_pages_count")
                or data.get("pages")
                or data.get("total_pages_no")
            )
            if isinstance(total_pages, int) and page >= total_pages:
                break

            if count < PAGE_SIZE:
                break

            page += 1

        except Exception as e:
            print(f"License API page={page} error: {e}")
            break

    results.sort(key=lambda x: x["expires_on"])
    return results