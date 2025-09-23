from typing import List, Dict
import csv
import tempfile
import os
from datetime import datetime


def _write_csv(headers: List[str], rows: List[List[str]], prefix="report"):
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=".csv")
    os.close(fd)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    return path


def format_assets_list(title: str, assets: List[Dict], fields=None):
    default_fields = ["asset_name", "ain", "serial_number", "purchased_on", "assigned_to_user_name"]
    fields = fields or default_fields
    count = len(assets or [])
    header = {"type": "section", "text": {"type": "mrkdwn", "text": f"*{title}* (found: {count})"}}

    if not assets:
        return [header, {"type": "section", "text": {"type": "mrkdwn", "text": "No assets found."}}], None

    rows = []
    for a in assets:
        row = []
        if "asset_name" in fields:
            row.append(a.get("name"))
        if "ain" in fields:
            row.append(a.get("identifier"))
        if "serial_number" in fields:
            row.append(a.get("bios_serial_number"))
        if "purchased_on" in fields:
            row.append(a.get("purchased_on"))
        if "location" in fields:
            row.append(a.get("location_name"))
        if "vendor" in fields:
            row.append(a.get("manufacturer"))
        if "assigned_to_user_name" in fields or "assigned_to_user_email" in fields:
            row.append(a.get("assigned_to_user_name"))
            row.append(a.get("assigned_to_user_email"))
        rows.append(row)

    if count > 10:  # 超過10筆才產生 CSV
        csv_path = _write_csv(fields, rows, prefix="assets")
        blocks = [
            header,
            {"type": "section", "text": {"type": "mrkdwn", "text": "⚠️ Too many results. CSV uploaded (no preview)."}}
        ]
        return blocks, csv_path

    # <=10 筆 → 直接顯示在 Slack，不產生 CSV
    blocks = [header, {"type": "divider"}]
    for a in assets:
        desc_parts = []
        if "asset_name" in fields:
            desc_parts.append(f"*Asset Name*: {a.get('name') or '-'}")
        if "ain" in fields:
            desc_parts.append(f"*AIN*: {a.get('identifier') or '-'}")
        if "serial_number" in fields:
            desc_parts.append(f"*Serial Number*: {a.get('bios_serial_number') or '-'}")
        if "purchased_on" in fields:
            desc_parts.append(f"*Purchased On*: {a.get('purchased_on') or '-'}")
        if "location" in fields:
            desc_parts.append(f"*Location*: {a.get('location_name') or '-'}")
        if "vendor" in fields:
            desc_parts.append(f"*Vendor*: {a.get('manufacturer') or '-'}")
        if "assigned_to_user_name" in fields or "assigned_to_user_email" in fields:
            desc_parts.append(
                f"*Assigned To*: {a.get('assigned_to_user_name') or '-'} ({a.get('assigned_to_user_email') or '-'})"
            )
        desc = "\n".join(desc_parts)
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": desc}})
        blocks.append({"type": "divider"})
    return blocks, None


def format_licenses_expiring(days: int, items: List[Dict]):
    count = len(items or [])
    header = {"type": "section", "text": {"type": "mrkdwn", "text": f":warning: *{count} licenses expiring within {days} days*"}}

    if not items:
        return [header, {"type": "section", "text": {"type": "mrkdwn", "text": "No expiring licenses."}}], None

    today = datetime.utcnow().date()
    rows = []
    for lic in items:
        expiry_str = lic.get("expires_on")
        expiry = None
        try:
            if expiry_str:
                expiry = datetime.fromisoformat(expiry_str).date()
        except Exception:
            pass
        remain = (expiry - today).days if expiry else None
        rows.append([lic.get("name"), expiry_str, remain if remain is not None else ""])

    if count > 10:  # 超過10筆才產生 CSV
        csv_path = _write_csv(["License Name", "Expires On", "Days Remaining"], rows, prefix="licenses")
        blocks = [
            header,
            {"type": "section", "text": {"type": "mrkdwn", "text": "⚠️ Too many results. CSV uploaded (no preview)."}}
        ]
        return blocks, csv_path

    # <=10 筆 → 直接顯示在 Slack
    blocks = [header, {"type": "divider"}]
    for lic in items:
        expiry_str = lic.get("expires_on")
        expiry = None
        try:
            if expiry_str:
                expiry = datetime.fromisoformat(expiry_str).date()
        except Exception:
            pass
        remain = (expiry - today).days if expiry else None
        desc_parts = [
            f"*License*: {lic.get('name') or '-'}",
            f"*Expires On*: {expiry_str or '-'}",
        ]
        if remain is not None:
            desc_parts.append(f"*Days Remaining*: {remain} days")
        desc = "\n".join(desc_parts)
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": desc}})
        blocks.append({"type": "divider"})
    return blocks, None