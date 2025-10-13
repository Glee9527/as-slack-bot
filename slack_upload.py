import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
client = WebClient(token=SLACK_BOT_TOKEN)


def upload_csv_to_slack(file_path: str, channels: str, title="Report CSV", thread_ts=None):
    """
    上傳 CSV 到 Slack，但不顯示預覽，只回傳 permalink
    """
    try:
        response = client.files_upload_v2(
            channels=[channels],
            file=file_path,
            title=title,
            thread_ts=thread_ts
        )
        file_info = response.get("file", {})
        return file_info.get("permalink")
    except SlackApiError as e:
        print(f"❌ Slack 上傳失敗: {e.response['error']}")
        return None