import requests
import pandas as pd
import json
import re
import os
from team_mapping import translate_team_name

def fetch_understat_xg():
    print("⏳ 启动 xG 雷达：开始抓取全球真实预期进球数据...")
    leagues = {'EPL': '英超', 'La_liga': '西甲', 'Bundesliga': '德甲', 'Serie_A': '意甲', 'Ligue_1': '法甲'}
    all_data = []
    
    for league_code, league_name in leagues.items():
        url = f"https://understat.com/league/{league_code}/2023" 
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                match = re.search(r"var datesData\s*=\s*JSON.parse\('(.*?)'\)", resp.text)
                if match:
                    json_str = match.group(1).encode().decode('unicode_escape')
                    data = json.loads(json_str)
                    for m in data:
                        all_data.append({
                            'date': m['datetime'][:10],
                            'home_team': translate_team_name(m['h']['title']),
                            'away_team': translate_team_name(m['a']['title']),
                            'home_xg': float(m['xG']['h']),
                            'away_xg': float(m['xG']['a'])
                        })
        except Exception as e:
            pass
            
    if all_data:
        df = pd.DataFrame(all_data).drop_duplicates(subset=['date', 'home_team', 'away_team'])
        df.to_csv('xg_data.csv', index=False, encoding='utf-8-sig')
        print(f"✅ xG 数据抓取完成，共 {len(df)} 场。")
    else:
        print("⚠️ 未抓取到 xG 数据。")

if __name__ == "__main__":
    fetch_understat_xg()
