"""发送一条测试消息到 Telegram Bot，用于验证配置是否正确。"""
from __future__ import annotations

import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.config_loader import DEFAULT_CONFIG_PATH, load_settings


CONFIG_PATH = DEFAULT_CONFIG_PATH


def load_telegram_credentials() -> tuple[str, str]:
    data = load_settings(CONFIG_PATH)
    if not data:
        raise SystemExit(f"未找到配置文件 {CONFIG_PATH}")
    telegram = data.get("telegram", {})
    bot_token = telegram.get("bot_token") or ""
    chat_id = telegram.get("chat_id") or ""
    if not bot_token or not chat_id:
        raise SystemExit("请在 config/config.yaml 中填写 telegram.bot_token 和 telegram.chat_id")
    return bot_token, chat_id


def send_test_message(bot_token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    resp = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=15)
    resp.raise_for_status()
    print("发送成功", resp.json())


def main() -> None:
    bot_token, chat_id = load_telegram_credentials()
    text = "Hello from RadarFlow test" if len(sys.argv) < 2 else " ".join(sys.argv[1:])
    send_test_message(bot_token, chat_id, text)


if __name__ == "__main__":
    main()
