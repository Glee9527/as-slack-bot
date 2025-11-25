print("DEBUG assetsonar.py loaded from:", __file__)

import os
import re
import time
import requests
from datetime import datetime, timedelta
from dateutil import parser as dtparser
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from functools import lru_cache

AS_SECRET = os.getenv("AS_SECRET_KEY")
AS_SUBDOMAIN = os.getenv("AS_SUBDOMAIN", "shopback")
BASE_URL = f"https://{AS_SUBDOMAIN}.assetsonar.com"
HEADERS = {"token": AS_SECRET or "65c020957ea3152a3267ec4b30240192"}

PAGE_SIZE = 25
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# --- Session with retry/timeout ---
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

# -------- email -> assets (fast path) --------
def get_member_by_email(email: str):
    """Fetch member record by email."""
    params = {"page": 1, "filter": "email", "filter_val": email}
    data = _get("members.api", params=params)
    members = []
    if isinstance(data, list):
        members = data
    elif isinstance(data, dict) and "members" in data:
        members = data["members"]
    if members:
        for m in members:
            if str(m.get("email", "")).lower() == email.lower():
                return m
        return members[0]
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

        # ✅ Normalize payload shape:
        # - list -> use as-is
        # - dict with "assets"/"rows"/"data" -> extract list
        # - anything else -> empty list
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("assets") or data.get("rows") or data.get("data") or []
        else:
            items = []

        # ✅ Keep only dict items to avoid `'str'.get` downstream
        items = [x for x in items if isinstance(x, dict)]

        results.extend(items)

        # pagination heuristic: stop if this page has fewer than 25 items
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
    (If you need name disambiguation, call find_assets_by_person_name().)
    """
    query_lower = query.lower()
    is_email = "@" in query
    is_ain = re.match(r"^[A-Za-z]{2}\d{3,}$", query)
    is_serial = len(query) > 6 and query.isalnum()

    # Fast path for email
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

    # Fallback full scan by fields
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

    if matched and is_email:
        return {"user": {"name": query}, "assets": matched}
    return {"user": None, "assets": matched}

# ====================== Name search + disambiguation ======================

def _norm(s: str) -> str:
    return (s or "").strip().lower()

def _tokenize_name(name: str):
    # "George Li" -> ["george", "li"]; supports multiple/ideographic spaces
    return [t for t in re.split(r"[\s\u3000]+", (name or "").strip()) if t]

def _extract_members_payload(data):
    """Accept both list and {'members': [...]} shapes."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "members" in data and isinstance(data["members"], list):
        return data["members"]
    return []

@lru_cache(maxsize=512)
def _get_all_members_pages(max_pages: int = 20, only_active: bool = True):
    """Cached retrieval of members (retry without active-filter if empty)."""
    def _fetch(only_active_flag: bool):
        people = []
        page = 1
        while page <= max_pages:
            params = {"page": page}
            if only_active_flag:
                params["filter"] = "status"
                params["filter_val"] = "active"
            data = _get("members.api", params=params)
            members = _extract_members_payload(data)
            if not members:
                break
            people.extend(members)
            if len(members) < 25:
                break
            page += 1
        return people

    people = _fetch(True if only_active else False)
    if not people and only_active:
        # Fallback: try again without status=active filter
        people = _fetch(False)
    return people

def search_members_by_name(name: str, max_pages: int = 20, only_active: bool = True):
    """
    Fuzzy search members by name.
    Priority: exact full-name match > token prefix matches > name/display_name substring > email substring.
    """
    tokens = [_norm(t) for t in _tokenize_name(name)]
    if not tokens:
        return []

    people = _get_all_members_pages(max_pages=max_pages, only_active=only_active)
    if not people:
        return []

    scored = []
    for m in people:
        first = _norm(m.get("first_name"))
        last  = _norm(m.get("last_name"))
        disp  = _norm(m.get("name") or m.get("display_name") or f"{first} {last}".strip())
        email = _norm(m.get("email"))

        # full name equality (first + last) gets highest score
        full_eq = (len(tokens) >= 2) and (
            (tokens[0] == first and tokens[1] == last) or
            (" ".join(tokens) == f"{first} {last}".strip())
        )

        score = 0
        if full_eq:
            score += 100

        for t in tokens:
            if first.startswith(t): score += 10
            if last.startswith(t):  score += 10
            if t in disp:          score += 15    # broader match on name/display_name
            if t in email:         score += 2

        if score > 0:
            scored.append((score, m))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored]

def find_assets_by_person_name(name: str, include_custom_fields: bool = False, max_pages: int = 10):
    """
    Find assets by human name:
      - If exactly one strong match (or one full-name match): fetch possessions_of.
      - Otherwise return candidates with only name & email (and id) for disambiguation.
    """
    candidates = search_members_by_name(name)
    if not candidates:
        return {"candidates": [], "assets": []}

    tokens = [_norm(t) for t in _tokenize_name(name)]

    def _is_full_eq(m):
        first = _norm(m.get("first_name"))
        last  = _norm(m.get("last_name"))
        return len(tokens) >= 2 and tokens[0] == first and tokens[1] == last

    full_matches = [m for m in candidates if _is_full_eq(m)]
    target = None
    if len(full_matches) == 1:
        target = full_matches[0]
    elif len(candidates) == 1:
        target = candidates[0]

    if target:
        uid = target.get("id") or target.get("user_id")
        assets = get_assets_possessions_of_user(int(uid), include_custom_fields=include_custom_fields, max_pages=max_pages)
        return {
            "candidates": [],
            "member": {
                "id": uid,
                "first_name": target.get("first_name"),
                "last_name": target.get("last_name"),
                "email": target.get("email"),
            },
            "assets": assets
        }

    # Return only name + email for disambiguation
    slim = [{
        "id": c.get("id") or c.get("user_id"),
        "first_name": c.get("first_name"),
        "last_name": c.get("last_name"),
        "email": c.get("email"),
    } for c in candidates[:15]]
    return {"candidates": slim, "assets": []}

# ====================== Other helpers ======================

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