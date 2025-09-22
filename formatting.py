# formatting.py
from typing import Dict, List
import csv
import tempfile
import os


def _pair(label, value):
    """格式化一行文字，處理空值"""
    return f"*{label}*：{value if value else '-'}"


def _write_csv(headers: List[str], rows: List[List[str]], prefix="report"):
    """生成臨時 CSV 檔案，回傳檔案路徑"""
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=".csv")
    os.close(fd)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    return path


# ---------------------------
# 使用者 / 資產查詢
# ---------------------------
def format_user_assets(query: str, data: Dict):
    user = data.get("user")
    assets = data.get("assets") or []

    header = {
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"查詢：`{query}`"}
    }

    if user:
        uname = user.get("name") or user.get("full_name") or user.get("email")
        ublock = {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"👤 *User Name*：{uname}"}
        }
    else:
        ublock = {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "未找到對應使用者，改以資產匹配。"}
        }

    if not assets:
        return [header, ublock, {"type": "section", "text": {"type": "mrkdwn", "text": "找不到資產。"}}], None

    blocks = [header, ublock, {"type": "divider"}]

    rows = []
    for a in assets[:10]:  # 最多列 10 筆
        name = a.get("name")
        serial = a.get("serial_number") or a.get("serial")
        pd = a.get("purchase_date") or a.get("purchased_on")
        ain = a.get("asset_number") or a.get("ain") or a.get("tag") or a.get("id")

        desc = "\n".join([
            _pair("💻 Asset Name", name),
            _pair("🔑 Serial Number", serial),
            _pair("📅 Purchased On", pd),
            _pair("🏷️ AIN", ain),
        ])

        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": desc}})
        blocks.append({"type": "divider"})

        rows.append([name, serial, pd, ain])

    csv_path = _write_csv(["Asset Name", "Serial Number", "Purchased On", "AIN"], rows, prefix="assets")
    return blocks, csv_path


# ---------------------------
# License 到期清單
# ---------------------------
def format_licenses_expiring(days: int, items: List[Dict]):
    header = {"type": "section", "text": {"type": "mrkdwn", "text": f"⚠️ *以下 License 將於 {days} 天內到期*"}}

    if not items:
        return [header, {"type": "section", "text": {"type": "mrkdwn", "text": "沒有快到期的 license。"}}], None

    blocks = [header, {"type": "divider"}]

    rows = []
    for lic in items[:20]:
        name = lic.get("name")
        exp = lic.get("expires_on")
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"• *{name}*（到期日：{exp})"}
        })
        rows.append([name, exp])

    csv_path = _write_csv(["License Name", "Expires On"], rows, prefix="licenses")
    return blocks, csv_path


# ---------------------------
# 老舊筆電清單
# ---------------------------
def format_old_laptops(years: int, items: List[Dict]):
    header = {"type": "section", "text": {"type": "mrkdwn", "text": f"🖥️ *以下筆電已超過 {years} 年*"}}

    if not items:
        return [header, {"type": "section", "text": {"type": "mrkdwn", "text": "沒有符合條件的筆電。"}}], None

    blocks = [header, {"type": "divider"}]

    rows = []
    for a in items[:20]:
        name = a.get("name")
        sn = a.get("serial")
        pd = a.get("purchased_on") or a.get("purchased_date") or a.get("purchase_date")
        ain = a.get("ain")
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"• *{name}* — Serial: `{sn}`，購買日：{pd}，AIN：`{ain}`"}
        })
        rows.append([name, sn, pd, ain])

    csv_path = _write_csv(["Asset Name", "Serial Number", "Purchased On", "AIN"], rows, prefix="old_laptops")
    return blocks, csv_path