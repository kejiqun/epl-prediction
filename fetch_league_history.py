import pandas as pd
import requests
from datetime import datetime
import os
import time
from team_mapping import translate_team_name

API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")

# 五大联赛 ID
LEAGUES = {'英超': 39, '西甲': 140, '德甲': 78, '意甲': 135, '法甲': 61}
# 抓取近两个赛季
SEASONS = [2024, 2025] 

def fetch_history():
    if not API_FOOTBALL_KEY:
        print("❌ 没有找到 API_FOOTBALL_KEY")
        return
        
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    all_matches = []
    
    for league_name, league_id in LEAGUES.items():
        for season in SEASONS:
            print(f"⏳ 正在抓取 {league_name} {season} 赛季...")
            url = f"https://v3.football.api-sports.io/fixtures?league={league_id}&season={season}&status=FT"
            try:
                resp = requests.get(url, headers=headers, timeout=20)
                if resp.status_code == 200:
                    data = resp.json().get('response', [])
                    for fixture in data:
                        hg = fixture['goals']['home']
                        ag = fixture['goals']['away']
                        if hg is None or ag is None: continue
                        
                        all_matches.append({
                            'date': fixture['fixture']['date'][:10],
                            'home_team': translate_team_name(fixture['teams']['home']['name']),
                            'away_team': translate_team_name(fixture['teams']['away']['name']),
                            'home_goals': hg,
                            'away_goals': ag
                        })
                    print(f"  ✅ 获取到 {len(data)} 场比赛")
                else:
                    print(f"  ⚠️ 请求失败: {resp.status_code}")
            except Exception as e:
                print(f"  ❌ 异常: {e}")
                
            # 强制休眠 6 秒，保护 API 额度
            time.sleep(6)

    if all_matches:
        df = pd.DataFrame(all_matches).drop_duplicates()
        df.to_csv('all_leagues_matches.csv', index=False, encoding='utf-8-sig')
        print(f"🎉 历史数据建库完成！共 {len(df)} 场，已保存至 all_leagues_matches.csv！")
    else:
        print("❌ 未抓取到任何历史数据，请检查 API Key。")

if __name__ == "__main__":
    fetch_history()
