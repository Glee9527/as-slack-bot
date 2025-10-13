from typing import List, Dict
import csv
import tempfile
import os
from datetime import datetime
from dateutil import parser as dtparser


def parse_date(value: str):
    if not value:
        return None
    try:
        return dtparser.parse(value).date()
    except Exception:
        return None


def write_csv(headers: List[str], rows: List[List[str]], prefix="report"):
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
        if "assigned_to_user_name" in fields or "assigned_to_user_email" in fields:
            row.append(a.get("assigned_to_user_name"))
            row.append(a.get("assigned_to_user_email"))
        rows.append(row)

    if count > 10:
        csv_path = write_csv(fields, rows, prefix="assets")
        blocks = [
            header,
            {"type": "section", "text": {"type": "mrkdwn", "text": "⚠️ Too many results. CSV uploaded."}}
        ]
        return blocks, csv_path

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
        expiry = parse_date(expiry_str)
        remain = (expiry - today).days if expiry else ""
        rows.append([lic.get("name"), expiry_str, remain])

    if count > 10:
        csv_path = write_csv(["License Name", "Expires On", "Days Remaining"], rows, prefix="licenses")
        blocks = [header, {"type": "section", "text": {"type": "mrkdwn", "text": "⚠️ Too many results. CSV uploaded."}}]
        return blocks, csv_path

    blocks = [header, {"type": "divider"}]
    for lic in items:
        expiry_str = lic.get("expires_on")
        expiry = parse_date(expiry_str)
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

def format_old_laptops(years: int, items: list, fields=None):
    """
    Format laptops older than N years into Slack blocks + CSV.
    """
    title = f"Laptops older than {years} years"
    return format_assets_list(title, items, fields=fields)