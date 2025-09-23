# slack_upload.py
import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# 從環境變數讀取 Token
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")

if not SLACK_BOT_TOKEN:
    raise ValueError("❌ Missing SLACK_BOT_TOKEN environment variable")

client = WebClient(token=SLACK_BOT_TOKEN)


def upload_csv_to_slack(file_path: str, channels: str, title="Report CSV", thread_ts=None):
    try:
        response = client.files_upload_v2(
            channels=[channels],   # ← 改成 list
            file=file_path,
            title=title,
            thread_ts=thread_ts
        )
        file_info = response.get("file", {})
        print(f"✅ Uploaded CSV to Slack: {file_info.get('permalink')}")
        return response
    except SlackApiError as e:
        print(f"❌ Slack 上傳失敗: {e.response['error']}")
        return None