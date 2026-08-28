import FinanceDataReader as fdr
import pandas as pd
import json
from datetime import datetime, timedelta

print("업종 매핑 파일 불러오는 중...")
try:
    with open('sector_map.json', 'r', encoding='utf-8') as f:
        sector_map = json.load(f)
    print(f"  {len(sector_map)}개 종목 업종 정보 로드 완료")
except:
    sector_map = {}
    print("  sector_map.json 없음 — 업종 정보 없이 진행")

print("코스피/코스닥 종목 목록 가져오는 중...")
kospi_listing  = fdr.StockListing('KOSPI')
kosdaq_listing = fdr.StockListing('KOSDAQ')

kospi  = kospi_listing[['Code','Name']].copy();  kospi['market']  = 'KOSPI'
kosdaq = kosdaq_listing[['Code','Name']].copy(); kosdaq['market'] = 'KOSDAQ'
stocks = pd.concat([kospi, kosdaq], ignore_index=True)

# 발행주식수 맵 (시가총액 계산용)
shares_map = {}
for listing_df in [kospi_listing, kosdaq_listing]:
    if 'Stocks' in listing_df.columns:
        for _, r in listing_df.iterrows():
            if pd.notna(r.get('Stocks')) and r['Stocks'] > 0:
                shares_map[r['Code']] = int(r['Stocks'])

end = datetime.today()
start = end - timedelta(days=800)
results = []

