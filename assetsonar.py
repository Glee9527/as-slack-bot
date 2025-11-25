print("DEBUG assetsonar.py loaded from:", __file__)

import os
import re
import time
import requests
from datetime import datetime, timedelta
from dateutil import parser as dtparser
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

AS_SECRET = os.getenv("AS_SECRET_KEY")
AS_SUBDOMAIN = os.getenv("AS_SUBDOMAIN", "shopback")
BASE_URL = f"https://{AS_SUBDOMAIN}.assetsonar.com"
HEADERS = {"token": AS_SECRET or "65c020957ea3152a3267ec4b30240192"}

PAGE_SIZE = 25
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# --- Session setup with retry and timeout ---
_session = requests.Session()
_session.mount("https://", HTTPAdapter(max_retries=Retry(
    total=3, connect=3, read=3,
    backoff_factor=0.4,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=("GET", "POST", "PUT", "PATCH")
)))
DEFAULT_TIMEOUT = (5, 20)

def _get(path, params=None):
    url = f"{BASE_URL}/{path}"
    r = _session.get(url, headers=HEADERS, params=params or {}, timeout=DEFAULT_TIMEOUT)
    if r.status_code == 429:
        retry_after = int(r.headers.get("Retry-After", "60"))
        time.sleep(min(retry_after, 120))
        r = _session.get(url, headers=HEADERS, params=params or {}, timeout=DEFAULT_TIMEOUT)
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

# --- New: Use AssetSonar server filters for faster email search ---
def get_member_by_email(email: str):
    """Fetch member record by email."""
    params = {"page": 1, "filter": "email", "filter_val": email}
    data = _get("members.api", params=params)
    if isinstance(data, list) and data:
        for m in data:
            if str(m.get("email", "")).lower() == email.lower():
                return m
        return data[0]
    return None

def get_assets_possessions_of_user(user_id: int, include_custom_fields=False, max_pages=10):
    """Use assets/filter.api possessions_of to list user assets quickly."""
    results = []
    page = 1
    while page <= max_pages:
        params = {
            "status": "possessions_of",
            "filter_param_val": str(user_id),
            "page": page,
        }
        if include_custom_fields:
            params["include_custom_fields"] = "true"
        data = _get("assets/filter.api", params=params)
        items = data or []
        results.extend(items)
        if len(items) < 25:
            break
        page += 1
    return results

def find_assets_by_assignee_email_fast(email: str, include_custom_fields=False, max_pages=10):
    """High-speed asset lookup via server-side filters."""
    if not EMAIL_RE.match(email or ""):
        return []
    member = get_member_by_email(email)
    if not member:
        return []
    user_id = member.get("id") or member.get("user_id")
    if not user_id:
        return []
    return get_assets_possessions_of_user(int(user_id), include_custom_fields, max_pages)

def find_user_assets(query: str, limit=200):
    """
    Search assets by user email, name, AIN, or serial.
    Email/name → server-side if possible; AIN/Serial → quick_search fallback.
    """
    query_lower = query.lower()
    is_email = "@" in query
    is_ain = re.match(r"^[A-Za-z]{2}\d{3,}$", query)
    is_serial = len(query) > 6 and query.isalnum()

    # --- Fast path for email ---
    m = EMAIL_RE.search(query)
    if m:
        email = m.group(0)
        fast_assets = find_assets_by_assignee_email_fast(email)
        if fast_assets:
            return {"user": {"name": email}, "assets": fast_assets}

    matched = []
    # Quick path for AIN/Serial
    if is_ain or is_serial:
        quick = quick_search(query)
        if quick:
            return {"user": None, "assets": quick}

    # Fallback full scan
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
    """Fetch all software licenses expiring within N days."""
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
        if count < PAGE_SIZE:
            break
        page += 1
    return sorted(results, key=lambda x: x["expires_on"])

def laptops_older_than(years: int = 3):
    """Find laptops older than N years."""
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
            if any(b in name for b in ["apple", "lenovo", "dell", "hp"]):
                if any(w in name or w in group for w in ["laptop", "notebook", "macbook", "desktop", "pc"]):
                    if pd and pd <= cutoff:
                        results.append(a)
        if page >= data.get("total_pages", 1):
            break
        page += 1
    print(f"[laptops_older_than] total matches={len(results)}")
    return results

def find_assets_by_location(location: str):
    """Find all assets in a given location (by location_name)."""
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