import json
import requests
from datetime import datetime
import os

# ── 설정 ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = "8946065825:AAHTo_CBNcHHiRs2zGa6O60YsMth6o0xLrE"
TELEGRAM_CHAT_ID = "348127299"

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
    """네이버 금융 API로 현재가 및 일간 변동률 조회"""
    try:
        url = f"https://m.stock.naver.com/api/stock/{code}/basic"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        data = r.json()
        price_str = data.get("closePrice", "").replace(",", "")
        price = int(price_str) if price_str else None
        day_chg = data.get("fluctuationsRatio")  # 일간 등락률 (%)
        if day_chg is not None:
            day_chg = round(float(day_chg), 2)
        return price, day_chg
    except Exception:
        return None, None


def heat_label(gap, avg, peak):
    if gap is None or gap <= 0 or avg is None or peak is None:
        return None
    if gap >= peak: return "over"
    if gap >= avg:  return "warn"
    return "up"


def fmt_cap(v):
    if not v or v <= 0: return "—"
    if v >= 1e12: return f"{v/1e12:,.1f}조"
    if v >= 1e8:  return f"{round(v/1e8):,}억"
    return f"{round(v/1e4):,}만"


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

        current_price, day_chg = get_current_price(code)
        week_chg = d.get("chg")

        if current_price is None:
            rows.append({"tag": tag, "name": name, "market": d.get("market",""), "cap": d.get("market_cap",0),
                         "price": None, "day_chg": None, "week_chg": week_chg,
                         "gap": None, "peak": prev_peak, "peak_date": d.get("prev_peak_date"),
                         "avg": avg50, "heat": None})
            continue

        if not ma10 or ma10 == 0:
            continue

        gap  = round((current_price - ma10) / ma10 * 100, 1)
        heat = heat_label(gap, avg50, prev_peak)

        rows.append({"tag": tag, "name": name, "market": d.get("market",""), "cap": d.get("market_cap",0),
                     "price": current_price, "day_chg": day_chg, "week_chg": week_chg,
                     "gap": gap, "peak": prev_peak,
                     "peak_date": d.get("prev_peak_date"), "avg": avg50, "heat": heat})

    if not rows:
        return

    heat_order = {"over": 0, "warn": 1, "up": 2, None: 3}
    hold_rows  = sorted([r for r in rows if r["tag"] == "📦"],
                        key=lambda x: (heat_order[x["heat"]], -(x["gap"] or -999)))
    watch_rows = sorted([r for r in rows if r["tag"] == "👀"],
                        key=lambda x: (heat_order[x["heat"]], -(x["gap"] or -999)))

    def fmt_row(r):
        gap      = r["gap"]
        peak     = r["peak"]
        avg      = r["avg"]
        price    = r["price"]
        day_chg  = r.get("day_chg")
        week_chg = r.get("week_chg")

        gap_str   = f"{gap:+.1f}%"   if gap   is not None else "—"
        price_str = f"{price:,}원"   if price  else "—"
        day_str   = f"{day_chg:+.2f}%"  if day_chg  is not None else "—"
        week_str  = f"{week_chg:+.1f}%" if week_chg is not None else "—"
        meta      = f"{r.get('market','')} · {fmt_cap(r.get('cap',0))}"

        # 평균 라인
        if gap is not None and avg is not None:
            avg_diff = round(gap - avg, 1)
            if avg_diff >= 0:
                avg_line = f"평균 : {avg:+.1f}%(+{avg_diff:.1f}% 초과)"
            else:
                avg_line = f"평균 : {avg:+.1f}%(△{abs(avg_diff):.1f}% 미달)"
        else:
            avg_line = "평균 : —"

        # 최고 라인
        if gap is not None and peak is not None:
            peak_diff = round(gap - peak, 1)
            if peak_diff >= 0:
                peak_line = f"최고 : {peak:+.1f}%(+{peak_diff:.1f}% 돌파)"
            else:
                peak_line = f"최고 : {peak:+.1f}%(△{abs(peak_diff):.1f}% 미달)"
        else:
            peak_line = "최고 : —"

        if r["heat"] in ("over", "warn", "up"):
            detail = f"{avg_line}\n{peak_line}"
        else:
            detail = "정배열 아님 / 기준 없음"

        peak_date_line = f"\n직전최고 : {r['peak_date']}" if r.get("peak_date") and r["heat"] else ""

        if price:
            return (f"<b>{r['name']}</b> ({meta})\n"
                    f"일간 : {day_str}  |  주간 : {week_str}\n"
                    f"현재가 : {price_str}  |  10주괴리율 : {gap_str}\n"
                    f"{detail}{peak_date_line}")
        return f"<b>{r['name']}</b> ({meta})\n{detail}{peak_date_line}"

    def fmt_section(rows_list):
        buckets = {"over": [], "warn": [], "up": [], None: []}
        for r in rows_list:
            buckets[r["heat"]].append(r)
        parts = []
        # 과열/과열주의: 각 종목마다 개별 라벨
        for r in buckets["over"]:
            parts.append(f"과열🔥\n{fmt_row(r)}")
        for r in buckets["warn"]:
            parts.append(f"과열주의⚠️\n{fmt_row(r)}")
        # 상승중/기준없음: 헤더 하나
        if buckets["up"]:
            parts.append("상승중📈\n\n" + "\n\n".join(fmt_row(r) for r in buckets["up"]))
        if buckets[None]:
            parts.append("기준없음➖\n\n" + "\n\n".join(fmt_row(r) for r in buckets[None]))
        return "\n\n".join(parts)

    lines = [f"📊 보유/관심종목 현황  ({now_str} · {title_suffix})"]
    if hold_rows:
        lines.append("\n━━━━━━━━━━━━━━━━\n보유종목📦\n")
        lines.append(fmt_section(hold_rows))
    if watch_rows:
        lines.append("\n━━━━━━━━━━━━━━━━\n관심종목👀\n")
        lines.append(fmt_section(watch_rows))

    send_telegram("\n".join(lines))


