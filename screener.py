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
        ma30 = weekly.rolling(30).mean()
        price = float(weekly.iloc[-1])
        ma10_val = float(ma10.iloc[-1])
        ma30_val = float(ma30.iloc[-1])
        ma30_prev = float(ma30.iloc[-2])

        if pd.isna(ma30_val) or ma30_val == 0:
            continue

        ma10gap = round((price - ma10_val) / ma10_val * 100, 1) if not pd.isna(ma10_val) and ma10_val != 0 else 0.0
        gap = round((price - ma30_val) / ma30_val * 100, 1)
        prev_price = float(weekly.iloc[-2])
        chg = round((price - prev_price) / prev_price * 100, 1)
        ma30_slope = round((ma30_val - ma30_prev) / ma30_prev * 100, 2)

        weekly_vol = df['Volume'].resample('W-FRI').sum().dropna()
        if len(weekly_vol) >= 10:
            vol_ratio = round(float(weekly_vol.iloc[-1]) / float(weekly_vol.iloc[-11:-1].mean()), 1)
        else:
            vol_ratio = 1.0

        recent8 = [int(v) for v in weekly.iloc[-8:].tolist()]

        # 30주선 위에 있었던 연속 주수 계산
        prices_arr = weekly.values
        ma30_arr = ma30.values
        above_weeks = 0
        for idx in range(len(prices_arr) - 1, -1, -1):
            if not pd.isna(ma30_arr[idx]) and prices_arr[idx] > ma30_arr[idx]:
                above_weeks += 1
            else:
                break

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
            'ma30': int(ma30_val),
            'chg': chg,
            'ma10gap': ma10gap,
            'ma30gap': gap,
            'vol': vol_ratio,
            'ma30_slope': ma30_slope,
            'rs': 50,
            'weeks': recent8,
            'signal': signal,
            'above_weeks': above_weeks,
        })

        if (i+1) % 50 == 0:
            print(f"  {i+1}/{len(stocks)} 진행 중... (강한돌파: {sum(1 for r in results if r['signal']=='strong')}개)")

    except Exception as e:
        continue

signal_order = {'strong': 0, 'watch': 1, 'weak': 2}
results.sort(key=lambda x: (signal_order[x['signal']], -x['ma30gap']))

with open('screener_result.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False)

print(f"\n완료! 총 {len(results)}개 종목 스캔")
print(f"강한돌파: {sum(1 for r in results if r['signal']=='strong')}개")
print(f"관찰중:   {sum(1 for r in results if r['signal']=='watch')}개")
print(f"결과 파일: screener_result.json 저장 완료")