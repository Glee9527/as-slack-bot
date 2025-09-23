import requests, os
from datetime import datetime, timedelta

AS_SECRET = os.getenv("AS_SECRET_KEY")
AS_SUBDOMAIN = os.getenv("AS_SUBDOMAIN")
BASE_URL = f"https://{AS_SUBDOMAIN}.assetsonar.com"
HEADERS = {"Authorization": f"token {AS_SECRET}"}

today = datetime.utcnow().date()
cutoff = today + timedelta(days=30)

statuses = ["expiring_in", "expiry_in", "expiring"]
param_vals = [
    "30",
    f"{today.isoformat()}~{cutoff.isoformat()}",
    cutoff.isoformat(),
]

for status in statuses:
    for val in param_vals:
        url = f"{BASE_URL}/software_licenses/filter.api"
        print(f"\n=== Trying status={status}, filter_param_val={val} (GET) ===")
        r = requests.get(url, headers=HEADERS, params={
            "status": status,
            "filter_param_val": val,
            "page": 1,
            "include_custom_fields": "true"
        })
        print("Status:", r.status_code, "Body:", r.text[:200])

        print(f"=== Trying status={status}, filter_param_val={val} (POST) ===")
        r = requests.post(url, headers=HEADERS, data={
            "status": status,
            "filter_param_val": val,
            "page": 1,
            "include_custom_fields": "true"
        })
        print("Status:", r.status_code, "Body:", r.text[:200])