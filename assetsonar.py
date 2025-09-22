# assetsonar.py
import os
import requests
from urllib.parse import urlencode
from datetime import datetime, timedelta
from dateutil import parser as dtparser

AS_SECRET = os.getenv("AS_SECRET_KEY")
AS_SUBDOMAIN = os.getenv("AS_SUBDOMAIN")
BASE_URL = f"https://{AS_SUBDOMAIN}.ezofficeinventory.com/api/v1"

HEADERS = {"Authorization": f"Token token={AS_SECRET}"}

# ---- 基本呼叫 ----
def _get(path, params=None):
    url = f"{BASE_URL}{path}"
    r = requests.get(url, headers=HEADERS, params=params or {}, timeout=20)
    r.raise_for_status()
    return r.json()

# ---- Users ----
def search_users(query: str):
    # 依租戶而異，/users 支援 search 通常可行
    return _get("/users", params={"search": query})

# ---- Assets ----
def search_assets(query: str):
    # 可搜尋 AIN、序號、資產名等（取決於實際設定）
    return _get("/assets", params={"search": query})

def assets_by_user_id(user_id: int):
    # 有些租戶用 assigned_to / assigned_to_id，若失敗請改成對應參數
    return _get("/assets", params={"assigned_to": user_id})

# ---- Licenses ----
def list_licenses():
    return _get("/licenses")

# ---- Helper：解析日期欄位（不同租戶可能 key 名不同）----
def parse_date(value):
    if not value:
        return None
    try:
        return dtparser.parse(value).date()
    except Exception:
        return None

# ---- 業務邏輯查詢 ----

def find_user_assets(query: str):
    """優先以人（姓名/email）找 user → 再取其資產；若找不到，改以資產/序號/AIN 搜尋。"""
    users = search_users(query)
    if isinstance(users, list) and users:
        user = users[0]
        uid = user.get("id")
        assets = assets_by_user_id(uid)
        return {
            "user": user,
            "assets": assets or []
        }

    # fallback：直接搜資產
    assets = search_assets(query)
    return {
        "user": None,
        "assets": assets or []
    }


def licenses_expiring_within(days: int = 30):
    items = list_licenses() or []
    today = datetime.utcnow().date()
    cutoff = today + timedelta(days=days)

    results = []
    for lic in items:
        # 嘗試多個可能的鍵名
        expiry = lic.get("expiry_date") or lic.get("expires_on") or lic.get("end_date")
        d = parse_date(expiry)
        if d and d <= cutoff:
            results.append({
                "name": lic.get("name") or lic.get("title") or lic.get("product_name") or "(unknown)",
                "expires_on": d.isoformat(),
                "raw": lic
            })
    return sorted(results, key=lambda x: x["expires_on"])  # 依到期日排序


def laptops_older_than(years: int = 3):
    # 先抓所有資產再在本地過濾（若清單很大可改分頁或用分類 ID）
    assets = _get("/assets")
    cutoff = datetime.utcnow().date().replace(year=datetime.utcnow().year - years)

    results = []
    for a in assets or []:
        # 嘗試抓常見欄位：分類/類型/標籤中含 Laptop 的
        name = a.get("name") or ""
        category = (a.get("category") or {}).get("name") if isinstance(a.get("category"), dict) else a.get("category")
        is_laptopish = any(
            s for s in [str(category), name, a.get("asset_type"), a.get("asset_class")] if s and "laptop" in str(s).lower()
        )

        # 購買日期
        pd = parse_date(a.get("purchase_date") or a.get("purchased_on") or a.get("acquired_on"))
        if pd and is_laptopish and pd <= cutoff:
            results.append({
                "name": name,
                "serial": a.get("serial_number") or a.get("serial") or a.get("sn"),
                "purchased_on": pd.isoformat(),
                "ain": a.get("asset_number") or a.get("ain") or a.get("tag") or a.get("id"),
                "raw": a
            })
    return results