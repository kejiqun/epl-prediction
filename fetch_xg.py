import requests
import re
import json
import pandas as pd
from io import StringIO
import warnings
warnings.filterwarnings('ignore')

# 使用 requests 结合正则提取网页内嵌的 JSON 数据
def fetch_understat_data(year):
    print(f"⏳ 正在抓取 {year} 赛季 xG 数据...")
    url = f"https://understat.com/league/EPL/{year}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200:
            print(f"⚠️ 抓取失败，状态码: {res.status_code}")
            return None
            
        # 正则提取 matchesData
        match = re.search(r"var matchesData = JSON.parse\('(.*?)'\);", res.text)
        if not match:
            print("⚠️ 未能找到 matchesData 变量")
            return None
            
        # 解码 unicode
        json_str = match.group(1).encode('utf-8').decode('unicode_escape')
        data = json.loads(json_str)
        
        matches = []
        for m in data:
            matches.append({
                'date': m['datetime'][:10], # YYYY-MM-DD
                'home_team': m['h']['title'],
                'away_team': m['a']['title'],
                'home_xg': float(m['xG']['h']),
                'away_xg': float(m['xG']['a']),
                'home_goals': int(m['goals']['h']),
                'away_goals': int(m['goals']['a'])
            })
        return pd.DataFrame(matches)
    except Exception as e:
        print(f"⚠️ 抓取 {year} 赛季出错: {e}")
        return None

print("⏳ 开始抓取近几个赛季的 xG 数据...")
all_data = []
for year in [2023, 2024, 2025, 2026]:
    df = fetch_understat_data(year)
    if df is not None:
        all_data.append(df)

if all_data:
    df_xg = pd.concat(all_data, ignore_index=True)
    # 去除重复
    df_xg = df_xg.drop_duplicates(subset=['date', 'home_team', 'away_team'], keep='last')
    df_xg.to_csv('epl_xg_data.csv', index=False, encoding='utf-8-sig')
    print(f"✅ 成功保存 {len(df_xg)} 场 xG 数据至 epl_xg_data.csv")
else:
    print("⚠️ 所有赛季抓取失败，请检查网络。系统将降级使用旧数据。")
