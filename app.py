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

# Load environment variables
load_dotenv()

# Initialize Slack + Flask
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

    if not text:
        client.chat_postEphemeral(
            channel=channel_id,
            user=body.get("user_id"),
            text="Please enter a query, e.g. `/asset George Li` or `assets older than 3 years`"
        )
        return

    # Step 1: post "Searching..." message (root of thread)
    searching_msg = client.chat_postMessage(
        channel=channel_id,
        text=":mag: Searching, please wait..."
    )
    thread_ts = searching_msg["ts"]

    try:
        intent_data = intent.parse_intent(text)
        itype = intent_data.get("intent")
        fields = intent_data.get("fields")
        print("DEBUG intent detected:", json.dumps(intent_data, ensure_ascii=False))

        blocks, csv_path = None, None

        if itype == "user_or_asset_lookup":
            q = intent_data.get("query")
            data = AS.find_user_assets(q)
            blocks, csv_path = FX.format_assets_list(f"Results for {q}", data.get("assets", []), fields=fields)

        elif itype == "license_expiry":
            days = int(intent_data.get("days", 30))
            items = AS.licenses_expiring_within(days)
            print(f"DEBUG license_expiry: days={days}, results={len(items)}")
            blocks, csv_path = FX.format_licenses_expiring(days, items)

        elif itype == "old_laptops":
            years = int(intent_data.get("years", 3))
            items = AS.laptops_older_than(years)
            print(f"DEBUG old_laptops: years={years}, results={len(items)}")
            blocks, csv_path = FX.format_old_laptops(years, items, fields=fields)

        elif itype == "location_assets":
            loc = intent_data.get("location")
            items = AS.find_assets_by_location(loc)
            print(f"DEBUG location_assets: location={loc}, results={len(items)}")
            blocks, csv_path = FX.format_assets_list(f"Assets in location {loc}", items, fields=fields)

        elif itype == "group_assets":
            grp = intent_data.get("group")
            items = AS.find_assets_by_group(grp)
            print(f"DEBUG group_assets: group={grp}, results={len(items)}")
            blocks, csv_path = FX.format_assets_list(f"{grp.capitalize()} assets", items, fields=fields)

        elif itype == "vendor_assets":
            ven = intent_data.get("vendor")
            items = AS.find_assets_by_vendor(ven)
            print(f"DEBUG vendor_assets: vendor={ven}, results={len(items)}")
            blocks, csv_path = FX.format_assets_list(f"Assets from vendor {ven}", items, fields=fields)

        elif itype == "age_assets":
            yrs = int(intent_data.get("years", 3))
            items = AS.find_assets_by_age(yrs)
            print(f"DEBUG age_assets: years={yrs}, results={len(items)}")
            blocks, csv_path = FX.format_assets_list(f"Assets older than {yrs} years", items, fields=fields)

        else:
            print("DEBUG intent fallback → unknown intent")
            blocks = [
                {"type": "section", "text": {"type": "mrkdwn", "text": f"❓ Sorry, I could not understand: {text}"}}
            ]

        # Step 2: reply results in the same thread
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text="Search results",
            blocks=blocks
        )

        # Step 3: Upload CSV if provided
        if csv_path:
            resp = upload_csv_to_slack(csv_path, channel_id, title="Results CSV", thread_ts=thread_ts)
            if resp and "file" in resp:
                permalink = resp["file"].get("permalink")
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
    return handler.handle(request)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    flask_app.run(host="0.0.0.0", port=port)