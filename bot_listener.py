"""
야수의심장 텔레그램 봇 리스너
PC 부팅 시 백그라운드에서 상시 실행
폰에서 명령어 보내면 즉시 반응

명령어:
  /status   보유/관심종목 현황 즉시 발송
  /help     명령어 목록
"""

import time
import requests
import subprocess
import sys
import os

TELEGRAM_TOKEN   = "8946065825:AAHTo_CBNcHHiRs2zGa6O60YsMth6o0xLrE"
TELEGRAM_CHAT_ID = "348127299"
SCRIPT_DIR       = os.path.dirname(os.path.abspath(__file__))
ALERT_SCRIPT     = os.path.join(SCRIPT_DIR, "alert_bot.py")
PYTHON           = sys.executable

HELP_TEXT = (
    "야수의심장 알림봇 명령어\n\n"
    "/status — 보유/관심종목 현황 즉시 조회\n"
    "/help   — 이 메시지"
)


def send(text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
        timeout=10
    )


def run_alert():
    send("⏳ 조회 중...")
    subprocess.run([PYTHON, ALERT_SCRIPT], cwd=SCRIPT_DIR)


def main():
    print("봇 리스너 시작. /status, /help 명령 대기 중...")
    send("✅ 야수의심장 봇 리스너 시작됨")

    offset = None
    while True:
        try:
            params = {"timeout": 30, "allowed_updates": ["message"]}
            if offset:
                params["offset"] = offset

            r = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params=params, timeout=40
            )
            updates = r.json().get("result", [])

            for u in updates:
                offset = u["update_id"] + 1
                msg = u.get("message", {})

                # 본인 메시지만 처리
                if str(msg.get("chat", {}).get("id", "")) != TELEGRAM_CHAT_ID:
                    continue

                text = msg.get("text", "").strip()
                print(f"수신: {text}")

                if text == "/status":
                    run_alert()
                elif text == "/help":
                    send(HELP_TEXT)
                # 그 외 메시지는 무시

        except Exception as e:
            print(f"오류: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
