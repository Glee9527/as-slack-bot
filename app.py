from dotenv import load_dotenv
load_dotenv()

import sys
sys.path.insert(0, "/Users/george.li/as-slack-bot")
import intent
print("DEBUG app.py importing intent from:", intent.__file__)

import ssl
import certifi
ssl._create_default_https_context = lambda *args, **kwargs: ssl.create_default_context(cafile=certifi.where())

import json
import os
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request
from dotenv import load_dotenv

import assetsonar as AS
import formatting as FX
from slack_upload import upload_csv_to_slack

# Load env
load_dotenv()

app = App(
    token=os.getenv("SLACK_BOT_TOKEN"),
    signing_secret=os.getenv("SLACK_SIGNING_SECRET"),
)
handler = SlackRequestHandler(app)
flask_app = Flask(__name__)


@app.command("/asset")
def handle_asset_command(ack, body, client, logger):
    ack()
    text = (body.get("text") or "").strip()
    channel_id = body.get("channel_id")

    searching_msg = client.chat_postMessage(
        channel=channel_id,
        text=":mag: Searching, please wait..."
    )
    thread_ts = searching_msg["ts"]

    try:
        # ✅ Debug 分支必須在 intent parser 之前
        if text.lower().startswith("debug olddevices"):
            from datetime import datetime, timedelta
            yrs = 3
            cutoff = datetime.utcnow().date() - timedelta(days=365 * yrs)
            all_assets = []
            page = 1
            while True:
                data = AS._get("assets.api", params={"page": page, "limit": 200})
                assets = data.get("assets", [])
                if not assets:
                    break
                all_assets.extend(assets)
                if page >= data.get("total_pages", 1):
                    break
                page += 1

            rows = []
            for a in all_assets:
                name = (a.get("name") or "")
                pd_raw = a.get("purchased_on")
                pd = AS.parse_date(pd_raw)
                if any(b in name.lower() for b in ["apple", "lenovo", "dell", "hp"]):
                    rows.append([name, pd_raw or "-", str(pd or "-"), str(cutoff)])

            if not rows:
                client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text="No candidate devices found."
                )
            else:
                csv_path = FX.write_csv(
                    ["Asset Name", "Purchased On (raw)", "Parsed", "Cutoff"],
                    rows,
                    prefix="debug_olddevices"
                )
                permalink = upload_csv_to_slack(csv_path, channel_id, title="Debug Old Devices", thread_ts=thread_ts)
                if permalink:
                    client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=thread_ts,
                        text=f"📎 Debug CSV uploaded: {permalink}"
                    )
            return

        # === 正常 intent parser 流程 ===
        intent_data = intent.parse_intent(text)
        itype = intent_data.get("intent")
        fields = intent_data.get("fields")

        blocks, csv_path = None, None

        # === 查詢分支 ===
        if itype == "user_or_asset_lookup":
            q = intent_data.get("query")
            data = AS.find_user_assets(q)
            blocks, csv_path = FX.format_assets_list(
                f"Results for your query: *{text}*",
                data.get("assets", []),
                fields=fields
            )

        elif itype == "license_expiry":
            days = int(intent_data.get("days", 30))
            items = AS.licenses_expiring_within(days)
            blocks, csv_path = FX.format_licenses_expiring(days, items)
            if blocks and len(blocks) > 0:
                blocks[0]["text"]["text"] = f"Results for your query: *{text}* (licenses expiring in {days} days)"

        elif itype == "old_laptops":
            years = int(intent_data.get("years", 3))
            items = AS.laptops_older_than(years)
            blocks, csv_path = FX.format_old_laptops(years, items, fields=fields)
            if blocks and len(blocks) > 0:
                blocks[0]["text"]["text"] = f"Results for your query: *{text}* (laptops older than {years} years)"
                
        elif itype == "location_assets":
            loc = intent_data.get("location")
            items = AS.find_assets_by_location(loc)
            print(f"DEBUG location_assets: location={loc}, results={len(items)}")
            blocks, csv_path = FX.format_assets_list(
                f"Results for your query: *{text}* (location={loc})",
                items,
                fields=fields
            )

        elif itype == "age_assets":
            yrs = int(intent_data.get("years", 3))
            items = AS.devices_older_than(yrs)
            print("DEBUG devices_older_than returned:", len(items))
            for dev in items:
                print("DEBUG match:", dev.get("name"), dev.get("purchased_on"))
            blocks, csv_path = FX.format_assets_list(
                f"Results for your query: *{text}*",
                items,
                fields=fields
            )

        else:
            blocks = [
                {"type": "section", "text": {"type": "mrkdwn", "text": f"❓ Sorry, I could not understand: {text}"}}
            ]

        # === 更新 root 訊息 ===
        client.chat_update(
            channel=channel_id,
            ts=thread_ts,
            text="✅ Search completed. See results in thread"
        )

        # === 在 thread 裡回覆結果 ===
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text="Search results",
            blocks=blocks
        )

        # === 上傳 CSV （如有需要） ===
        if csv_path:
            permalink = upload_csv_to_slack(csv_path, channel_id, title="Results CSV", thread_ts=thread_ts)
            if permalink:
                client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text=f"📎 [Download CSV here]({permalink})"
                )

    except Exception as e:
        logger.exception(e)
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=f":x: Query failed: {e}"
        )


@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    # Slack URL 驗證
    data = request.get_json(silent=True)
    if data and data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}, 200

    # 其他 Slack event 正常處理
    return handler.handle(request)

# --- Health check for Render / UptimeRobot ---
@flask_app.route("/healthz", methods=["GET"])
def healthz():
    return "ok", 200

# (可選) 根路由也回應，方便快速檢查
@flask_app.route("/", methods=["GET"])
def root():
    return "running", 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    flask_app.run(host="0.0.0.0", port=port)