# ── 금요일 장마감 전용 — 최초정배열 종목 알림 ────────────────────────────
def _lock_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".first_align_sent")

def first_align_already_sent():
    path = _lock_path()
    if not os.path.exists(path):
        return False
    with open(path) as f:
        return f.read().strip() == datetime.now().strftime("%Y-%m-%d")

def mark_first_align_sent():
    with open(_lock_path(), "w") as f:
        f.write(datetime.now().strftime("%Y-%m-%d"))


def run_first_align_alert(screener_map, now_str):
    stocks = list(screener_map.values())

    first_fa = [
        d for d in stocks
        if d.get("first_full_align")
        and d.get("market_cap", 0) >= 100_000_000_000
    ]

    if not first_fa:
        send_telegram(f"🌙 [{now_str} 장마감] 오늘 최초정배열 진입 종목 없음 (시총 1,000억 이상 기준)")
        mark_first_align_sent()
        return

    kospi_list  = sorted([d for d in first_fa if d.get("market") == "KOSPI"],
                         key=lambda x: -x.get("market_cap", 0))
    kosdaq_list = sorted([d for d in first_fa if d.get("market") == "KOSDAQ"],
                         key=lambda x: -x.get("market_cap", 0))

    def fmt_fa_row(d):
        gap   = d.get("ma10gap")
        peak  = d.get("prev_peak_gap")
        avg   = d.get("align_avg50")
        price = d.get("price")
        day_chg  = d.get("day_chg")
        week_chg = d.get("chg")
        market   = d.get("market", "")
        cap_str  = fmt_cap(d.get("market_cap", 0))
        meta     = f"{market} · {cap_str}"

        gap_str   = f"{gap:+.1f}%"   if gap   is not None else "—"
        price_str = f"{price:,}원"   if price  else "—"
        day_str   = f"{day_chg:+.2f}%"  if day_chg  is not None else "—"
        week_str  = f"{week_chg:+.1f}%" if week_chg is not None else "—"

        if gap is not None and avg is not None:
            avg_diff = round(gap - avg, 1)
            avg_line = f"평균 : {avg:+.1f}%(+{avg_diff:.1f}% 초과)" if avg_diff >= 0 \
                       else f"평균 : {avg:+.1f}%(△{abs(avg_diff):.1f}% 미달)"
        else:
            avg_line = "평균 : —"

        if gap is not None and peak is not None:
            peak_diff = round(gap - peak, 1)
            peak_line = f"최고 : {peak:+.1f}%(+{peak_diff:.1f}% 돌파)" if peak_diff >= 0 \
                        else f"최고 : {peak:+.1f}%(△{abs(peak_diff):.1f}% 미달)"
        else:
            peak_line = "최고 : —"

        peak_date = d.get("prev_peak_date")
        peak_date_line = f"\n직전최고 : {peak_date}" if peak_date else ""

        return (f"<b>{d['name']}</b> ({meta})\n"
                f"일간 : {day_str}  |  주간 : {week_str}\n"
                f"현재가 : {price_str}  |  10주괴리율 : {gap_str}\n"
                f"{avg_line}\n{peak_line}{peak_date_line}")

    def fmt_fa_section(stock_list):
        heat_order = {"over": 0, "warn": 1, "up": 2, None: 3}
        sorted_list = sorted(stock_list,
                             key=lambda x: (heat_order[heat_label(x.get("ma10gap"), x.get("align_avg50"), x.get("prev_peak_gap"))],
                                            -(x.get("market_cap", 0))))
        buckets = {"over": [], "warn": [], "up": [], None: []}
        for d in sorted_list:
            h = heat_label(d.get("ma10gap"), d.get("align_avg50"), d.get("prev_peak_gap"))
            buckets[h].append(d)

        parts = []
        for d in buckets["over"]:
            parts.append(f"과열🔥\n{fmt_fa_row(d)}")
        for d in buckets["warn"]:
            parts.append(f"과열주의⚠️\n{fmt_fa_row(d)}")
        if buckets["up"]:
            parts.append("상승중📈\n\n" + "\n\n".join(fmt_fa_row(d) for d in buckets["up"]))
        if buckets[None]:
            parts.append("기준없음➖\n\n" + "\n\n".join(fmt_fa_row(d) for d in buckets[None]))
        return "\n\n".join(parts)

    lines = [f"🌙 [{now_str} 장마감] 최초정배열 진입 종목  ({len(first_fa)}개)\n시총 1,000억 이상"]

    if kospi_list:
        lines.append(f"\n━━━━━━━━━━━━━━━━\n📌 KOSPI ({len(kospi_list)}개)\n")
        lines.append(fmt_fa_section(kospi_list))

    if kosdaq_list:
        lines.append(f"\n━━━━━━━━━━━━━━━━\n📌 KOSDAQ ({len(kosdaq_list)}개)\n")
        lines.append(fmt_fa_section(kosdaq_list))

    send_telegram("\n".join(lines))
    mark_first_align_sent()


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

    # 2. 최초정배열 알림 — 금요일 장마감, 하루 한 번만
    if is_closed and now.weekday() == 4:
        if not first_align_already_sent():
            run_first_align_alert(screener_map, now_str)


if __name__ == "__main__":
    # chat_id 확인이 필요할 때만 주석 해제:
    # get_chat_id()
    run_alert()
