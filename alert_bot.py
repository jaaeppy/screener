import json
import requests
from datetime import datetime
import FinanceDataReader as fdr
import os

# ── 설정 ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = "YOUR_BOT_TOKEN"   # BotFather에서 받은 토큰
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"     # 아래 get_chat_id() 실행 후 확인

SCREENER_FILE = os.path.join(os.path.dirname(__file__), "screener_result.json")
WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), "watchlist.json")
# ────────────────────────────────────────────────────────────────────────────


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML"
        }, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"텔레그램 전송 실패: {e}")


def get_chat_id():
    """봇에게 아무 메시지나 보낸 후 이 함수 실행하면 chat_id 출력"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    r = requests.get(url, timeout=10)
    updates = r.json().get("result", [])
    if not updates:
        print("봇에게 먼저 메시지를 보내주세요 (텔레그램에서 /start 또는 아무 텍스트)")
        return
    for u in updates:
        msg = u.get("message", {})
        chat = msg.get("chat", {})
        print(f"chat_id: {chat.get('id')}  |  from: {chat.get('first_name')}")


def get_current_price(code):
    """네이버 금융 모바일 API로 현재가 조회 (장중 실시간)"""
    try:
        url = f"https://m.stock.naver.com/api/stock/{code}/basic"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        data = r.json()
        price_str = data.get("closePrice", "").replace(",", "")
        return int(price_str) if price_str else None
    except Exception:
        return None


def heat_label(gap, avg, peak):
    if gap is None or gap <= 0 or avg is None or peak is None:
        return None
    if gap >= peak:
        return "over"
    if gap >= avg:
        return "warn"
    return "up"


def run_alert():
    now_str = datetime.now().strftime("%H:%M")
    is_market_closed = datetime.now().hour >= 15 and datetime.now().minute >= 30

    # 스크리너 결과 로드 (MA10, 최고괴리율 등)
    if not os.path.exists(SCREENER_FILE):
        send_telegram("⚠️ screener_result.json 없음. 스크리너를 먼저 실행하세요.")
        return
    with open(SCREENER_FILE, encoding="utf-8") as f:
        raw = json.load(f)
    screener_map = {d["code"]: d for d in (raw.get("stocks") or raw)}

    # 감시 종목 로드
    if not os.path.exists(WATCHLIST_FILE):
        send_telegram("⚠️ watchlist.json 없음. portfolio 페이지에서 '알림봇 동기화' 버튼을 눌러주세요.")
        return
    with open(WATCHLIST_FILE, encoding="utf-8") as f:
        wl = json.load(f)
    hold_codes  = wl.get("hold", [])
    watch_codes = wl.get("watch", [])
    all_codes   = list(dict.fromkeys(hold_codes + watch_codes))  # 순서 유지 + 중복 제거

    if not all_codes:
        send_telegram("⚠️ 감시 종목이 없습니다. portfolio 페이지에서 종목을 추가하세요.")
        return

    rows = []
    for code in all_codes:
        d = screener_map.get(code)
        if not d:
            continue

        ma10      = d.get("ma10")
        prev_peak = d.get("prev_peak_gap")
        avg50     = d.get("align_avg50")
        name      = d["name"]
        tag       = "📦" if code in hold_codes else "👀"

        current_price = get_current_price(code)
        if current_price is None or not ma10 or ma10 == 0:
            rows.append({"tag": tag, "name": name, "code": code,
                         "price": None, "gap": None, "peak": prev_peak, "avg": avg50, "heat": None})
            continue

        gap = round((current_price - ma10) / ma10 * 100, 1)
        heat = heat_label(gap, avg50, prev_peak)

        rows.append({
            "tag": tag, "name": name, "code": code,
            "price": current_price, "gap": gap,
            "peak": prev_peak, "avg": avg50, "heat": heat
        })

    # 정렬: 과열 > 과열주의 > 상승중 > 기타, 같은 레벨 내엔 괴리율 높은 순
    heat_order = {"over": 0, "warn": 1, "up": 2, None: 3}
    rows.sort(key=lambda x: (heat_order[x["heat"]], -(x["gap"] or -999)))

    # 메시지 조립
    title_suffix = "장마감" if is_market_closed else "장중"
    lines = [f"📊 <b>보유/관심종목 현황</b> ({now_str} · {title_suffix})\n"]

    for r in rows:
        gap_str  = f"{'+' if (r['gap'] or 0) >= 0 else ''}{r['gap']}%" if r["gap"] is not None else "—"
        peak_str = f"+{r['peak']}%" if r["peak"] is not None else "—"
        avg_str  = f"+{r['avg']}%"  if r["avg"]  is not None else "—"
        price_str = f"{r['price']:,}원" if r["price"] else "—"

        if r["heat"] == "over":
            icon = "🔥"
            heat_txt = f"<b>과열!</b> (역대최고 {peak_str} 초과)"
        elif r["heat"] == "warn":
            icon = "⚠️"
            heat_txt = f"과열 주의 (평균 {avg_str} 초과)"
        elif r["heat"] == "up":
            icon = "📈"
            heat_txt = "상승중"
        else:
            icon = "➖"
            heat_txt = "해당없음"

        lines.append(
            f"{r['tag']} {icon} <b>{r['name']}</b> ({r['code']})\n"
            f"  현재가 {price_str}  |  10주괴리율 {gap_str}\n"
            f"  최고 {peak_str}  |  {heat_txt}\n"
        )

    send_telegram("\n".join(lines))
    print(f"[{now_str}] 알림 전송 완료 ({len(rows)}종목)")


if __name__ == "__main__":
    # 처음 실행 시 chat_id 확인이 필요하면 아래 주석 해제:
    # get_chat_id()

    run_alert()
