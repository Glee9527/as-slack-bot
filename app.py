# app.py
import os
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request
from dotenv import load_dotenv

from intent import parse_intent
import assetsonar as AS
import formatting as FX
from slack_upload import upload_csv_to_slack

# 載入本地開發用的 .env
load_dotenv()

# 初始化 Slack App
app = App(
    token=os.getenv("SLACK_BOT_TOKEN"),
    signing_secret=os.getenv("SLACK_SIGNING_SECRET")
)

# Flask + Slack Bolt handler
handler = SlackRequestHandler(app)
flask_app = Flask(__name__)


# Slash Command: /asset
@app.command("/asset")
def handle_asset_command(ack, body, respond, logger):
    # Slack 要求必須在 3 秒內 ack
    ack()

    text = (body.get("text") or "").strip()
    channel_id = body.get("channel_id")
    thread_ts = body.get("thread_ts")

    if not text:
        respond("請輸入查詢，例如：`/asset George Li` 或 `License will expire within 30 days`")
        return

    try:
        # 解析使用者意圖
        intent = parse_intent(text)
        itype = intent.get("intent")

        if itype == "user_or_asset_lookup":
            q = intent.get("query")
            data = AS.find_user_assets(q)
            blocks, csv_path = FX.format_user_assets(q, data)
            respond(blocks=blocks, text="查詢結果")
            if csv_path:
                upload_csv_to_slack(csv_path, channel_id, title="User Assets", thread_ts=thread_ts)

        elif itype == "license_expiry":
            days = int(intent.get("days", 30))
            items = AS.licenses_expiring_within(days)
            blocks, csv_path = FX.format_licenses_expiring(days, items)
            respond(blocks=blocks, text="License 到期清單")
            if csv_path:
                upload_csv_to_slack(csv_path, channel_id, title="License Expiry Report", thread_ts=thread_ts)

        elif itype == "old_laptops":
            years = int(intent.get("years", 3))
            items = AS.laptops_older_than(years)
            blocks, csv_path = FX.format_old_laptops(years, items)
            respond(blocks=blocks, text="老舊筆電清單")
            if csv_path:
                upload_csv_to_slack(csv_path, channel_id, title="Old Laptops Report", thread_ts=thread_ts)

        else:
            respond(f"看不懂這個請求：{text}")

    except Exception as e:
        logger.exception(e)
        respond(f"查詢失敗：{e}")


# Slack Events Endpoint (Slash Commands 也會走這裡)
@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)


# Render 啟動入口
if __name__ == "__main__":
    port = int(os.getenv("PORT", "3000"))  # Render 會自動提供 PORT
    flask_app.run(host="0.0.0.0", port=port)