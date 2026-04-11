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
kospi = fdr.StockListing('KOSPI')[['Code','Name']].copy()
kospi['market'] = 'KOSPI'
kosdaq = fdr.StockListing('KOSDAQ')[['Code','Name']].copy()
kosdaq['market'] = 'KOSDAQ'
stocks = pd.concat([kospi, kosdaq], ignore_index=True)

end = datetime.today()
start = end - timedelta(days=700)
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

        ma10 = weekly.rolling(10).mean()
        ma20 = weekly.rolling(20).mean()
        ma30 = weekly.rolling(30).mean()

        price     = float(weekly.iloc[-1])
        ma10_val  = float(ma10.iloc[-1])
        ma20_val  = float(ma20.iloc[-1]) if not pd.isna(ma20.iloc[-1]) else 0.0
        ma30_val  = float(ma30.iloc[-1])
        ma30_prev = float(ma30.iloc[-2])

        if pd.isna(ma30_val) or ma30_val == 0:
            continue

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

        # 24주 캔들 데이터 (주봉 OHLC)
        weekly_ohlc = df[['Open','High','Low','Close']].resample('W-FRI').agg(
            {'Open':'first','High':'max','Low':'min','Close':'last'}
        ).dropna()
        recent = weekly_ohlc.tail(24)
        candles = [[int(r.Open), int(r.High), int(r.Low), int(r.Close)] for _, r in recent.iterrows()]

        # 24주 이동평균선 값
        def ma_line(series, n=24):
            tail = series.tail(n).tolist()
            return [int(v) if not pd.isna(v) and v != 0 else 0 for v in tail]

        ma10_line = ma_line(ma10)
        ma20_line = ma_line(ma20)
        ma30_line = ma_line(ma30)

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
            'ma10': int(ma10_val) if not pd.isna(ma10_val) else 0,
            'ma20': int(ma20_val),
            'ma30': int(ma30_val),
            'chg': chg,
            'ma10gap': ma10gap,
            'ma30gap': gap,
            'vol': vol_ratio,
            'ma30_slope': ma30_slope,
            'signal': signal,
            'above_ma10_weeks': above_ma10_weeks,
            'above_ma30_weeks': above_ma30_weeks,
            'candles': candles,
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
