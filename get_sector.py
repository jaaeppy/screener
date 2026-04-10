import requests
import json
from bs4 import BeautifulSoup

print("네이버 증권 업종 목록 가져오는 중...")
sector_map = {}

r = requests.get(
    'https://finance.naver.com/sise/sise_group.nhn?type=upjong',
    headers={'User-Agent': 'Mozilla/5.0'}
)
r.encoding = 'euc-kr'
soup = BeautifulSoup(r.text, 'html.parser')

links = soup.select('table.type_1 a')
total = len(links)
print(f"  총 {total}개 업종 발견")

for i, link in enumerate(links):
    href = link.get('href', '')
    sector_name = link.text.strip()
    if 'no=' not in href:
        continue

    no = href.split('no=')[-1]
    detail_url = f"https://finance.naver.com/sise/sise_group_detail.nhn?type=upjong&no={no}"

    try:
        dr = requests.get(detail_url, headers={'User-Agent': 'Mozilla/5.0'})
        dr.encoding = 'euc-kr'
        dsoup = BeautifulSoup(dr.text, 'html.parser')
        for a in dsoup.select('a[href*="code="]'):
            code = a['href'].split('code=')[-1][:6]
            if code:
                sector_map[code] = sector_name
        print(f"  [{i+1}/{total}] {sector_name} — {len([c for c,s in sector_map.items() if s==sector_name])}개 종목")
    except Exception as e:
        print(f"  [{i+1}/{total}] {sector_name} 실패: {e}")
        continue

with open('sector_map.json', 'w', encoding='utf-8') as f:
    json.dump(sector_map, f, ensure_ascii=False)

print(f"\n완료! 총 {len(sector_map)}개 종목 업종 매핑 저장")
print("파일: sector_map.json")