for i, row in stocks.iterrows():
    code = row['Code']
    name = row['Name']
    market = row['market']

    try:
        df = fdr.DataReader(code, start.strftime('%Y-%m-%d'))
        if len(df) < 60:
            continue

        weekly = df['Close'].resample('W-FRI').last().dropna()
        if len(weekly) < 32:
            continue

        ma5  = weekly.rolling(5).mean()
        ma10 = weekly.rolling(10).mean()
        ma20 = weekly.rolling(20).mean()
        ma30 = weekly.rolling(30).mean()

        price     = float(weekly.iloc[-1])
        ma5_val   = float(ma5.iloc[-1]) if not pd.isna(ma5.iloc[-1]) else 0.0
        ma10_val  = float(ma10.iloc[-1])
        ma20_val  = float(ma20.iloc[-1]) if not pd.isna(ma20.iloc[-1]) else 0.0
        ma30_val  = float(ma30.iloc[-1])
        ma30_prev = float(ma30.iloc[-2])

        if pd.isna(ma30_val) or ma30_val == 0:
            continue

        full_align = (
            ma5_val > 0 and ma10_val > 0 and ma20_val > 0 and ma30_val > 0 and
            price > ma5_val > ma10_val > ma20_val > ma30_val
        )

        day_close = float(df['Close'].iloc[-1])
        day_prev  = float(df['Close'].iloc[-2])
        day_chg   = round((day_close - day_prev) / day_prev * 100, 1) if day_prev else 0.0

        ma5gap  = round((price - ma5_val)  / ma5_val  * 100, 1) if ma5_val  != 0 else 0.0
        ma10gap = round((price - ma10_val) / ma10_val * 100, 1) if not pd.isna(ma10_val) and ma10_val != 0 else 0.0
        gap      = round((price - ma30_val) / ma30_val * 100, 1)
        prev_price = float(weekly.iloc[-2])
        chg      = round((price - prev_price) / prev_price * 100, 1)
        ma30_slope = round((ma30_val - ma30_prev) / ma30_prev * 100, 2)

        weekly_vol = df['Volume'].resample('W-FRI').sum().dropna()
        if len(weekly_vol) >= 10:
            vol_ratio = round(float(weekly_vol.iloc[-1]) / float(weekly_vol.iloc[-11:-1].mean()), 1)
        else:
            vol_ratio = 1.0

        # 30주선 연속 돌파 주수
        prices_arr = weekly.values
        ma10_arr   = ma10.values
        ma20_arr   = ma20.values
        ma30_arr   = ma30.values

        above_ma30_weeks = 0
        for idx in range(len(prices_arr) - 1, -1, -1):
            if not pd.isna(ma30_arr[idx]) and prices_arr[idx] > ma30_arr[idx]:
                above_ma30_weeks += 1
            else:
                break

        # 10주선 연속 돌파 주수
        above_ma10_weeks = 0
        for idx in range(len(prices_arr) - 1, -1, -1):
            if not pd.isna(ma10_arr[idx]) and prices_arr[idx] > ma10_arr[idx]:
                above_ma10_weeks += 1
            else:
                break

        # MA10>MA20>MA30 연속 유지 주수 (전체 정배열 기간, 5주선 제외)
        ma10_align_weeks = 0
        for idx in range(len(prices_arr) - 1, -1, -1):
            m10 = ma10_arr[idx]; m20 = ma20_arr[idx]; m30 = ma30_arr[idx]
            if (not pd.isna(m10) and not pd.isna(m20) and not pd.isna(m30) and
                    m10 > 0 and m20 > 0 and m30 > 0 and m10 > m20 > m30):
                ma10_align_weeks += 1
            else:
                break

        # 24주 캔들 데이터 (주봉 OHLC + 거래량)
        weekly_ohlc = df[['Open','High','Low','Close','Volume']].resample('W-FRI').agg(
            {'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}
        ).dropna()
        recent = weekly_ohlc.tail(24)
        candles = [[int(r.Open), int(r.High), int(r.Low), int(r.Close)] for _, r in recent.iterrows()]
        vol_line = [int(r.Volume) for _, r in recent.iterrows()]

        # 24주 이동평균선 값
        def ma_line(series, n=24):
            tail = series.tail(n).tolist()
            return [int(v) if not pd.isna(v) and v != 0 else 0 for v in tail]

        ma5_line  = ma_line(ma5)
        ma10_line = ma_line(ma10)
        ma20_line = ma_line(ma20)
        ma30_line = ma_line(ma30)

        shares = shares_map.get(code, 0)
        market_cap = int(price * shares) if shares else 0

        # 최초정배열: 직전 주는 full_align 아님 → 이번 주 처음 진입
        prev_ma5_val  = float(ma5.iloc[-2])  if len(ma5)  >= 2 and not pd.isna(ma5.iloc[-2])  else 0.0
        prev_ma10_val = float(ma10.iloc[-2]) if len(ma10) >= 2 and not pd.isna(ma10.iloc[-2]) else 0.0
        prev_ma20_val = float(ma20.iloc[-2]) if len(ma20) >= 2 and not pd.isna(ma20.iloc[-2]) else 0.0
        prev_ma30_val = float(ma30.iloc[-2]) if len(ma30) >= 2 and not pd.isna(ma30.iloc[-2]) else 0.0
        prev_full_align = (
            prev_ma5_val > 0 and prev_ma10_val > 0 and prev_ma20_val > 0 and prev_ma30_val > 0 and
            prev_price > prev_ma5_val > prev_ma10_val > prev_ma20_val > prev_ma30_val
        )
        first_full_align = bool(full_align and not prev_full_align)

        # 2년 정배열 사이클 분석 (MTS 방식 10주선 괴리율)
        N = min(104, len(weekly))
        recent_w = weekly.iloc[-N:]
        ma5_r  = ma5.iloc[-N:];  ma10_r = ma10.iloc[-N:]
        ma20_r = ma20.iloc[-N:]; ma30_r = ma30.iloc[-N:]

        align_data = []
        for dt, w, m5, m10v, m20v, m30v in zip(
            recent_w.index, recent_w.values,
            ma5_r.values, ma10_r.values, ma20_r.values, ma30_r.values
        ):
            if any(pd.isna(v) or v == 0 for v in [m5, m10v, m20v, m30v]):
                align_data.append((dt, None, False)); continue
            w, m5, m10v, m20v, m30v = float(w), float(m5), float(m10v), float(m20v), float(m30v)
            is_aln = w > m5 > m10v > m20v > m30v
            g = round((w - m10v) / m10v * 100, 1) if is_aln and m10v > 0 else None
            align_data.append((dt, g, is_aln))

        cycles = []; cur_c = []
        for dt, g, is_aln in align_data:
            if is_aln:
                cur_c.append((dt, g))
            elif cur_c:
                cycles.append(cur_c); cur_c = []
        if cur_c:
            cycles.append(cur_c)

        def cycle_peak(cyc):
            if not cyc: return None, None
            best = max(cyc, key=lambda x: x[1])
            return best[1], best[0].strftime('%y/%m/%d')

        all_align_gaps = [g for cyc in cycles for _, g in cyc]
        sorted_ag = sorted(all_align_gaps, reverse=True)
        top50 = sorted_ag[:len(sorted_ag)//2] if sorted_ag else []
        align_avg50 = round(sum(top50) / len(top50), 1) if top50 else None

        if full_align and cycles:
            cur_peak_gap, cur_peak_date = cycle_peak(cycles[-1])
        else:
            cur_peak_gap, cur_peak_date = None, None

        # B방식: 2년 내 모든 사이클 통틀어 최고 괴리율 (현재 사이클 제외)
        past_cycles = cycles[:-1] if (full_align and cycles) else cycles
        past_gaps = [(dt, g) for cyc in past_cycles for dt, g in cyc]
        if past_gaps:
            best = max(past_gaps, key=lambda x: x[1])
            prev_peak_gap, prev_peak_date = best[1], best[0].strftime('%y/%m/%d')
        else:
            prev_peak_gap, prev_peak_date = None, None

        if gap > 3 and chg > 2 and vol_ratio > 1.5 and ma30_slope > 0:
            signal = 'strong'
        elif gap > 0 and ma30_slope > 0:
            signal = 'watch'
        else:
            signal = 'weak'

        results.append({
            'name': name,
            'code': code,
            'market': market,
            'sector': sector_map.get(code, '기타'),
            'price': int(price),
            'market_cap': market_cap,
            'ma10': int(ma10_val) if not pd.isna(ma10_val) else 0,
            'ma20': int(ma20_val),
            'ma30': int(ma30_val),
            'day_chg': day_chg,
            'chg': chg,
            'ma5gap': ma5gap,
            'ma10gap': ma10gap,
            'ma30gap': gap,
            'vol': vol_ratio,
            'ma30_slope': ma30_slope,
            'signal': signal,
            'full_align': full_align,
            'first_full_align': first_full_align,
            'ma10_align_weeks': ma10_align_weeks,
            'cur_peak_gap': cur_peak_gap,
            'cur_peak_date': cur_peak_date,
            'prev_peak_gap': prev_peak_gap,
            'prev_peak_date': prev_peak_date,
            'align_avg50': align_avg50,
            'above_ma10_weeks': above_ma10_weeks,
            'above_ma30_weeks': above_ma30_weeks,
            'candles': candles,
            'vol_line': vol_line,
            'ma5_line': ma5_line,
            'ma10_line': ma10_line,
            'ma20_line': ma20_line,
            'ma30_line': ma30_line,
        })

        if (i+1) % 50 == 0:
            print(f"  {i+1}/{len(stocks)} 진행 중... (강한돌파: {sum(1 for r in results if r['signal']=='strong')}개)")

    except Exception as e:
        continue

signal_order = {'strong': 0, 'watch': 1, 'weak': 2}
results.sort(key=lambda x: (signal_order[x['signal']], -x['ma30gap']))

output = {
    'updated': datetime.now().strftime('%Y-%m-%d %H:%M'),
    'stocks': results
}
with open('screener_result.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False)

print(f"\n완료! 총 {len(results)}개 종목 스캔")
print(f"강한돌파: {sum(1 for r in results if r['signal']=='strong')}개")
print(f"관찰중:   {sum(1 for r in results if r['signal']=='watch')}개")
print(f"결과 파일: screener_result.json 저장 완료")
