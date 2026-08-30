import json
import requests
from datetime import datetime
import os

# ── 설정 ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = ""   # BotFather 토큰 (나중에 입력)
TELEGRAM_CHAT_ID = ""   # chat_id (나중에 입력)

SCREENER_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screener_result.json")
WATCHLIST_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlist.json")
# ────────────────────────────────────────────────────────────────────────────


def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("\n[텔레그램 미설정 — 콘솔 출력]\n")
        print(text)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML"
        }, timeout=10)
        r.raise_for_status()
        print("텔레그램 전송 완료")
    except Exception as e:
        print(f"텔레그램 전송 실패: {e}")
        print(text)


def get_chat_id():
    """봇에게 /start 메시지 보낸 후 이 함수 실행 → chat_id 출력"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    r = requests.get(url, timeout=10)
    for u in r.json().get("result", []):
        chat = u.get("message", {}).get("chat", {})
        print(f"chat_id: {chat.get('id')}  |  이름: {chat.get('first_name')}")


def get_current_price(code):
    """네이버 금융 API로 현재가 조회 (장중 실시간 반영)"""
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
    if gap >= peak: return "over"
    if gap >= avg:  return "warn"
    return "up"


def fmt_cap(v):
    if not v or v <= 0: return "—"
    if v >= 1e12: return f"{v/1e12:.1f}조"
    if v >= 1e8:  return f"{round(v/1e8)}억"
    return f"{round(v/1e4)}만"


# ── 보유/관심종목 알림 ──────────────────────────────────────────────────────
def run_watchlist_alert(screener_map, now_str, title_suffix):
    if not os.path.exists(WATCHLIST_FILE):
        send_telegram("⚠️ watchlist.json 없음. portfolio 페이지에서 '알림봇 동기화' 버튼을 눌러주세요.")
        return

    with open(WATCHLIST_FILE, encoding="utf-8") as f:
        wl = json.load(f)
    hold_codes  = wl.get("hold", [])
    watch_codes = wl.get("watch", [])
    all_codes   = list(dict.fromkeys(hold_codes + watch_codes))

    print(f"  보유/관심 {len(all_codes)}개 조회 중...")

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
        if current_price is None:
            rows.append({"tag": tag, "name": name, "price": None,
                         "gap": None, "peak": prev_peak, "avg": avg50, "heat": None})
            continue

        if not ma10 or ma10 == 0:
            continue

        gap  = round((current_price - ma10) / ma10 * 100, 1)
        heat = heat_label(gap, avg50, prev_peak)

        rows.append({"tag": tag, "name": name, "price": current_price,
                     "gap": gap, "peak": prev_peak, "avg": avg50, "heat": heat})

    if not rows:
        return

    heat_order = {"over": 0, "warn": 1, "up": 2, None: 3}
    hold_rows  = sorted([r for r in rows if r["tag"] == "📦"],
                        key=lambda x: (heat_order[x["heat"]], -(x["gap"] or -999)))
    watch_rows = sorted([r for r in rows if r["tag"] == "👀"],
                        key=lambda x: (heat_order[x["heat"]], -(x["gap"] or -999)))

    def fmt_row(r):
        gap_str   = f"{r['gap']:+.1f}%"  if r["gap"]  is not None else "—"
        peak_str  = f"{r['peak']:+.1f}%" if r["peak"] is not None else "—"
        avg_str   = f"{r['avg']:+.1f}%"  if r["avg"]  is not None else "—"
        price_str = f"{r['price']:,}원"  if r["price"] else "—"

        if r["heat"] == "over":
            detail = f"역대최고 {peak_str} 돌파"
        elif r["heat"] == "warn":
            detail = f"평균 {avg_str} 초과, 최고 {peak_str} 미달"
        elif r["heat"] == "up":
            detail = f"평균 {avg_str} 미달, 최고 {peak_str}"
        else:
            detail = "정배열 아님 / 기준 없음"

        if r["price"]:
            return f"{r['name']}\n현재가 {price_str}  |  10주괴리율 {gap_str}\n{detail}"
        return f"{r['name']}\n{detail}"

    def fmt_section(rows_list):
        buckets = {"over": [], "warn": [], "up": [], None: []}
        for r in rows_list:
            buckets[r["heat"]].append(r)
        parts = []
        if buckets["over"]:
            parts.append("과열🔥\n" + "\n\n".join(fmt_row(r) for r in buckets["over"]))
        if buckets["warn"]:
            parts.append("과열주의⚠️\n" + "\n\n".join(fmt_row(r) for r in buckets["warn"]))
        if buckets["up"]:
            parts.append("상승중📈\n" + "\n\n".join(fmt_row(r) for r in buckets["up"]))
        if buckets[None]:
            parts.append("기준없음➖\n" + "\n\n".join(fmt_row(r) for r in buckets[None]))
        return "\n\n".join(parts)

    lines = [f"📊 보유/관심종목 현황  ({now_str} · {title_suffix})"]
    if hold_rows:
        lines.append("\n━━━━━━━━━━━━━━━━\n보유종목📦\n")
        lines.append(fmt_section(hold_rows))
    if watch_rows:
        lines.append("\n━━━━━━━━━━━━━━━━\n관심종목👀\n")
        lines.append(fmt_section(watch_rows))

    send_telegram("\n".join(lines))


# ── 15:30 전용 — 최초정배열 종목 알림 ─────────────────────────────────────
def run_first_align_alert(screener_map, now_str):
    stocks = list(screener_map.values())

    # 전체정배열 + 시총 1000억 이상 + 최초정배열
    first_fa = [
        d for d in stocks
        if d.get("first_full_align")
        and d.get("market_cap", 0) >= 100_000_000_000
    ]
    # 시총 내림차순
    first_fa.sort(key=lambda x: -x.get("market_cap", 0))

    if not first_fa:
        send_telegram(f"🌙 [{now_str} 장마감] 오늘 최초정배열 진입 종목 없음 (시총 1000억 이상 기준)")
        return

    lines = [f"🌙 [{now_str} 장마감] 최초정배열 진입 종목  ({len(first_fa)}개)"]
    lines.append("시총 1000억 이상 · 시총 내림차순\n")

    for d in first_fa:
        gap_str  = f"{d['ma10gap']:+.1f}%"          if d.get("ma10gap")      is not None else "—"
        peak_str = f"{d['prev_peak_gap']:+.1f}%"    if d.get("prev_peak_gap") is not None else "—"
        avg_str  = f"{d['align_avg50']:+.1f}%"      if d.get("align_avg50")   is not None else "—"
        cap_str  = fmt_cap(d.get("market_cap", 0))
        mkt      = d.get("market", "")

        # 과열 상태 표시
        heat = heat_label(d.get("ma10gap"), d.get("align_avg50"), d.get("prev_peak_gap"))
        if heat == "over":   heat_txt = "🔥과열"
        elif heat == "warn": heat_txt = "⚠️과열주의"
        elif heat == "up":   heat_txt = "📈상승중"
        else:                heat_txt = "➖"

        lines.append(
            f"{heat_txt}  {d['name']} ({mkt} · {cap_str})\n"
            f"10주괴리율 {gap_str}  |  평균 {avg_str}  |  최고 {peak_str}"
        )

    send_telegram("\n\n".join(lines))


# ── 메인 ───────────────────────────────────────────────────────────────────
def run_alert():
    now = datetime.now()
    now_str      = now.strftime("%H:%M")
    is_closed    = (now.hour > 15) or (now.hour == 15 and now.minute >= 30)
    title_suffix = "장마감" if is_closed else "장중"

    if not os.path.exists(SCREENER_FILE):
        send_telegram("⚠️ screener_result.json 없음. 스크리너를 먼저 실행하세요.")
        return

    with open(SCREENER_FILE, encoding="utf-8") as f:
        raw = json.load(f)
    screener_map = {d["code"]: d for d in (raw.get("stocks") or raw)}

    print(f"[{now_str}] 알림 실행 (장마감={is_closed})")

    # 1. 보유/관심종목 알림 — 매 회 공통
    run_watchlist_alert(screener_map, now_str, title_suffix)

    # 2. 최초정배열 알림 — 15:30 장마감 회차만
    if is_closed:
        run_first_align_alert(screener_map, now_str)


if __name__ == "__main__":
    # chat_id 확인이 필요할 때만 주석 해제:
    # get_chat_id()
    run_alert()
