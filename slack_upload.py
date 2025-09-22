# slack_upload.py
import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
client = WebClient(token=SLACK_BOT_TOKEN)


def upload_csv_to_slack(file_path: str, channels: str, title="Report CSV", thread_ts=None):
    """
    上傳 CSV 到 Slack
    :param file_path: 本地 CSV 檔案路徑
    :param channels: Slack channel id（可從 command body["channel_id"] 拿到）
    :param title: 檔案標題
    :param thread_ts: 如果要回覆在同一個 thread，可以傳 thread_ts
    """
    try:
        response = client.files_upload_v2(
            channel=channels,
            file=file_path,
            title=title,
            thread_ts=thread_ts
        )
        return response
    except SlackApiError as e:
        print(f"Slack 上傳失敗: {e.response['error']}")
        return None